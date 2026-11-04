import { backendDownload, backendRequest } from "@/api/backendApi";
import { pendingPrefix } from "./pendingPackingApi";
import type { PendingRow, ReturnAddress } from "./pendingPackingTypes";

export interface AllocationInput {
  order_id: string; expected_version: number; expected_box_version: number;
  additional_selections?: { order_id: string; expected_version: number; expected_box_version: number }[];
  shipping_boxes: number; shipment_count: number; shipment_boxes: number[];
}
export interface BoxRange {
  order_id: string; pk: string; sku: string; box_version: number;
  line_id: string; line_no: number; start: number; end: number; boxes: number;
  units_per_box: number; units: number; length_cm: string; width_cm: string;
  height_cm: string; gross_weight_kg: string;
}
export interface AllocationTicket { number: number; boxes: number; units: number; ranges: BoxRange[] }
export interface AllocationPreview {
  order_id: string; order_version: number; box_version: number;
  available_boxes: number; remaining_boxes: number; tickets: AllocationTicket[]; preview_hash: string;
}
export interface CreationInput extends AllocationInput {
  source_account_ref: string; preview_hash: string; idempotency_key: string;
  return_address: ReturnAddress; its: boolean; expected_delivery_at: string;
}
export type CreationState = "AWAITING_APPROVAL" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "UNKNOWN" | "PARTIAL";
export interface CreationOperation {
  id: string; order_id: string; state: CreationState; created_at: string;
  // Every Walmart write needs a written human approval; automatic checks are evidence only.
  approval_mode: "manual"; automatic_checks_at: string | null;
  approval_ref: string | null; approved_by: string | null; approved_at: string | null;
  tickets: { id: string; number: number; state: CreationState; allocation: AllocationTicket;
    error_code: string | null; shipments: { shipment_id: string; label_state: "PENDING" | "READY" | "FAILED" }[] }[];
}
export const creationLabels: Record<CreationState, string> = {
  AWAITING_APPROVAL: "待人工批准", QUEUED: "已批准待执行", RUNNING: "创建中", SUCCEEDED: "创建成功", FAILED: "创建失败", UNKNOWN: "结果待确认", PARTIAL: "部分成功",
};
export interface CreationCapabilities {
  creation_enabled: boolean; preview_enabled: boolean; reason: string | null;
  mode?: "off" | "probe" | "single" | "batch" | "simulator";
  /** 本机模拟通道（只在 APP_ENV=local）：页面显示横幅和「立即拉取结果」。 */
  simulator?: boolean;
}
export const getCreationCapabilities = (signal?: AbortSignal) => backendRequest<CreationCapabilities>(`${pendingPrefix}/capabilities`, { signal });
export const allocationPreview = (body: AllocationInput) => backendRequest<AllocationPreview>(`${pendingPrefix}/allocation-preview`, { method: "POST", body: JSON.stringify(body) });
export const createShipments = (body: CreationInput) => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations`, { method: "POST", body: JSON.stringify(body) });
export const listCreationOperations = (id: string, page = 1, signal?: AbortSignal) => backendRequest<{ items: CreationOperation[]; total: number }>(`${pendingPrefix}/creation-operations?order_id=${encodeURIComponent(id)}&page=${page}&page_size=10`, { signal });
export const approveCreation = (id: string, approvalRef: string) => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/approve`, { method: "POST", body: JSON.stringify({ approval_ref: approvalRef }) });
export const recoverCreation = (id: string, action: "reconcile" | "labels/retry") => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/${action}`, { method: "POST" });
export const optionalPreview = (body: CreationInput) => backendRequest<{ preview_hash: string; result: unknown }>(`${pendingPrefix}/optional-previews`, { method: "POST", body: JSON.stringify(body) });
export const downloadCreationLabel = (id: string, shipmentId: string) => backendDownload(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/labels/${encodeURIComponent(shipmentId)}`, "wfs-label.pdf");

