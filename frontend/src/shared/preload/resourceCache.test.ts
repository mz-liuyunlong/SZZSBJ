import { afterEach, describe, expect, it, vi } from "vitest";
import { clearResourceCache, getCachedResource } from "@/shared/preload/resourceCache";

afterEach(() => clearResourceCache());

describe("resource cache invalidation", () => {
  it("does not restore a stale response after a write invalidates its pending request", async () => {
    let resolveOld!: (value: string) => void;
    const oldLoader = vi.fn(() => new Promise<string>((resolve) => { resolveOld = resolve; }));
    const newLoader = vi.fn(async () => "new state");
    const oldRequest = getCachedResource("listing-management:rows", oldLoader);

    clearResourceCache("listing-management:");
    expect(await getCachedResource("listing-management:rows", newLoader)).toBe("new state");
    resolveOld("old state");
    expect(await oldRequest).toBe("old state");
    expect(await getCachedResource("listing-management:rows", newLoader)).toBe("new state");
    expect(newLoader).toHaveBeenCalledTimes(1);
  });

  it("does not let a stale request error erase a newer cached response", async () => {
    let rejectOld!: (error: Error) => void;
    const oldRequest = getCachedResource("listing-management:summary", () => new Promise<string>((_, reject) => {
      rejectOld = reject;
    }));
    clearResourceCache("listing-management:");
    const newLoader = vi.fn(async () => "new summary");
    expect(await getCachedResource("listing-management:summary", newLoader)).toBe("new summary");
    rejectOld(new Error("old request failed"));
    await expect(oldRequest).rejects.toThrow("old request failed");
    expect(await getCachedResource("listing-management:summary", newLoader)).toBe("new summary");
    expect(newLoader).toHaveBeenCalledTimes(1);
  });
});
