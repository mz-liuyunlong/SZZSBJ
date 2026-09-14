export interface BackendEnvelope<T, M = Record<string, unknown>> {
  success: boolean;
  data: T;
  error: { code?: string } | null;
  meta: M;
  request_id: string;
}

export async function backendRequest<T, M = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
): Promise<BackendEnvelope<T, M>> {
  const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(previewToken ? { "X-Product-Management-Preview-Token": previewToken } : {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    await response.text();
    throw new Error(
      `API returned non-JSON response (status=${response.status}, url=${response.url || path}, content-type=${contentType || "missing"})`,
    );
  }
  const body = await response.json() as BackendEnvelope<T, M>;
  if (!response.ok || !body.success) {
    throw new Error(body.error?.code ?? "BACKEND_REQUEST_FAILED");
  }
  return body;
}
