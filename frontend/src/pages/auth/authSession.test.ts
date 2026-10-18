// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_TOKEN_STORAGE_KEY,
  clearAuthTokenIfCurrent,
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
      newValue: null,
    }));

    expect(listener).toHaveBeenNthCalledWith(1, "token-changed");
    expect(listener).toHaveBeenNthCalledWith(2, "logged-out");
    unsubscribe();
  });
});
