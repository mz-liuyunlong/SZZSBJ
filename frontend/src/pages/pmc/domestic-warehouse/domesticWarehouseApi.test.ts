/** Contract tests guard against unsupported query fields and accidental date fallbacks. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import { domesticErrorText, domesticFilterQuery, getDomesticFilterOptions, getDomesticSummary, getDomesticTrace, listDomesticBatches } from "./domesticWarehouseApi";
import { initialDomesticFilters } from "./domesticWarehouseTypes";
vi.mock("@/api/backendApi", async (original) => ({
  ...await original<typeof import("@/api/backendApi")>(), backendRequest: vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());
describe("domestic receipt contract", () => {
  it("loads scoped options and submits stable owner UIDs with identical list/summary filters", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ success: true, error: null, meta: {},
      request_id: "synthetic-options-test", data: { stores: [], owners: [] } });
    const signal = new AbortController().signal;
    await getDomesticFilterOptions(signal);
    expect(backendRequest).toHaveBeenCalledWith("/api/pmc/domestic/filter-options", { signal });
    const filters = { ...initialDomesticFilters(), storeIds: ["001"], ownerUids: ["0002", "0003"] };
    await listDomesticBatches(filters, 1, 50);
    await getDomesticSummary(filters);
    for (const [path] of vi.mocked(backendRequest).mock.calls.slice(1)) {
      const params = new URL(path, "http://localhost").searchParams;
      expect(params.getAll("owner_uid")).toEqual(["0002", "0003"]);
      expect(params.getAll("store_id")).toEqual(["001"]);
    }
  });
  it("serializes repeated IDs and receipt-date filters without inventing unsupported fields", () => {
    const query = domesticFilterQuery({ ...initialDomesticFilters(), warehouseIds: ["W1", "W2"],
      storeIds: ["001"], search: " SKU-A ", mappingStatus: "unresolved",
      receivedFrom: "2026-10-01", receivedTo: "2026-10-19" });
    expect(query.getAll("warehouse_id")).toEqual(["W1", "W2"]);
    expect(query.getAll("store_id")).toEqual(["001"]);
    expect(query.get("received_from")).toBe("2026-10-01");
    expect(query.get("received_to")).toBe("2026-10-19");
    expect(query.getAll("sku")).toEqual(["SKU-A"]);
    expect(query.has("search")).toBe(false);
    expect([...query.keys()].some((key) => /owner|item_id|order_date|search_type/.test(key))).toBe(false);
  });
  it("uses exact multi-value purchase/receipt filters and rejects unsupported business states", () => {
    const purchase = domesticFilterQuery({ ...initialDomesticFilters(), searchType: "purchase", batchValues: ["PO-1", "PO-2", "PO-1"] });
    expect(purchase.getAll("purchase_order_sn")).toEqual(["PO-1", "PO-2"]);
    expect(domesticFilterQuery({ ...initialDomesticFilters(), searchType: "receipt", search: "RCPT-1" }).get("receipt_order_sn")).toBe("RCPT-1");
    expect(() => domesticFilterQuery({ ...initialDomesticFilters(), businessStatus: "packed" })).toThrow("DOMESTIC_BUSINESS_STATUS_NOT_SUPPORTED");
    expect(() => domesticFilterQuery({ ...initialDomesticFilters(), searchType: "inbound", batchValues: ["IB-1", "IB-2"] })).toThrow("DOMESTIC_SEARCH_TYPE_NOT_SUPPORTED");
    expect(() => domesticFilterQuery({ ...initialDomesticFilters(), batchValues: Array.from({ length: 51 }, (_, i) => String(i)) })).toThrow("DOMESTIC_BATCH_SEARCH_LIMIT");
  });
  it("uses server pagination and leaves null dates and zero quantities untouched", async () => {
    const response = { success: true, error: null, request_id: "synthetic-test", data: { items: [{ received_business_date: null, received_qty: 0 }], total: 51 }, meta: {} };
    vi.mocked(backendRequest).mockResolvedValue(response);
    const signal = new AbortController().signal;
    const result = await listDomesticBatches({ ...initialDomesticFilters(), sort: "qty_desc" }, 2, 50, signal);
    const path = vi.mocked(backendRequest).mock.calls[0][0];
    const url = new URL(path, "http://localhost");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("50");
    expect(url.searchParams.get("sort")).toBe("qty_desc");
    expect(backendRequest).toHaveBeenCalledWith(path, { signal });
    expect(result).toBe(response);
  });
  it("does not send paging or sorting into strict summary filters", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ success: true, error: null, request_id: "synthetic-test", data: {}, meta: {} });
    await getDomesticSummary(initialDomesticFilters());
    const url = new URL(vi.mocked(backendRequest).mock.calls[0][0], "http://localhost");
    expect(url.pathname).toBe("/api/pmc/domestic/batches/summary");
    expect(url.searchParams.has("sort")).toBe(false);
    expect(url.searchParams.has("page")).toBe(false);
  });
  it("uses encoded trace identifiers and explains unavailable or forbidden sources", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ success: true, error: null, request_id: "synthetic-test", data: {}, meta: {} });
    await getDomesticTrace("batch/1");
    expect(backendRequest).toHaveBeenCalledWith("/api/pmc/domestic/batches/batch%2F1/trace", { signal: undefined });
    expect(domesticErrorText(new BackendRequestError(403, "FORBIDDEN"))).toContain("查看权限");
    expect(domesticErrorText(new BackendRequestError(503, "UNAVAILABLE"))).toContain("尚未就绪");
  });
});
