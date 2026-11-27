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
  it("passes committed facets and search to the summary, not pagination", async () => {
    await getNewProductSummary(undefined,["2026-11-01","2026-11-15"],{
      phase:"pending",npStatuses:"flow:待等级确认",npOwners:"A",npRatings:"C",
      npOwnerKeyword:"",keyword:"YC001",searchField:"sku",
    });
    const url=new URL(vi.mocked(backendRequest).mock.calls[0][0],"https://example.test");
    expect(url.searchParams.get("np_phase")).toBe("pending");
    expect(url.searchParams.get("np_statuses")).toBe("flow:待等级确认");
    expect(url.searchParams.get("np_owners")).toBe("A");
    expect(url.searchParams.get("np_ratings")).toBe("C");
    expect(url.searchParams.get("keyword")).toBe("YC001");
    expect(url.searchParams.get("search_field")).toBe("sku");
    expect(url.searchParams.has("page")).toBe(false);
    expect(url.searchParams.get("first_wfs_end_date")).toBe("2026-11-15");
  });
  it("keeps previous API behavior for a cleared range", async () => {
    await getNewProductSummary();
    await listNewProducts();
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toBe("/api/new-products/summary");
    expect(vi.mocked(backendRequest).mock.calls[1][0]).not.toContain("first_wfs_");
  });
});
