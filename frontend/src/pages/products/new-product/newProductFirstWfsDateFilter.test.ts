import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { getNewProductSummary, listNewProducts } from "./newProductBusinessApi";

vi.mock("@/api/backendApi", () => ({backendRequest:vi.fn(),backendDownload:vi.fn()}));

describe("first WFS performance date filters", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(backendRequest).mockResolvedValue({data:{items:[]}} as never);
  });
  it("sends the same inclusive date bounds to summary and paginated list", async () => {
    await getNewProductSummary(undefined,["2026-11-01","2026-11-15"]);
    await listNewProducts({page:1,pageSize:50,npStatuses:"测评通过",firstWfsStartDate:"2026-11-01",firstWfsEndDate:"2026-11-15"});
    const urls=vi.mocked(backendRequest).mock.calls.map(call=>new URL(call[0],"https://example.test"));
    for (const url of urls) {
      expect(url.searchParams.get("first_wfs_start_date")).toBe("2026-11-01");
      expect(url.searchParams.get("first_wfs_end_date")).toBe("2026-11-15");
    }
    expect(urls[1].searchParams.get("np_statuses")).toBe("测评通过");
    expect(urls[1].searchParams.get("page")).toBe("1");
  });
  it("keeps previous API behavior for a cleared range", async () => {
    await getNewProductSummary();
    await listNewProducts();
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toBe("/api/new-products/summary");
    expect(vi.mocked(backendRequest).mock.calls[1][0]).not.toContain("first_wfs_");
  });
});
