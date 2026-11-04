/**
 * PMC 总看板 contract types (`/api/pmc/overview/*`, PRP pmc-overview §5).
 *
 * Field names follow the backend contract verbatim (snake_case): the page is read-only and
 * every value is shown as delivered, so there is no client-side mapping layer to drift.
 */

export const OVERVIEW_CATEGORIES = [
  "Listing 异常",
  "已断货",
  "断货风险",
  "供应链异常",
  "执行异常",
  "库存过剩",
  "严重过剩",
  "滞销",
  "近 90 天无库存",
  "有库存不足 30 天",
  "海外仓可补",
  "超期未上架",
  "缺默认箱规",
] as const;
export type OverviewCategory = (typeof OVERVIEW_CATEGORIES)[number];

export const OVERVIEW_PAGE_SIZES = [50, 100, 200, 500] as const;
export type OverviewPageSize = (typeof OVERVIEW_PAGE_SIZES)[number];

export interface OverviewFilters {
  storeId?: string;
  owner?: string;
  cats: OverviewCategory[];
  keyword: string;
  onlyIssue: boolean;
}

export const createInitialOverviewFilters = (): OverviewFilters => ({
  storeId: undefined,
  owner: undefined,
  cats: [],
  keyword: "",
  onlyIssue: true,
});

export interface OverviewIssue {
  label: string;
  level: string;
  detail: string;
}

export interface OverviewStoreShare {
  id: string;
  name: string;
  sales30: number;
  available: number;
  intransit: number;
}

export interface OverviewItemRow {
  item_id: string;
  sku: string;
  msku: string;
  name: string;
  owner: string;
  stores: OverviewStoreShare[];
  listing: string;
  tags: string[];
  daily: number;
  n30: number;
  n_window: number | null;
  oos_days: number | null;
  no_stock_90: boolean;
  supply: number;
  wm_available: number;
  seg: Record<string, number>;
  dom_lock: number;
  sellout: string | null;
  gap_days: number | null;
  resume: string | null;
  next_date: string | null;
  lead_total: number;
  lead_p: number | null;
  lead_avg: number | null;
  cycle_days: number | null;
  suggest: number;
  suggest_raw: number;
  capped: boolean;
  box: number;
  cover: number | null;
  over: string | null;
  stale: boolean;
  risk: boolean;
  oos: boolean;
  low_days: boolean;
  listing_bad: boolean;
  dom_over_qty: number;
  dom_max: number | null;
  overseas_total: number;
  overseas_alloc: number;
  purchase: number;
  boxed: number | null;
  is_draft: boolean;
  draft_id: string;
  draft_text: string;
  issues: OverviewIssue[];
  sc_flags: OverviewIssue[];
  exec_flags: OverviewIssue[];
  main: string;
  level: string;
  cats: string[];
  sort_cat: string;
}

export interface OverviewBatch {
  kind: string;
  qty: number;
  date?: string;
  note?: string;
  overdue?: boolean;
  inspected?: boolean;
  store?: string;
}

export interface OverviewDomesticRow {
  batch: string;
  in_date?: string;
  age: number;
  qty: number;
}

export interface OverviewItemDetail extends OverviewItemRow {
  batches: OverviewBatch[];
  dom_rows: OverviewDomesticRow[];
  plans_recent: Record<string, unknown>[];
}

export interface OverviewKpi {
  items: number;
  listing_bad: number;
  oos: number;
  risk: number;
  over1: number;
  over2: number;
  stale: number;
  supply_chain: number;
  execution: number;
  no_stock_90: number;
  low_days: number;
  overseas: number;
  drafts: number;
  normal: number;
  low_supply: number;
  overdue: number;
  box_missing: number;
}

export interface OverviewUnattributed {
  kind: string;
  why: string;
  qty: number;
}

export interface OverviewSummary {
  data_date: string;
  source: string;
  source_note: string;
  kpi: OverviewKpi;
  params: Record<string, number>;
  parity_with_8088: Record<string, { demo: number; ours: number }>;
  unattributed: OverviewUnattributed[];
  overseas_total: number;
}

export interface OverviewFilterOptions {
  stores: { id: string; name: string }[];
  owners: string[];
  categories: string[];
}

export interface OverviewWarehouse {
  name: string;
  warehouse_class: string;
  valid: number;
  lock: number;
  total: number;
  onway: number;
  skus: number;
  age_avg: number | null;
  age_max: number | null;
  age_bands: Record<string, number>;
}

export interface OverviewWarehouseData {
  warehouses: OverviewWarehouse[];
  overseas_total: number;
}

export interface OverviewRules {
  rule_version: string;
  editable: boolean;
  params: { key: string; value: number }[];
}

export interface OverviewExportData {
  data_date: string;
  source_note: string;
  params: Record<string, number>;
  store_summary: Record<string, string | number>[];
  items: OverviewItemRow[];
  ops_heads: string[];
  ops_rows: (string | number | null)[][];
  warehouses: OverviewWarehouse[];
}

export interface OverviewReadMeta {
  source: string;
  source_objects: string[];
  data_date: string;
  rule_version: string;
  draft_mode: string;
  page?: number | null;
  page_size?: number | null;
  total?: number | null;
}

export interface OverviewItemPage {
  rows: OverviewItemRow[];
  total: number;
  meta?: OverviewReadMeta;
}
