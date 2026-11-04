import { afterEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import {
  buildOverviewFilterQuery,
  getOverviewExport,
  listOverviewItems,
  overviewErrorText,
} from "@/pages/pmc/overview/overviewApi";
import { createInitialOverviewFilters } from "@/pages/pmc/overview/overviewTypes";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));

afterEach(() => vi.mocked(backendRequest).mockReset());

describe("overview api", () => {
  it("builds repeated cats and trims the keyword", () => {
    const query = buildOverviewFilterQuery({
      ...createInitialOverviewFilters(),
      storeId: "s1",
      owner: "Ann",
      cats: ["已断货", "断货风险"],
      keyword: "  SKU-1 ",
    });
    expect(query.toString()).toBe(
      new URLSearchParams([
        ["store_id", "s1"], ["owner", "Ann"], ["cats", "已断货"], ["cats", "断货风险"],
        ["keyword", "SKU-1"], ["only_issue", "true"],
      ]).toString(),
    );
  });

  it("reads total from meta and pages through the contract", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ data: { items: [] }, meta: { total: 7 } } as never);
    const result = await listOverviewItems(createInitialOverviewFilters(), 2, 100);
    expect(result.total).toBe(7);
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toBe("/api/pmc/overview/items?only_issue=true&page=2&page_size=100");
  });

  it("sends the whitelisted sort and reads category counts", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ data: { items: [], category_counts: { 已断货: 3 } }, meta: { total: 0 } } as never);
    const result = await listOverviewItems(createInitialOverviewFilters(), 1, 50, undefined, { by: "supply", order: "asc" });
    expect(result.categoryCounts).toEqual({ 已断货: 3 });
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toBe(
      "/api/pmc/overview/items?only_issue=true&page=1&page_size=50&sort_by=supply&sort_order=asc",
    );
  });

  it("exports everything when no filter is given", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ data: { items: [] } } as never);
    await getOverviewExport();
    expect(vi.mocked(backendRequest).mock.calls[0][0]).toBe("/api/pmc/overview/export?only_issue=false");
  });

  it("explains not-ready and permission errors", () => {
    expect(overviewErrorText({ status: 503, code: "PMC_OVERVIEW_NOT_READY" })).toContain("快照");
    expect(overviewErrorText({ status: 403, code: "FORBIDDEN" })).toContain("pmc:overview:read");
    expect(overviewErrorText({ status: 403, code: "DATA_SCOPE_DENIED" })).toContain("数据范围");
  });
});
