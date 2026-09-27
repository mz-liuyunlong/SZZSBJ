import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildPurchaseBoardListQuery,
  getPurchaseBoardSummary,
  getPurchaseOrderDetail,
  listPurchaseBoard,
  normalizeSearchValues,
} from "@/pages/pmc/purchase-board/purchaseBoardApi";
import { createInitialPurchaseBoardFilters } from "@/pages/pmc/purchase-board/purchaseBoardTypes";

const envelope = (data: unknown, meta: Record<string, unknown> = {}) => ({
  ok: true,
  status: 200,
  url: "",
  headers: new Headers({ "content-type": "application/json" }),
  json: async () => ({ success: true, data, error: null, meta, request_id: "req-1" }),
  text: async () => "",
});

const backendRow = {
  purchase_order_sn: "PO1",
  order_item_id: "L1",
  plan_sn: "P1",
  plan_sns: ["P1"],
  order_status: 2,
  stage: {
    stage_code: "S3",
    stage_start: "2026-09-01",
    stage_start_estimated: false,
    threshold_days: 12,
    due_date: "2026-09-13",
    overdue_days: 10,
    overdue_kind: "arrival",
    alert_due_since: "2026-09-14",
  },
  store: { id: "110652398125259264", name: "Store A", attributed: true },
  sku: "SKU-A",
  product_name: "Widget",
  item_id: {
    item_id: "19051502014",
    source: "from_plan_remark",
    source_ref: "P1",
    matched_at: "2026-09-23T03:00:00Z",
    match_status: "matched",
    msku: "MSKU-A",
    gtin: "00012345678905",
    fulfillment_type: "1",
    wfs_not_ready: false,
  },
  owner: { uid: "u-1", name: "Owner One" },
  quantity_total: 100,
  quantity_allocated: 100,
  quantity_received: 0,
  progress_ratio: "0",
  remaining_quantity: 100,
  order_date: "2026-09-01",
  order_create_date: "2026-08-31",
  plan_create_date: "2026-08-29",
  arrival_date: null,
  arrival_receipt_order_sn: null,
  purchase_cycle_days: null,
  approval_cycle_days: 2,
  sku_cycle: { value_days: "12.0000", source: "samples", sample_count: 5, unstable: true },
  unit_price: "5.0000",
  amount_allocated: "500.0000",
  amount_total: "500.0000",
  currency_code: "CNY",
  calculated_at: "2026-09-23T03:00:00Z",
};

describe("purchaseBoardApi query building", () => {
  it("sends list filters as repeated keys and splits batch values like the backend", () => {
    const query = buildPurchaseBoardListQuery(
      {
        ...createInitialPurchaseBoardFilters(),
        ownerUids: ["u-1", "u-2"],
        statuses: ["s3", "overdue"],
        searchType: "sku",
        keyword: "",
        batchValues: ["SKU-A, SKU-B", " SKU-A ", "SKU-C\nSKU-D"],
        orderDateFrom: "2026-09-01",
        orderDateTo: "2026-09-24",
        itemIdSources: ["unresolved"],
        qtyMin: 10,
        priceMax: "5.5",
        wfsNotReady: true,
        todayFollowup: true,
        sort: "amount_desc",
      },
      2,
      100,
    );
    expect(query.getAll("owner_uid")).toEqual(["u-1", "u-2"]);
    expect(query.getAll("status")).toEqual(["s3", "overdue"]);
    expect(query.get("search_type")).toBe("sku");
    expect(query.getAll("search_values")).toEqual(["SKU-A", "SKU-B", "SKU-C", "SKU-D"]);
    expect(query.get("order_date_from")).toBe("2026-09-01");
    expect(query.get("order_date_to")).toBe("2026-09-24");
    expect(query.getAll("item_id_source")).toEqual(["unresolved"]);
    expect(query.get("qty_min")).toBe("10");
    expect(query.has("qty_max")).toBe(false);
    expect(query.get("price_max")).toBe("5.5");
    expect(query.get("wfs_not_ready")).toBe("true");
    expect(query.get("today_followup")).toBe("true");
    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("100");
    expect(query.get("sort")).toBe("amount_desc");
  });

  it("omits search_type when there is nothing to search and never sends unknown keys", () => {
    const query = buildPurchaseBoardListQuery(createInitialPurchaseBoardFilters(), 1, 50);
    expect([...query.keys()].sort()).toEqual(["page", "page_size", "sort"]);
  });

  it("normalises comma / whitespace separated values and drops duplicates", () => {
    expect(normalizeSearchValues(["a,b", "b c", "", "  "])).toEqual(["a", "b", "c"]);
  });
});

