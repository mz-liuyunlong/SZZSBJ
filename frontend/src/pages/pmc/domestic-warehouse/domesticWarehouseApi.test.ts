import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import { domesticErrorText, domesticFilterQuery, getDomesticFilterOptions, getDomesticSummary, getDomesticTrace, listDomesticBatches } from "./domesticWarehouseApi";
import { initialDomesticFilters } from "./domesticWarehouseTypes";
vi.mock("@/api/backendApi", async (original) => ({ ...await original<typeof import("@/api/backendApi")>(), backendRequest: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
describe("domestic inbound contract", () => {
  it("serializes inbound dates, precise order arrays, repeated scopes and inventory status", () => {
    const q = domesticFilterQuery({ ...initialDomesticFilters(), searchType: "inbound", batchValues: ["IB-1", "IB-2", "IB-1"],
      ownerUids: ["0001", "0002"], warehouseIds: ["W1", "W2"], storeIds: ["001"], inboundFrom: "2026-10-01", inboundTo: "2026-10-20", inventoryStatus: "unknown" });
    expect(q.getAll("inbound_order_sn")).toEqual(["IB-1", "IB-2"]);
    expect(q.getAll("owner_uid")).toEqual(["0001", "0002"]);
    expect(q.getAll("warehouse_id")).toEqual(["W1", "W2"]); expect(q.getAll("store_id")).toEqual(["001"]);
    expect(q.get("inbound_from")).toBe("2026-10-01"); expect(q.get("inventory_status")).toBe("unknown");
    expect([...q.keys()].some((k) => /receipt|mapping|received/.test(k))).toBe(false);
    expect(() => domesticFilterQuery({ ...initialDomesticFilters(), searchType: "all", batchValues: ["1", "2"] })).toThrow();
    expect(() => domesticFilterQuery({ ...initialDomesticFilters(), batchValues: Array.from({ length: 51 }, (_, i) => String(i)) })).toThrow();
  });
  it("calls only inbound endpoints, carries cancellation, and excludes paging from summary", async () => {
    const result = { success: true, data: { items: [{ balance_num: 0, parent_inbound_qty: null }], total: 51 }, error: null, meta: {}, request_id: "synthetic" };
    vi.mocked(backendRequest).mockResolvedValue(result);
    const signal = new AbortController().signal;
    expect(await listDomesticBatches({ ...initialDomesticFilters(), sort: "balance_desc" }, 2, 50, signal)).toBe(result);
    await getDomesticSummary(initialDomesticFilters(), signal); await getDomesticTrace("batch/1", signal);
    const calls = vi.mocked(backendRequest).mock.calls;
    const url = new URL(calls[0][0], "http://localhost");
    expect(url.pathname).toBe("/api/pmc/domestic/inbound-batches"); expect(url.searchParams.get("page")).toBe("2"); expect(url.searchParams.get("sort")).toBe("balance_desc");
    expect(calls[0][1]?.signal).toBe(signal);
    const summary = new URL(calls[1][0], "http://localhost");
    expect(summary.pathname).toBe("/api/pmc/domestic/inbound-batches/summary"); expect(summary.searchParams.has("page")).toBe(false); expect(summary.searchParams.has("sort")).toBe(false);
    expect(calls[2][0]).toBe("/api/pmc/domestic/inbound-batches/batch%2F1/trace");
  });
  it("loads full inbound filter options with warehouse scope and cancellation", async () => {
    const signal = new AbortController().signal;
    await getDomesticFilterOptions(["WH1", "WH2"], signal);
    const [path, options] = vi.mocked(backendRequest).mock.calls[0];
    const url = new URL(path, "http://localhost");
    expect(url.pathname).toBe("/api/pmc/domestic/inbound-batches/filter-options");
    expect(url.searchParams.getAll("warehouse_id")).toEqual(["WH1", "WH2"]);
    expect(options?.signal).toBe(signal);
  });
  it("explains authorization, migration/service and stale detail failures", () => {
    expect(domesticErrorText(new BackendRequestError(403, "FORBIDDEN"))).toContain("查看权限");
    expect(domesticErrorText(new BackendRequestError(500, "INTERNAL_ERROR"))).toContain("迁移");
    expect(domesticErrorText(new BackendRequestError(404, "NOT_FOUND"))).toContain("刷新列表");
  });
});
