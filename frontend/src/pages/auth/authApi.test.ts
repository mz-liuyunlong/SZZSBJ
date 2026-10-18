// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchCurrentUser, loginWithPassword } from "@/pages/auth/authApi";
import { AUTH_TOKEN_STORAGE_KEY } from "@/pages/auth/authSession";

function envelopeResponse(status: number, data: unknown, code?: string): Response {
  return new Response(JSON.stringify({
    success: status >= 200 && status < 300,
    data,
    error: code ? { code } : null,
    meta: null,
    request_id: "synthetic-request",
  }), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => localStorage.clear());

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("auth API session safety", () => {
  it("returns the current user after login and profile validation", async () => {
    const loginData = {
      access_token: "new-session-token",
      token_type: "bearer",
      expires_at: "2030-01-01T00:00:00Z",
      user: {},
    };
    const currentUserData = {
      id: 1,
      username: "synthetic",
      display_name: "Synthetic User",
      is_super_admin: false,
      role_keys: [],
      role_names: [],
      permissions: [],
    };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(envelopeResponse(200, loginData))
      .mockResolvedValueOnce(envelopeResponse(200, currentUserData)));

    await expect(loginWithPassword({ username: "synthetic", password: "synthetic" }))
      .resolves.toMatchObject({ username: "synthetic", displayName: "Synthetic User" });
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("new-session-token");
  });

  it("clears the current token only for a genuine 401", async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "expired-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      envelopeResponse(401, null, "UNAUTHORIZED"),
    ));

    await expect(fetchCurrentUser()).resolves.toBeUndefined();
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it.each([403, 500, 502, 503, 504])(
    "preserves the token when session restore returns %s",
    async (status) => {
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "preserved-token");
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
        envelopeResponse(status, null, status === 403 ? "FORBIDDEN" : "INTERNAL_ERROR"),
      ));

      await expect(fetchCurrentUser()).rejects.toMatchObject({ status });
      expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("preserved-token");
    },
  );

  it.each([
    [new TypeError("network detail"), "network"],
    [new DOMException("timed out", "TimeoutError"), "timeout"],
  ])("preserves the token for transport failures", async (failure, kind) => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "preserved-token");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));

    await expect(fetchCurrentUser()).rejects.toMatchObject({ kind });
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("preserved-token");
  });

  it("does not let a stale 401 clear a newer login token", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "old-token");
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pendingResponse));

    const restore = fetchCurrentUser();
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "new-token");
    resolveResponse?.(envelopeResponse(401, null, "UNAUTHORIZED"));

    await expect(restore).resolves.toBeUndefined();
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("new-token");
  });

  it("keeps the issued token when the post-login profile check has a gateway failure", async () => {
    const loginData = {
      access_token: "new-session-token",
      token_type: "bearer",
      expires_at: "2030-01-01T00:00:00Z",
      user: {},
    };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(envelopeResponse(200, loginData))
      .mockResolvedValueOnce(envelopeResponse(502, null, "INTERNAL_ERROR")));

    await expect(loginWithPassword({ username: "synthetic", password: "synthetic" }))
      .rejects.toMatchObject({ status: 502, kind: "gateway" });
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("new-session-token");
  });
});
