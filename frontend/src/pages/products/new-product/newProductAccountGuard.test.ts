import { describe, expect, it } from "vitest";
import { createNewProductAccountGuard } from "./newProductAccountGuard";

describe("new-product account isolation under delayed responses", () => {
  it("discards an older account's late response after switching stores", () => {
    const guard = createNewProductAccountGuard();
    guard.selectAccount("account-a");
    const previous = guard.begin("account-a");
    guard.selectAccount("account-b");
    const latest = guard.begin("account-b");
    expect(guard.isCurrent(previous)).toBe(false);
    expect(guard.isCurrent(latest)).toBe(true);
  });

  it("discards an older page response for the same account", () => {
    const guard = createNewProductAccountGuard();
    guard.selectAccount("account-a");
    const older = guard.begin("account-a");
    const newer = guard.begin("account-a");
    expect(guard.isCurrent(older)).toBe(false);
    expect(guard.isCurrent(newer)).toBe(true);
  });

  it("never allows a ticket for an account that was not selected", () => {
    const guard = createNewProductAccountGuard();
    guard.selectAccount("account-a");
    const wrong = guard.begin("account-b");
    expect(guard.isCurrent(wrong)).toBe(false);
    guard.invalidate();
    expect(guard.isCurrent(wrong)).toBe(false);
  });
});
