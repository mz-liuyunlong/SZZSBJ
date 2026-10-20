// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BackendRequestError,
  backendDownload,
  backendDownloadErrorMessage,
} from "@/api/backendApi";
import { AUTH_TOKEN_STORAGE_KEY } from "@/pages/auth/authSession";

const successEnvelope = (code: string, requestId = "synthetic-request") => JSON.stringify({
  success: false,
  data: null,
  error: { code },
  meta: null,
  request_id: requestId,
});

const installDownloadDom = () => {
  const createObjectURL = vi.fn().mockReturnValue("blob:synthetic-download");
  const revokeObjectURL = vi.fn();
  let downloadedFilename = "";
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click(
    this: HTMLAnchorElement,
  ) {
    downloadedFilename = this.download;
  });
  return { createObjectURL, revokeObjectURL, downloadedFilename: () => downloadedFilename };
};

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("backendDownload", () => {
  it("uses the real session token, downloads the file, and cleans up the object URL", async () => {
    const authToken = "synthetic-user-session-that-must-not-be-logged";
    const previewToken = "synthetic-preview-session-that-must-not-be-used";
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authToken);
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", previewToken);
    const fetch = vi.fn().mockResolvedValue(new Response("csv-content", {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="safe-export.csv"',
      },
    }));
    vi.stubGlobal("fetch", fetch);
    const download = installDownloadDom();

    await backendDownload("/api/protected/export", "fallback.csv");

    expect(fetch).toHaveBeenCalledWith("/api/protected/export", expect.objectContaining({
      credentials: "same-origin",
      headers: expect.objectContaining({ Authorization: `Bearer ${authToken}` }),
    }));
    const headers = fetch.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers["X-Product-Management-Preview-Token"]).toBeUndefined();
    expect(download.downloadedFilename()).toBe("safe-export.csv");
    expect(download.createObjectURL).toHaveBeenCalledOnce();
    expect(download.revokeObjectURL).toHaveBeenCalledWith("blob:synthetic-download");
  });

  it.each([
    [401, "UNAUTHORIZED", "authentication"],
    [403, "FORBIDDEN", "authorization"],
    [403, "DATA_SCOPE_DENIED", "authorization"],
    [422, "INVALID_REQUEST", "validation"],
    [500, "INTERNAL_ERROR", "server"],
  ] as const)("classifies %s %s without exposing response details", async (status, code, kind) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(successEnvelope(code), {
      status,
      headers: { "Content-Type": "application/json" },
    })));

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toEqual(
      expect.objectContaining<Partial<BackendRequestError>>({
        status,
        code,
        kind,
        requestId: "synthetic-request",
        message: code,
      }),
    );
  });

  it("does not invent an identity when no session or preview token exists", async () => {
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", "");
    const fetch = vi.fn().mockResolvedValue(new Response(successEnvelope("UNAUTHORIZED"), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });
    expect(fetch.mock.calls[0]?.[1]?.headers).not.toEqual(expect.objectContaining({
      Authorization: expect.anything(),
    }));
    expect(fetch.mock.calls[0]?.[1]?.headers).not.toEqual(expect.objectContaining({
      "X-Product-Management-Preview-Token": expect.anything(),
    }));
  });

  it("keeps preview mode separate and does not grant export permission", async () => {
    const previewToken = "synthetic-preview-session-that-cannot-export";
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", previewToken);
    const fetch = vi.fn().mockResolvedValue(new Response(successEnvelope("FORBIDDEN"), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 403,
      code: "FORBIDDEN",
    });
    expect(fetch.mock.calls[0]?.[1]?.headers).toEqual(expect.objectContaining({
      "X-Product-Management-Preview-Token": previewToken,
    }));
    expect(fetch.mock.calls[0]?.[1]?.headers).not.toEqual(expect.objectContaining({
      Authorization: expect.anything(),
    }));
  });

  it("classifies a Vercel-style non-JSON 502 without exposing the body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      "external target connection detail",
      { status: 502, headers: { "Content-Type": "text/plain" } },
    )));

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 502,
      code: "NON_JSON_RESPONSE",
      kind: "gateway",
      responseFormat: "non_json",
      message: "NON_JSON_RESPONSE",
    });
  });

  it.each([
    [
      new Response("proxy unauthorized", {
        status: 401,
        headers: { "Content-Type": "text/plain" },
      }),
      "NON_JSON_RESPONSE",
    ],
    [
      new Response(JSON.stringify({ error: "proxy" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
      "INVALID_API_ENVELOPE",
    ],
  ])("keeps the session for an untrusted download 401", async (response, code) => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "preserved-session");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    let failure: unknown;
    try {
      await backendDownload("/api/protected/export", "fallback.csv");
    } catch (error) {
      failure = error;
    }

    expect(failure).toMatchObject({ status: 401, code });
    expect(backendDownloadErrorMessage(failure)).toBe("认证服务响应异常，请稍后重试");
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("preserved-session");
  });

  it("rejects an HTML success page instead of downloading it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      "<!doctype html><title>proxy error</title>",
      {
        status: 200,
        headers: {
          "Content-Type": "text/html",
          "X-Request-ID": "synthetic-html-request",
        },
      },
    )));

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 200,
      code: "UNEXPECTED_DOWNLOAD_CONTENT_TYPE",
      kind: "invalid_response",
      requestId: "synthetic-html-request",
    });
  });

  it("accepts a real XLSX response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("xlsx", {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    })));
    const download = installDownloadDom();

    await backendDownload("/api/protected/template", "template.xlsx");

    expect(download.downloadedFilename()).toBe("template.xlsx");
    expect(download.revokeObjectURL).toHaveBeenCalledOnce();
  });

  it("classifies network failures without inventing an authorization error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network detail")));

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
      kind: "network",
    });
  });

  it("classifies download timeouts separately", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("timed out", "TimeoutError")));

    await expect(backendDownload("/api/protected/export", "fallback.csv")).rejects.toMatchObject({
      status: 0,
      code: "REQUEST_TIMEOUT",
      kind: "timeout",
    });
  });

  it("revokes the object URL when the browser download click fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("binary", {
      status: 200,
      headers: { "Content-Type": "application/octet-stream" },
    })));
    const download = installDownloadDom();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new Error("synthetic click failure");
    });

    await expect(backendDownload("/api/protected/export", "fallback.bin")).rejects.toThrow(
      "synthetic click failure",
    );
    expect(download.revokeObjectURL).toHaveBeenCalledWith("blob:synthetic-download");
  });

  it.each([
    [new BackendRequestError(401, "UNAUTHORIZED"), "登录状态已失效，请重新登录"],
    [
      new BackendRequestError(
        401,
        "NON_JSON_RESPONSE",
        undefined,
        "authentication",
        "non_json",
      ),
      "认证服务响应异常，请稍后重试",
    ],
    [
      new BackendRequestError(
        401,
        "INVALID_API_ENVELOPE",
        undefined,
        "authentication",
        "invalid_envelope",
      ),
      "认证服务响应异常，请稍后重试",
    ],
    [new BackendRequestError(403, "FORBIDDEN"), "当前账号缺少导出权限"],
    [new BackendRequestError(403, "DATA_SCOPE_DENIED"), "当前账号没有可导出的数据范围"],
    [new BackendRequestError(422, "INVALID_REQUEST"), "导出参数或字段无效"],
    [new BackendRequestError(500, "INTERNAL_ERROR"), "导出服务异常，请稍后重试"],
    [new BackendRequestError(502, "NON_JSON_RESPONSE"), "导出服务暂时不可用，请稍后重试"],
    [new BackendRequestError(0, "NETWORK_ERROR", undefined, "network"), "网络连接失败，请检查网络后重试"],
    [new BackendRequestError(0, "REQUEST_TIMEOUT", undefined, "timeout"), "导出请求超时，请稍后重试"],
  ])("returns a safe user message for %#", (error, expected) => {
    expect(backendDownloadErrorMessage(error)).toBe(expected);
    expect(backendDownloadErrorMessage(error)).not.toContain("synthetic-secret");
  });
});
