import { afterEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";

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

    const request = backendRequest("/api/product-management/skus");

    await expect(request).rejects.toThrow(
      "API returned non-JSON response (status=200, url=/api/product-management/skus, content-type=text/html)",
    );
    await expect(request).rejects.not.toThrow("<!doctype");
    await expect(request).rejects.not.toThrow(token);
  });
});