describe("purchaseBoardApi mapping", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("maps board rows, decimal strings and envelope meta", async () => {
    fetchMock.mockResolvedValue(envelope(
      { items: [backendRow], total: 1 },
      { source: "new_system_postgresql", source_objects: ["dws_purchase_board"], freshness_at: "2026-09-23T03:00:00Z", rule_version: 1, total: 1 },
    ));
    const result = await listPurchaseBoard(createInitialPurchaseBoardFilters(), 1, 50);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/pmc/purchase/board?page=1&page_size=50&sort=order_date_desc");
    expect(result.total).toBe(1);
    expect(result.meta).toEqual({ freshnessAt: "2026-09-23T03:00:00Z", ruleVersion: 1, total: 1 });
    const row = result.rows[0];
    expect(row.id).toBe("PO1::L1::P1");
    expect(row.stage.overdueKind).toBe("arrival");
    expect(row.itemId.itemId).toBe("19051502014");
    expect(row.skuCycle).toEqual({ valueDays: 12, source: "samples", sampleCount: 5, unstable: true });
    expect(row.unitPrice).toBe(5);
    expect(row.amountAllocated).toBe(500);
    expect(row.progressRatio).toBe(0);
    expect(row.arrivalDate).toBeNull();
  });

  it("maps the summary cards including per-currency month amounts", async () => {
    fetchMock.mockResolvedValue(envelope({
      awaiting_arrival_orders: 3,
      arrival_overdue_orders: 1,
      purchase_overdue_orders: 0,
      purchase_overdue_plans: 2,
      average_purchase_cycle_days_90d: "11.5000",
      month_purchase_amount: [{ currency_code: "CNY", amount: "1234.5000" }],
      unstable_sku_count: 1,
      itemid_pending_lines: 4,
      wfs_not_ready_lines: 0,
      unattributed_store_lines: 2,
      as_of: "2026-09-24",
    }));
    const summary = await getPurchaseBoardSummary({ ...createInitialPurchaseBoardFilters(), statuses: ["s2"] });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/pmc/purchase/board/summary?status=s2");
    expect(summary.averagePurchaseCycleDays90d).toBe(11.5);
    expect(summary.monthPurchaseAmount).toEqual([{ currencyCode: "CNY", amount: 1234.5 }]);
    expect(summary.purchaseOverduePlans).toBe(2);
    expect(summary.asOf).toBe("2026-09-24");
  });

  it("maps the order detail and encodes the order number in the path", async () => {
    fetchMock.mockResolvedValue(envelope({
      purchase_order_sn: "PO 1",
      order_status: 2,
      order_date: "2026-09-01",
      order_create_date: "2026-08-31",
      quantity_total: 100,
      quantity_received: 50,
      progress_ratio: "0.5",
      arrival_date: null,
      amount_total: "500.0000",
      currency_code: "CNY",
      stage: backendRow.stage,
      lines: [backendRow],
      receipts: [{ receipt_order_sn: "R1", is_arrival_receipt: true }],
      plans: [{ plan_sn: "P1", plan_status: 3, plan_create_date: "2026-08-29", quantity_plan: 100, remark_item_id: "19051502014", store_id: "110652398125259264" }],
      sku_cycles: [{
        sku: "SKU-A",
        value_days: "12.0000",
        source: "samples",
        sample_count: 1,
        baseline_days: null,
        baseline_set_on: null,
        lingxing_default_days: 12,
        unstable: false,
        range_days: 0,
        samples: [{ purchase_order_sn: "PO0", order_date: "2026-08-01", arrival_date: "2026-08-13", cycle_days: 12, used: true, exclusion: null }],
        rule_version: 1,
        calculated_at: "2026-09-23T03:00:00Z",
      }],
    }));
    const detail = await getPurchaseOrderDetail("PO 1");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/pmc/purchase/orders/PO%201");
    expect(detail.progressRatio).toBe(0.5);
    expect(detail.receipts[0]).toEqual({ receiptOrderSn: "R1", isArrivalReceipt: true });
    expect(detail.plans[0].remarkItemId).toBe("19051502014");
    expect(detail.skuCycles[0].samples[0].purchaseOrderSn).toBe("PO0");
    expect(detail.lines[0].id).toBe("PO1::L1::P1");
  });
});
