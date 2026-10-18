import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendRequestError, backendRequest } from "@/api/backendApi";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("backendRequest", () => {
  it("does not add the preview token when it is not configured", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: {},
      error: null,
      meta: {},
      request_id: "synthetic-request",
    }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", "");

    await backendRequest("/api/product-management/skus");

    expect(fetch).toHaveBeenCalledWith(
      "/api/product-management/skus",
      expect.objectContaining({
        headers: expect.not.objectContaining({
          "X-Product-Management-Preview-Token": expect.anything(),
        }),
      }),
    );
  });

  it("adds the configured preview token in Vite DEV mode", async () => {
    const token = "synthetic-preview-token-that-is-never-logged";
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: {},
      error: null,
      meta: {},
      request_id: "synthetic-request",
    }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", token);

    await backendRequest("/api/product-management/skus");

    expect(fetch).toHaveBeenCalledWith(
      "/api/product-management/skus",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Product-Management-Preview-Token": token,
        }),
      }),
    );
  });

  it("adds the configured preview token outside Vite DEV mode", async () => {
    const token = "synthetic-production-preview-token-that-is-never-logged";
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: {},
      error: null,
      meta: {},
      request_id: "synthetic-request",
    }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", token);

    await backendRequest("/api/integrations/interfaces");

    expect(fetch).toHaveBeenCalledWith(
      "/api/integrations/interfaces",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Product-Management-Preview-Token": token,
        }),
      }),
    );
  });

  it("reports non-JSON responses without exposing the response body", async () => {
    const token = "synthetic-preview-token-that-must-not-appear";
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN", token);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<!doctype html><h1>Vite</h1>", {
      status: 200,
      headers: { "Content-Type": "text/html" },
    })));

    await expect(backendRequest("/api/product-management/skus")).rejects.toMatchObject({
      name: "BackendRequestError",
      status: 200,
      code: "NON_JSON_RESPONSE",
      kind: "invalid_response",
      responseFormat: "non_json",
      message: "NON_JSON_RESPONSE",
    });
  });

  it("classifies a non-JSON 502 as a gateway failure without exposing its body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      "external target connection detail",
      { status: 502, headers: { "Content-Type": "text/plain" } },
    )));

    await expect(backendRequest("/api/auth/login")).rejects.toMatchObject({
      status: 502,
      code: "NON_JSON_RESPONSE",
      kind: "gateway",
      responseFormat: "non_json",
      message: "NON_JSON_RESPONSE",
    });
  });

  it("classifies network, timeout, and cancelled requests separately", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("network detail")));
    await expect(backendRequest("/api/auth/me")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
      kind: "network",
    });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new DOMException("timed out", "TimeoutError")));
    await expect(backendRequest("/api/auth/me")).rejects.toMatchObject({
      code: "REQUEST_TIMEOUT",
      kind: "timeout",
    });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new DOMException("cancelled", "AbortError")));
    await expect(backendRequest("/api/auth/me")).rejects.toMatchObject({
      code: "REQUEST_CANCELLED",
      kind: "cancelled",
    });
  });

  it("rejects a malformed success envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));

    await expect(backendRequest("/api/auth/me")).rejects.toEqual(expect.objectContaining<Partial<BackendRequestError>>({
      code: "INVALID_API_ENVELOPE",
      kind: "invalid_response",
      responseFormat: "invalid_envelope",
    }));
  });
});
