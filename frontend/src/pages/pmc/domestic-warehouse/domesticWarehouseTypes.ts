/** Domestic batch API types preserve unknown values and receipt-line identity. */
import type { ReportFilterOption } from "@/shared/report-filters";

export interface DomesticFilterOptions { stores: ReportFilterOption[]; owners: ReportFilterOption[] }
export type MappingStatus = "matched" | "unresolved";
export type BatchSort = "received_date_desc" | "received_date_asc" | "qty_desc";
export type DomesticSearchType = "sku" | "inbound" | "purchase" | "receipt" | "item" | "gtin" | "msku" | "all";
export type DomesticBusinessStatus = "in_stock" | "pending_pack" | "packed" | "overdue" | "shipped" | "other_out";
export const domesticBusinessStatusOptions = [
  { value: "in_stock", label: "在库" },
  { value: "pending_pack", label: "待打包（领星打包单）" },
  { value: "packed", label: "已打包待发" },
  { value: "overdue", label: "超时未发" },
  { value: "shipped", label: "已发出" },
  { value: "other_out", label: "非发货出库" },
] satisfies { value: DomesticBusinessStatus; label: string }[];
export const domesticSearchOptions = [
  { value: "sku", label: "SKU" }, { value: "inbound", label: "入库单号" },
  { value: "purchase", label: "采购单号" }, { value: "receipt", label: "收货单号" },
  { value: "item", label: "ItemID（待接入）", disabled: true },
  { value: "gtin", label: "GTIN（待接入）", disabled: true },
  { value: "msku", label: "MSKU（待接入）", disabled: true },
  { value: "all", label: "综合搜索" },
];
export interface BatchLink {
  id: string; batch_order_sn: string | null; batch_no: string | null;
  store_id: string | null; mapped_qty: number | null; mapping_status: MappingStatus;
  mapping_method: string | null;
}
export interface DomesticBatch {
  id: string; source_account_ref: string; receipt_order_sn: string; line_ordinal: number;
  purchase_order_sn: string | null; source_warehouse_id: string | null; sku: string | null;
  received_qty: number | null; receive_time: string | null; received_business_date: string | null;
  days_in_warehouse: number | null; arrival_date_status: "known" | "unknown";
  mapping_status: MappingStatus; links: BatchLink[];
}
export interface DomesticMeta {
  source: string; source_objects: string[]; freshness_at: string | null;
  page?: number; page_size?: number; total?: number;
}
export interface DomesticSummary {
  receipt_batch_count: number; received_qty: number; warehouse_count: number;
  matched_batch_count: number; unresolved_batch_count: number;
  missing_arrival_date_count: number; as_of: string;
}
export interface DomesticTrace {
  batch: DomesticBatch;
  outbound: { status: "unknown"; reason: "source_not_published"; events: string[] };
}
export interface DomesticFilters {
  search: string; storeIds: string[]; warehouseIds: string[]; ownerUids?: string[];
  searchType?: DomesticSearchType; batchValues?: string[]; businessStatus?: DomesticBusinessStatus;
  mappingStatus?: MappingStatus; receivedFrom?: string; receivedTo?: string; sort: BatchSort;
}
export const initialDomesticFilters = (): DomesticFilters => ({
  search: "", searchType: "sku", storeIds: [], ownerUids: [], warehouseIds: [], sort: "received_date_desc",
});
export const domesticColumns = [
  { key: "arrival", title: "到仓日期", width: 128 },
  { key: "inbound", title: "入库单号", width: 160 },
  { key: "receipt", title: "收货单号", width: 160 },
  { key: "purchase", title: "采购单号", width: 160 },
  { key: "sku", title: "SKU", width: 140 },
  { key: "product", title: "产品", width: 150 },
  { key: "store", title: "店铺", width: 150 },
  { key: "item", title: "ItemID / MSKU", width: 155 },
  { key: "gtin", title: "GTIN", width: 140 },
  { key: "owner", title: "负责人", width: 100 },
  { key: "age", title: "在仓天数", width: 112 },
  { key: "note", title: "延迟备注", width: 140 },
  { key: "quantity", title: "实收数量", width: 112 },
  { key: "warehouse", title: "仓库 ID", width: 130 },
  { key: "mapping", title: "库存批次关联", width: 140 },
];
export const defaultColumnKeys = domesticColumns.map(({ key }) => key);
export const defaultColumnWidths = Object.fromEntries(domesticColumns.map(({ key, width }) => [key, width]));
export const formatQuantity = (value: number | null) => value === null ? "—" : value.toLocaleString("zh-CN");
