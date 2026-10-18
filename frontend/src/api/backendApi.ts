import { beginBackendRequest } from "@/shared/network/backendRequestBusy";
import { readAuthToken } from "@/pages/auth/authSession";
export interface BackendEnvelope<T, M = Record<string, unknown>> {
  success: boolean;
  data: T;
  error: { code?: string } | null;
  meta: M;
  request_id: string;
}

export type BackendErrorKind =
  | "authentication"
  | "authorization"
  | "validation"
  | "rate_limit"
  | "gateway"
  | "server"
  | "http"
  | "network"
  | "timeout"
  | "cancelled"
  | "invalid_response";

export type BackendResponseFormat = "json" | "non_json" | "invalid_envelope";

export class BackendRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly kind: BackendErrorKind;
  readonly responseFormat: BackendResponseFormat;

  constructor(
    status: number,
    code: string,
    requestId?: string,
    kind = classifyHttpStatus(status),
    responseFormat: BackendResponseFormat = "json",
  ) {
    super(code);
    this.name = "BackendRequestError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.kind = kind;
    this.responseFormat = responseFormat;
  }
}

function classifyHttpStatus(status: number): BackendErrorKind {
  if (status === 401) return "authentication";
  if (status === 403) return "authorization";
  if (status === 400 || status === 409 || status === 422) return "validation";
  if (status === 429) return "rate_limit";
  if (status === 502 || status === 503 || status === 504) return "gateway";
  if (status >= 500) return "server";
  return "http";
}

function transportError(error: unknown, signal?: AbortSignal | null): BackendRequestError {
  const name = error instanceof DOMException ? error.name : "";
  const signalReasonName = signal?.reason instanceof DOMException ? signal.reason.name : "";
  if (name === "TimeoutError" || signalReasonName === "TimeoutError") {
    return new BackendRequestError(0, "REQUEST_TIMEOUT", undefined, "timeout");
  }
  if (name === "AbortError" || signal?.aborted) {
    return new BackendRequestError(0, "REQUEST_CANCELLED", undefined, "cancelled");
  }
  return new BackendRequestError(0, "NETWORK_ERROR", undefined, "network");
}

function isBackendEnvelope(value: unknown): value is BackendEnvelope<unknown, unknown> {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.success === "boolean"
    && typeof candidate.request_id === "string"
    && "data" in candidate
    && "error" in candidate;
}

async function fetchBackendResponse(path: string, init?: RequestInit): Promise<Response> {
  const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
  const authToken = readAuthToken();
  try {
    return await fetch(path, {
      credentials: "same-origin",
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
        ...(authToken
          ? { Authorization: `Bearer ${authToken}` }
          : previewToken
            ? { "X-Product-Management-Preview-Token": previewToken }
            : {}),
      },
    });
  } catch (error) {
    throw transportError(error, init?.signal);
  }
}

async function parseBackendEnvelope<T, M>(response: Response): Promise<BackendEnvelope<T, M>> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    await response.text();
    throw new BackendRequestError(
      response.status,
      "NON_JSON_RESPONSE",
      response.headers.get("X-Request-ID") ?? undefined,
      response.ok ? "invalid_response" : classifyHttpStatus(response.status),
      "non_json",
    );
  }

  let parsedBody: unknown;
  try {
    parsedBody = await response.json();
  } catch {
    throw new BackendRequestError(
      response.status,
      "INVALID_JSON_RESPONSE",
      response.headers.get("X-Request-ID") ?? undefined,
      response.ok ? "invalid_response" : classifyHttpStatus(response.status),
      "non_json",
    );
  }
  if (!isBackendEnvelope(parsedBody)) {
    throw new BackendRequestError(
      response.status,
      "INVALID_API_ENVELOPE",
      response.headers.get("X-Request-ID") ?? undefined,
      response.ok ? "invalid_response" : classifyHttpStatus(response.status),
      "invalid_envelope",
    );
  }
  const body = parsedBody as BackendEnvelope<T, M>;
  if (!response.ok || !body.success) {
    throw new BackendRequestError(
      response.status,
      body.error?.code ?? "BACKEND_REQUEST_FAILED",
      body.request_id,
    );
  }
  return body;
}

function downloadFilename(response: Response, fallbackFilename: string): string {
  const disposition = response.headers.get("content-disposition") ?? "";
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const filenameMatch = /filename="?([^";]+)"?/i.exec(disposition);
  const rawFilename = utf8Match?.[1] ?? filenameMatch?.[1];
  if (!rawFilename) return fallbackFilename;
  try {
    return decodeURIComponent(rawFilename).split(/[\\/]/).pop() || fallbackFilename;
  } catch {
    return rawFilename.split(/[\\/]/).pop() || fallbackFilename;
  }
}

function acceptsDownloadContentType(response: Response, filename: string): boolean {
  const contentType = (response.headers.get("content-type") ?? "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase();
  if (filename.toLowerCase().endsWith(".csv")) {
    return contentType === "text/csv" || contentType === "application/csv";
  }
  if (filename.toLowerCase().endsWith(".xlsx")) {
    return contentType === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  return contentType === "application/octet-stream";
}

export async function backendRequest<T, M = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
): Promise<BackendEnvelope<T, M>> {
  const endRequest = beginBackendRequest();

  try {
    return await parseBackendEnvelope<T, M>(await fetchBackendResponse(path, init));
  } finally {
    endRequest();
  }
}

export async function backendDownload(
  path: string,
  fallbackFilename: string,
  init?: RequestInit,
): Promise<void> {
  const endRequest = beginBackendRequest();
  try {
    const response = await fetchBackendResponse(path, init);
    if (!response.ok) {
      await parseBackendEnvelope(response);
      throw new BackendRequestError(response.status, "BACKEND_DOWNLOAD_FAILED");
    }
    if (!acceptsDownloadContentType(response, fallbackFilename)) {
      throw new BackendRequestError(
        response.status,
        "UNEXPECTED_DOWNLOAD_CONTENT_TYPE",
        response.headers.get("X-Request-ID") ?? undefined,
        "invalid_response",
        "non_json",
      );
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    try {
      link.href = url;
      link.download = downloadFilename(response, fallbackFilename);
      document.body.appendChild(link);
      link.click();
    } finally {
      link.remove();
      URL.revokeObjectURL(url);
    }
  } finally {
    endRequest();
  }
}

export function backendDownloadErrorMessage(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "导出失败，请稍后重试";
  if (error.status === 401) return "登录状态已失效，请重新登录";
  if (error.code === "DATA_SCOPE_DENIED") return "当前账号没有可导出的数据范围";
  if (error.status === 403) return "当前账号缺少导出权限";
  if (error.status === 422) return "导出参数或字段无效";
  if (error.kind === "gateway") return "导出服务暂时不可用，请稍后重试";
  if (error.kind === "network") return "网络连接失败，请检查网络后重试";
  if (error.kind === "timeout") return "导出请求超时，请稍后重试";
  if (error.kind === "server") return "导出服务异常，请稍后重试";
  return "导出失败，请稍后重试";
}