/** 待创建货件页签（Rocky 2026-11-04）：一行一票（计划货件）。 */
export type TicketTab = "submitting" | "failed" | "created";
export interface TicketRow {
  operation_id: string; order_id: string; ticket_id: string; number: number; tab: TicketTab;
  /** 我方单号 = Walmart inboundOrderId = 领星入库订单编号（PMC-店铺码-日期-序号），提交后才有。 */
  inbound_order_id: string | null;
  state: CreationState; status_label: string; pks: string[]; skus: string[];
  store_id: string | null; store_name: string | null; source_account_ref: string;
  boxes: number; units: number; error_code: string | null; error_message: string | null;
  submissions: number; polls: number | null; max_polls: number | null; next_poll_at: string | null;
  shipments: { shipment_id: string; label_state: "PENDING" | "READY" | "FAILED"; fc: string | null }[];
  expected_delivery_at: string | null; created_at: string; created_by: string;
  approved_at: string | null; approved_by: string | null; approval_ref: string | null;
  awaiting_approval: boolean;
}
export type TicketCounts = Record<TicketTab, number>;
export interface TicketFilters { store_id?: string; keyword: string }
const ticketQuery = (f: TicketFilters) => {
  const p = new URLSearchParams();
  if (f.store_id) p.set("store_id", f.store_id);
  if (f.keyword) p.set("keyword", f.keyword);
  return p;
};
export const listCreationTickets = (tab: TicketTab, f: TicketFilters, page: number, size: number, signal?: AbortSignal) => {
  const p = ticketQuery(f); p.set("tab", tab); p.set("page", String(page)); p.set("page_size", String(size));
  return backendRequest<{ items: TicketRow[]; total: number }>(`${pendingPrefix}/creation-tickets?${p}`, { signal });
};
export const getTicketCounts = (f: TicketFilters, signal?: AbortSignal) => backendRequest<TicketCounts>(`${pendingPrefix}/creation-ticket-counts?${ticketQuery(f)}`, { signal });
export const retryCreation = (id: string) => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/retry`, { method: "POST" });

/** 创建默认值：本店铺 → 全部店铺通用（store_id = "*"）→ 8088 默认值。 */
export const COMMON_STORE = "*";
export type Transport = "LTL" | "SMALL_PARCEL" | "FTL";
export interface DefaultValues {
  transport: Transport; ship_date_offset: number; pallet_boxes: number; mixed_boxes: number;
  carrier_opt: "own" | "wm"; its: boolean; return_address: ReturnAddress | null;
}
export interface StoreDefaultsRow extends DefaultValues {
  store_id: string; store_name: string | null; source_account_ref: string;
  level: "store" | "common" | "account" | "default"; updated_by: string | null; updated_at: string | null;
}
export interface CreationDefaults extends DefaultValues {
  source_account_ref: string; store_id: string | null; level: StoreDefaultsRow["level"];
  saved: boolean; expected_delivery_date: string;
}
export const listStoreDefaults = (signal?: AbortSignal) => backendRequest<{ common: StoreDefaultsRow[]; items: StoreDefaultsRow[] }>(`${pendingPrefix}/store-creation-defaults`, { signal });
export const saveStoreDefaults = (storeId: string, body: DefaultValues & { reason?: string; source_account_ref?: string }) => backendRequest<StoreDefaultsRow>(`${pendingPrefix}/store-creation-defaults/${encodeURIComponent(storeId)}`, { method: "PUT", body: JSON.stringify(body) });
export const getCreationDefaults = (account: string, storeId: string | null | undefined, signal?: AbortSignal) => {
  const p = new URLSearchParams({ source_account_ref: account });
  if (storeId) p.set("store_id", storeId);
  return backendRequest<CreationDefaults>(`${pendingPrefix}/creation-defaults?${p}`, { signal });
};

/** 单列表（Rocky 2026-11-04 第 12–16 条 + 拆票）：一行 = 一个打包单 × 一个货件，状态在行上。 */
/** Rocky 2026-11-04 取消「待批准」：「确认创建」直接发出，5 种状态。 */
export type RowStatus = "pending" | "submitting" | "failed" | "created" | "shipped";
export const ROW_STATUSES: RowStatus[] = ["pending", "submitting", "failed", "created", "shipped"];
export const DEFAULT_STATUSES: RowStatus[] = ROW_STATUSES.slice(0, 4);
export const statusText: Record<RowStatus, string> = {
  pending: "待创建", submitting: "提交中", failed: "创建失败", created: "已创建未发货", shipped: "已发货",
};
export interface BoardRow {
  key: string; kind: "pending" | "shipment"; status: RowStatus; status_label: string; detail: string | null;
  sort_at: string | null; order_id: string; pk: string; store_id: string | null; store_name: string | null;
  sku: string | null; product_name: string | null; item_id: string | null; gtin: string | null; business_test: boolean;
  pending: PendingRow | null; ticket: TicketRow | null;
  shipment_id: string | null; fc: string | null; label_state: "PENDING" | "READY" | "FAILED" | null;
  print_count: number; printed_at: string | null; printed_by: string | null;
  /** 领星 SP 发货单号：有就代表已发货（几票可以共用一张）。 */
  shipping_code: string | null; demo: boolean;
}
export type BoardRowCounts = Record<RowStatus, number>;
export interface BoardRowFilters {
  store_id?: string; keyword: string; only_test: boolean; completed_from?: string; completed_to?: string;
  statuses: RowStatus[]; show_shipped: boolean;
}
export const listBoardRows = (f: BoardRowFilters, page: number, size: number, signal?: AbortSignal) => {
  const p = new URLSearchParams();
  if (f.store_id) p.set("store_id", f.store_id);
  if (f.keyword) p.set("keyword", f.keyword);
  if (f.only_test) p.set("only_test", "true");
  if (f.completed_from) p.set("completed_from", f.completed_from);
  if (f.completed_to) p.set("completed_to", f.completed_to);
  f.statuses.forEach((s) => p.append("status", s));
  if (f.show_shipped) p.set("show_shipped", "true");
  p.set("page", String(page)); p.set("page_size", String(size));
  return backendRequest<{ items: BoardRow[]; total: number; counts: BoardRowCounts }>(`${pendingPrefix}/rows?${p}`, { signal });
};
/** 「打印箱唛」：下载 PDF，后端同时记一次打印（已打印 x 次）。 */
export const printCreationLabel = (id: string, shipmentId: string) => backendDownload(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/labels/${encodeURIComponent(shipmentId)}/print`, "wfs-label.pdf", { method: "POST" });
/** 只在本机模拟模式存在（别处 404）：代替本机没有的 3 分钟定时，立即跑一次「WFS 创建结果拉取」。 */
export const simulatorPull = () => backendRequest<{ run_ids: string[] }>(`${pendingPrefix}/simulator/pull`, { method: "POST" });
