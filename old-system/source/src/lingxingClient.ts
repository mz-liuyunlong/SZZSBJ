import type { AxiosError, AxiosInstance, AxiosRequestConfig } from "axios";
import CryptoJS from "crypto-js";
import FormData from "form-data";
import { LingxingConfig } from "./config";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

type SignParams = Record<string, unknown>;
type ReadonlyMethod = "GET" | "POST";

export interface TokenData {
  access_token: string;
  refresh_token?: string;
  expires_in?: number | string;
}

export interface TokenResponse {
  code?: string | number;
  msg?: string;
  message?: string;
  data?: TokenData | null;
}

export interface LingxingApiResponse<T = unknown> {
  code?: string | number;
  message?: string;
  msg?: string;
  error_details?: unknown;
  request_id?: string;
  response_time?: string;
  data?: T;
}

export interface ApiResult<T = unknown> {
  status: number;
  data: LingxingApiResponse<T>;
}

export interface ReadonlyRequestOptions {
  method: ReadonlyMethod;
  path: string;
  params?: SignParams;
  timeoutMs?: number;
}

export class LingxingRequestError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly data?: unknown,
  ) {
    super(message);
    this.name = "LingxingRequestError";
  }
}

export class LingxingClient {
  private readonly http: AxiosInstance;
  private accessToken?: string;
  private tokenExpiresAtMs?: number;

  constructor(private readonly config: LingxingConfig) {
    this.http = axios.create({
      baseURL: config.baseURL,
      timeout: config.timeoutMs,
      validateStatus: () => true,
    });
  }

  async fetchAccessToken(timeoutMs?: number): Promise<{ status: number; token: TokenData; raw: TokenResponse }> {
    const form = new FormData();
    form.append("appId", this.config.appId);
    form.append("appSecret", this.config.appSecret);

    const response = await this.http.post<TokenResponse>(
      "/api/auth-server/oauth/access-token",
      form,
      {
        headers: form.getHeaders(),
        timeout: timeoutMs,
      },
    );

    const body = response.data;

    if (response.status < 200 || response.status >= 300 || String(body?.code) !== "200" || !body?.data?.access_token) {
      const reason =
        response.status < 200 || response.status >= 300
          ? `Token request failed with HTTP ${response.status}: ${getResponseMessage(body)}`
          : `Token request rejected: ${getResponseMessage(body)}`;
      logRequestResult("/api/auth-server/oauth/access-token", response.status, false, reason);
      throw new LingxingRequestError(reason, response.status, body);
    }

    logRequestResult("/api/auth-server/oauth/access-token", response.status, true);

    return {
      status: response.status,
      token: body.data,
      raw: body,
    };
  }

  async get<T = unknown>(path: string, params: SignParams = {}): Promise<ApiResult<T>> {
    return this.requestWithStatus<T>({
      method: "GET",
      path,
      params,
    });
  }

  async post<T = unknown>(path: string, params: SignParams = {}): Promise<ApiResult<T>> {
    return this.requestWithStatus<T>({
      method: "POST",
      path,
      params,
    });
  }

  async request<T = unknown>(options: ReadonlyRequestOptions): Promise<LingxingApiResponse<T>> {
    const result = await this.requestWithStatus<T>(options);
    return result.data;
  }

  private async requestWithStatus<T = unknown>(options: ReadonlyRequestOptions): Promise<ApiResult<T>> {
    const method = normalizeReadonlyMethod(options.method);
    const path = normalizePath(options.path);
    assertReadOnlyPath(path);

    const businessParams = options.params ?? {};
    const accessToken = await this.getAccessToken(options.timeoutMs);
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const commonParams = {
      access_token: accessToken,
      app_key: this.config.appId,
      timestamp,
    };
    const sign = this.generateSign({ ...businessParams, ...commonParams });
    const queryParams = {
      ...commonParams,
      sign,
    };

    const requestConfig: AxiosRequestConfig = {
      method,
      url: path,
      timeout: options.timeoutMs,
      params:
        method === "GET"
          ? { ...businessParams, ...queryParams }
          : queryParams,
    };

    if (method === "POST") {
      requestConfig.headers = { "Content-Type": "application/json" };
      requestConfig.data = businessParams;
    }

    try {
      const response = await this.http.request<LingxingApiResponse<T>>(requestConfig);
      const success = response.status >= 200 && response.status < 300 && Number(response.data?.code) === 0;

      logRequestResult(path, response.status, success, success ? undefined : getResponseMessage(response.data));

      if (!success) {
        throw new LingxingRequestError(
          `Lingxing API request failed: ${getResponseMessage(response.data)}`,
          response.status,
          response.data,
        );
      }

      return {
        status: response.status,
        data: response.data,
      };
    } catch (error) {
      if (error instanceof LingxingRequestError) {
        throw error;
      }

      const reason = getErrorReason(error);
      logRequestResult(path, undefined, false, reason);
      throw new LingxingRequestError(reason);
    }
  }

