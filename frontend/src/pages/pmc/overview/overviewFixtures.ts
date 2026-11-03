/** Synthetic rows for overview tests only (no real data). */
import type { OverviewExportData, OverviewItemRow, OverviewSummary } from "@/pages/pmc/overview/overviewTypes";

export const syntheticRow = (over: Partial<OverviewItemRow> = {}): OverviewItemRow => ({
  item_id: "1001", sku: "SKU-A", msku: "SKU-A-M", name: "Synthetic A", owner: "Ann",
  stores: [{ id: "s1", name: "S1-Store", sales30: 30, available: 0, intransit: 0 }],
  listing: "PUBLISHED", tags: [], daily: 1, n30: 30, n_window: 30, oos_days: 3, no_stock_90: false,
  supply: 0, wm_available: 0, seg: { domestic: 5 }, dom_lock: 2, sellout: "2026-11-02", gap_days: null,
  resume: null, next_date: null, lead_total: 60, lead_p: 8, lead_avg: null, cycle_days: 14,
  suggest: 74, suggest_raw: 74, capped: false, box: 20, cover: null, over: null, stale: false,
  risk: false, oos: true, low_days: false, listing_bad: false, dom_over_qty: 0, dom_max: null,
  overseas_total: 0, overseas_alloc: 0, purchase: 74, boxed: 80, is_draft: true, draft_id: "D-1",
  draft_text: "已出草稿", issues: [{ label: "已断货", level: "red", detail: "断货 3 天" }],
  sc_flags: [], exec_flags: [], main: "已断货", level: "red", cats: ["已断货"], sort_cat: "已断货",
  ...over,
});

export const syntheticSummary: OverviewSummary = {
  data_date: "2026-11-02",
  source: "synthetic",
  source_note: "synthetic note；more",
  kpi: {
    items: 2, listing_bad: 0, oos: 1, risk: 0, over1: 0, over2: 0, stale: 0, supply_chain: 0,
    execution: 0, no_stock_90: 0, low_days: 0, overseas: 0, drafts: 1, normal: 1, low_supply: 1,
    overdue: 0, box_missing: 0,
  },
  params: { over1: 120, over2: 150, salesMinDays: 14, minQty: 50 },
  parity_with_8088: {},
  unattributed: [{ kind: "plan", why: "SKU 未上架任何在售 ItemID", qty: 4 }],
  overseas_total: 0,
};

export const syntheticExport: OverviewExportData = {
  data_date: "2026-11-02",
  source_note: "synthetic",
  params: { over1: 120, over2: 150 },
  store_summary: [{ store: "S1-Store", skus: 2, wm_available: 3 }],
  items: [syntheticRow()],
  ops_heads: ["SKU"],
  ops_rows: [["SKU-A"]],
  warehouses: [{ name: "WH", warehouse_class: "国内仓", valid: 1, lock: 0, total: 1, onway: 0, skus: 1, age_avg: 2, age_max: 3, age_bands: {} }],
};
