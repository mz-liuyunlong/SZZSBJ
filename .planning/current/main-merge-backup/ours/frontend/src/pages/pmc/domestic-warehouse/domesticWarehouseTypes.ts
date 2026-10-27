/** Procurement inbound grain; parent quantities must never be summed across store rows. */
export type BatchSort = "inbound_date_desc" | "inbound_date_asc" | "balance_desc";
export type InventoryStatus = "known" | "unknown";
export type DomesticSearchType = "sku" | "inbound" | "purchase" | "all";
export const domesticSearchOptions = [
  { value: "sku", label: "SKU" }, { value: "inbound", label: "入库单号" },
  { value: "purchase", label: "采购单号" }, { value: "all", label: "综合搜索" },
];
export interface BatchComponent {
  batch_no: string; store_id: string | null; balance_num: number | null;
  source_batch_nos: string[]; receipt_order_sns: string[];
}
export interface InboundEvent {
  statement_id: string | number | null; order_sn: string | null; sub_type: string | number | null;
  product_total: number | string | null; product_qc_num: number | string | null; opt_time: string | null;
}
export interface DomesticBatch {
  id: string; publication_id: string | null; source_account_ref: string; source_warehouse_id: string;
  warehouse_name: string | null; inbound_order_sn: string; sku: string; product_name: string;
  store_id: string | null; store_name: string | null; attribution_status: "known" | "unknown";
  purchase_order_sns: string[]; draft_nos?: string[]; inbound_at_raw: string | null; inbound_at: string | null;
  arrival_business_date: string | null; arrival_source: "inventory_statement" | "batch_fallback" | "unknown";
  arrival_date_status: "known" | "unknown"; days_in_warehouse: number | null;
  total_inbound_qty: number | null; parent_inbound_qty: number | null; quantity_scope: "inbound_sku" | "unknown";
  balance_num: number | null; inventory_status: InventoryStatus; batch_nos: string[];
  batch_details: BatchComponent[]; history_complete: boolean; source_kind: "inventory_statement" | "batch_backfill";
  /** Optional until identity enrichment is published; missing values stay explicit in the table. */
  item_identities?: { item_id: string; gtin: string | null }[];
  identity_status?: "resolved" | "missing" | "partial" | "conflict" | "multiple";
  owner?: { uid: string | null; name: string | null; status: "resolved" | "missing" | "conflict" };
}
export interface DomesticMeta {
  source: string; source_objects: string[]; freshness_at: string | null;
  data_status: "not_published" | "ready"; publication_ids: string[];
  coverage_start: string | null; coverage_end: string | null; as_of: string;
  page?: number; page_size?: number; total?: number;
}
export interface DomesticSummary {
  board_row_count: number; inbound_order_count: number; sku_count: number; balance_qty: number;
  unknown_inventory_row_count: number; total_inbound_qty: number; unknown_inbound_qty_count: number;
  missing_arrival_date_count: number; as_of: string;
}
export interface DomesticTrace {
  batch: DomesticBatch; inbound_events: InboundEvent[];
  outbound_status: "unknown"; outbound_reason: "source_not_published";
}
export interface DomesticFilterOption { value: string; label: string }
export interface DomesticFilterOptions {
  stores: DomesticFilterOption[]; owners: DomesticFilterOption[];
  statuses: (DomesticFilterOption & { disabled: boolean; reason: string })[];
  owner_basis: "current_product_owner";
}
export interface DomesticFilters {
  search: string; searchType: DomesticSearchType; batchValues?: string[];
  ownerUids: string[]; storeIds: string[]; warehouseIds: string[]; inventoryStatus?: InventoryStatus;
  inboundFrom?: string; inboundTo?: string; sort: BatchSort;
}
export const initialDomesticFilters = (): DomesticFilters => ({
  search: "", searchType: "sku", ownerUids: [], storeIds: [], warehouseIds: [], sort: "inbound_date_desc",
});
export const domesticColumns = [
  { key: "arrival", title: "到仓日期（入库）", width: 155 },
  { key: "draft", title: "草稿号", width: 160 },
  { key: "inbound", title: "入库单号", width: 170 }, { key: "sku", title: "SKU", width: 140 },
  { key: "product", title: "产品", width: 180 }, { key: "purchase", title: "采购单号", width: 170 },
  { key: "store", title: "店铺", width: 150 },
  { key: "item", title: "ItemID", width: 170 }, { key: "gtin", title: "GTIN", width: 180 },
  { key: "owner", title: "负责人", width: 130 },
  { key: "quantity", title: "入库总量（IB×SKU）", width: 175 },
  { key: "balance", title: "当前批次余额", width: 140 }, { key: "batches", title: "批次号", width: 180 },
  { key: "age", title: "在仓天数", width: 110 }, { key: "warehouse", title: "仓库", width: 150 },
  { key: "account", title: "来源账号", width: 150 }, { key: "inventory", title: "余额数据状态", width: 130 },
  { key: "source", title: "入库来源", width: 140 },
];
export const defaultColumnKeys = domesticColumns.map(({ key }) => key);
export const defaultColumnWidths = Object.fromEntries(domesticColumns.map(({ key, width }) => [key, width]));
export const formatQuantity = (value: number | null | undefined) => value == null ? "—" : value.toLocaleString("zh-CN");
export const arrivalSourceText = { inventory_statement: "库存流水", batch_fallback: "批次日期补充", unknown: "未知" };
