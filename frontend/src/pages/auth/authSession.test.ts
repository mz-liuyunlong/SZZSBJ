// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_TOKEN_STORAGE_KEY,
  clearAuthTokenIfCurrent,
  isCurrentAuthSessionEvent,
  subscribeAuthSession,
} from "@/pages/auth/authSession";

beforeEach(() => localStorage.clear());

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("auth session synchronization", () => {
  it("does not let stale cleanup remove a newer token", () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "new-token");

    expect(clearAuthTokenIfCurrent("old-token")).toBe(false);
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("new-token");
    expect(clearAuthTokenIfCurrent("new-token")).toBe(true);
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("maps cross-tab storage changes to login and logout events", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuthSession(listener);

    window.dispatchEvent(new StorageEvent("storage", {
      key: AUTH_TOKEN_STORAGE_KEY,
      newValue: "other-tab-token",
    }));
    window.dispatchEvent(new StorageEvent("storage", {
      key: AUTH_TOKEN_STORAGE_KEY,
      oldValue: "other-tab-token",
      newValue: null,
    }));

    expect(listener).toHaveBeenNthCalledWith(1, {
      type: "token-changed",
      token: "other-tab-token",
    });
    expect(listener).toHaveBeenNthCalledWith(2, {
      type: "logged-out",
      token: "other-tab-token",
    });
    unsubscribe();
  });

  it("ignores stale and duplicate events while accepting the matching logout", () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "new-token");

    expect(isCurrentAuthSessionEvent({ type: "logged-out", token: "old-token" })).toBe(false);
    expect(isCurrentAuthSessionEvent({ type: "token-changed", token: "old-token" })).toBe(false);
    expect(isCurrentAuthSessionEvent({ type: "token-changed", token: "new-token" })).toBe(true);
    expect(isCurrentAuthSessionEvent({ type: "token-changed", token: "new-token" })).toBe(false);

    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    expect(isCurrentAuthSessionEvent({ type: "logged-out", token: "old-token" })).toBe(false);
    expect(isCurrentAuthSessionEvent({ type: "logged-out", token: "new-token" })).toBe(true);
    expect(isCurrentAuthSessionEvent({ type: "logged-out", token: "new-token" })).toBe(false);
  });
});
