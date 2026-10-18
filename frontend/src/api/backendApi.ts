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

export async function backendRequest<T, M = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
): Promise<BackendEnvelope<T, M>> {
  const endRequest = beginBackendRequest();

  try {
    const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
    const authToken = readAuthToken();
    let response: Response;
    try {
      response = await fetch(path, {
        credentials: "same-origin",
        ...init,
        headers: {
          ...(previewToken ? { "X-Product-Management-Preview-Token": previewToken } : {}),
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
    } catch (error) {
      throw transportError(error, init?.signal);
    }

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
      const errorCode = body.error?.code ?? "BACKEND_REQUEST_FAILED";
      throw new BackendRequestError(response.status, errorCode, body.request_id);
    }

    return body;
  } finally {
    endRequest();
  }
}
