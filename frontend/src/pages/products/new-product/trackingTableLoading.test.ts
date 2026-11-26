/** The tracking list owns its loading state; other requests retain global busy semantics. */
import { describe, expect, it } from "vitest";
import { beginBackendRequest, getBackendRequestBusySnapshot, runWithoutBackendRequestBusy } from "@/shared/network/backendRequestBusy";
import source from "./NewProductTrackingReport.tsx?raw";

describe("tracking table loading", () => {
  it("keeps query placeholders and mounts loading only on the table", () => {
    expect(source).toContain("placeholderData:keepPreviousData");
    expect(source).toContain("loading={listingQuery.isFetching}");
    expect(source).not.toContain("正在读取打品明细…");
    expect(source).toContain("disabled={listingQuery.isPlaceholderData || listingQuery.isFetching}");
    expect(source).toContain("from:dateRange?.[0],to:dateRange?.[1]");
    expect(source).toContain("queryFn:({signal})=>runWithoutBackendRequestBusy(()=>listTrackingProducts({");
  });

  it("suppresses only the explicitly scoped read without leaking to other requests", async () => {
    let finishScoped: (() => void) | undefined;
    const work = runWithoutBackendRequestBusy(async () => {
      finishScoped = beginBackendRequest();
      await Promise.resolve();
      finishScoped();
    });
    expect(getBackendRequestBusySnapshot()).toBe(false);
    const finishNormal = beginBackendRequest();
    try {
      expect(getBackendRequestBusySnapshot()).toBe(true);
      await work;
      expect(getBackendRequestBusySnapshot()).toBe(true);
    } finally {
      finishNormal();
      finishScoped?.();
    }
    expect(getBackendRequestBusySnapshot()).toBe(false);
  });
});