  generateSign(params: SignParams): string {
    const signingString = buildSigningString(params);
    const md5Value = CryptoJS.MD5(signingString).toString().toUpperCase();
    const key = CryptoJS.enc.Utf8.parse(this.config.appId);
    const encrypted = CryptoJS.AES.encrypt(md5Value, key, {
      mode: CryptoJS.mode.ECB,
      padding: CryptoJS.pad.Pkcs7,
    });

    return encrypted.toString();
  }

  private async getAccessToken(timeoutMs?: number): Promise<string> {
    if (this.config.accessToken) {
      return this.config.accessToken;
    }

    if (this.accessToken && this.tokenExpiresAtMs && Date.now() < this.tokenExpiresAtMs) {
      return this.accessToken;
    }

    const tokenResult = await this.fetchAccessToken(timeoutMs);
    this.accessToken = tokenResult.token.access_token;
    this.tokenExpiresAtMs = calculateTokenExpiresAtMs(tokenResult.token.expires_in);

    return this.accessToken;
  }
}

export function buildSigningString(params: SignParams): string {
  return Object.keys(params)
    .filter((key) => key !== "sign" && key !== "api_code")
    .sort()
    .flatMap((key) => {
      const value = toSigningValue(params[key]);

      if (value === undefined || value === "") {
        return [];
      }

      return `${key}=${value}`;
    })
    .join("&");
}

export function maskSecret(value: string | undefined): string {
  if (!value) {
    return "(empty)";
  }

  if (value.length <= 8) {
    return "****";
  }

  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

export function getErrorReason(error: unknown): string {
  if (error instanceof LingxingRequestError) {
    return error.message;
  }

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    const status = axiosError.response?.status;
    const code = axiosError.code;

    if (code === "ECONNABORTED") {
      return "Request timeout";
    }

    const message = getResponseMessage(axiosError.response?.data);
    return status ? `HTTP ${status}: ${message}` : error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

export function getResponseMessage(data: unknown): string {
  if (!data || typeof data !== "object") {
    return data ? String(data) : "No response body";
  }

  const body = data as Record<string, unknown>;
  const message = body.message ?? body.msg ?? body.error ?? body.code;
  return message ? String(message) : JSON.stringify(body);
}

function normalizeReadonlyMethod(method: ReadonlyMethod): ReadonlyMethod {
  const normalizedMethod = method.toUpperCase();

  if (normalizedMethod !== "GET" && normalizedMethod !== "POST") {
    throw new Error("Lingxing readonly request only supports GET and POST");
  }

  return normalizedMethod;
}

function normalizePath(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error("Lingxing API path must start with /");
  }

  if (/^https?:\/\//i.test(path)) {
    throw new Error("Lingxing API path must be a path, not an absolute URL");
  }

  return path;
}

function assertReadOnlyPath(path: string): void {
  const unsafePattern =
    /\/(add|batchRename|batchOperate|batchDelete|cancel|confirm|create|delete|discard|edit|fastReceive|finish|invalid|modify|operate|publish|receive|refund|remove|rename|revoke|send|set|submit|sync|update|upload)(\/|$)/i;

  if (unsafePattern.test(path)) {
    throw new Error(`Refusing to call a possible write operation path: ${path}`);
  }
}

function calculateTokenExpiresAtMs(expiresIn: TokenData["expires_in"]): number {
  const expiresInSeconds = Number(expiresIn);

  if (!Number.isFinite(expiresInSeconds) || expiresInSeconds <= 0) {
    return Date.now() + 55 * 60 * 1000;
  }

  const safetyWindowSeconds = 60;
  return Date.now() + Math.max(expiresInSeconds - safetyWindowSeconds, 1) * 1000;
}

function logRequestResult(path: string, status: number | undefined, success: boolean, reason?: string): void {
  console.log(`请求路径: ${path}`);
  console.log(`HTTP 状态码: ${status ?? "N/A"}`);
  console.log(`是否成功: ${success ? "是" : "否"}`);

  if (!success && reason) {
    console.log(`错误原因: ${reason}`);
  }
}

function toSigningValue(value: unknown): string | undefined {
  if (value === undefined) {
    return undefined;
  }

  if (value === null) {
    return "null";
  }

  if (typeof value === "object") {
    // TODO: Confirm per-endpoint signing requirements if Lingxing documents a
    // different JSON serialization rule for nested objects or arrays.
    return JSON.stringify(value).trim();
  }

  return String(value).trim();
}
