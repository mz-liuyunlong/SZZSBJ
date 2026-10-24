/** All warehouse business requests use the authenticated new-system backend. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { PackingWarehouseFilters, PackingWarehouseRow, WarehouseAction, WarehouseBase, WarehouseEvent, WarehouseFields } from "./packingWarehouseTypes";
export const warehousePrefix = "/api/pmc/domestic/packing-warehouse";
export function warehouseQuery(filters: PackingWarehouseFilters, page?: number, size?: number) {
  const q = new URLSearchParams({ status: filters.status, keyword: filters.search });
  if (filters.exception) q.set("exception", filters.exception);
  if (filters.storeId) q.set("store_id", filters.storeId);
  if (filters.approvedFrom) q.set("approved_from", filters.approvedFrom);
  if (filters.approvedTo) q.set("approved_to", filters.approvedTo);
  if (page !== undefined) { q.set("page", String(page)); q.set("page_size", String(size ?? 50)); q.set("sort", filters.sort === "approved_asc" ? "approved_asc" : "approved_desc"); }
  return q;
}
export const listWarehouseOrders = (f: PackingWarehouseFilters, page: number, size: number, signal?: AbortSignal) => backendRequest<{ items: PackingWarehouseRow[]; total: number }>(`${warehousePrefix}/orders?${warehouseQuery(f, page, size)}`, { signal });
export const getWarehouseSummary = (f: PackingWarehouseFilters, signal?: AbortSignal) => backendRequest<{ todo: number; packed: number; overpack_blocked?: number; unpacked_pending?: number }>(`${warehousePrefix}/orders/summary?${warehouseQuery(f)}`, { signal });
export const getWarehouseOptions = (signal?: AbortSignal) => backendRequest<{ stores: { value: string; label: string }[] }>(`${warehousePrefix}/filter-options`, { signal });
export const getWarehouseOrder = (id: string, signal?: AbortSignal) => backendRequest<PackingWarehouseRow>(`${warehousePrefix}/orders/${encodeURIComponent(id)}`, { signal });
export const getWarehouseEvents = (id: string, page: number, signal?: AbortSignal) => backendRequest<{ items: WarehouseEvent[]; total: number }>(`${warehousePrefix}/orders/${encodeURIComponent(id)}/events?page=${page}&page_size=20`, { signal });
export const writeWarehouseOrder = (id: string, action: WarehouseAction, body: WarehouseBase & WarehouseFields) => backendRequest<PackingWarehouseRow>(`${warehousePrefix}/orders/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify(body) });
const reasons: Record<string, string> = { ALREADY_COMPLETED: "已完成，不可再次操作", BOXES_REQUIRED: "请先保存装箱", UNDERPACK_REASON_REQUIRED: "请选择少装原因；其他原因须填写说明", EXTRA_STOCK_RULE_UNCONFIRMED: "超量余量口径待确认，暂不允许完成", NO_PENDING_UNPACKED: "没有待处置的未装数量", PACKAGE_REQUIRED: "请先补填单品包装尺寸和毛重", PRODUCT_REQUIREMENT_CHANGED: "产品包装资料已更新，请刷新核对", ORDER_VERSION_CHANGED: "订单已被修改，请刷新", BOX_VERSION_CHANGED: "装箱版本已更新，请刷新", OVERPACK_NOT_ALLOWED: "装箱合计不能超过审批数量", VARIANCE_REASON_REQUIRED: "少装暂存须填写至少2字原因", NO_CHANGE: "内容没有变化", NO_ACTIVE_NOTE: "当前没有待处理的延迟备注", IDEMPOTENCY_KEY_REUSED: "该请求编号已用于其他操作，请重新核对" };
export const warehouseReason = (reason: string) => reasons[reason] ?? reason;
export function warehouseError(error: unknown) {
  if (error instanceof BackendRequestError) {
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有该操作权限、账号范围，或当前不在允许的本地环境";
    if (error.status === 409) return "状态、版本或数量已变化，请刷新核对后重试";
    if (error.status === 422) return "请检查箱数、件数、尺寸、重量和必填原因";
  }
  return "仓库打包服务请求失败，请重试；未确认成功前不要重复发起其他请求";
}

export function warehouseSyncLabel(code?: string | null): string {
  const labels: Record<string, string> = { NOT_SYNCED: "已登记，尚未同步", LINGXING_SYNC_NOT_CONFIGURED: "领星同步未配置", LINGXING_SYNC_FAILED: "同步失败，请重试", SYNC_EVIDENCE_INVALID: "同步证据无效", SYNC_SCOPE_MISMATCH: "同步账号或仓库不匹配", SYNC_EVIDENCE_STALE: "同步数据不是补单后的新快照", IB_SKU_WAREHOUSE_MISMATCH: "未找到匹配的入库单、SKU及仓库", IB_QUANTITY_UNKNOWN: "入库数量无法核实", IB_QUANTITY_INSUFFICIENT: "补入库数量不足", STOCK_STILL_INSUFFICIENT: "最新可用余量仍不足", STOCK_PROOF_UNKNOWN: "库存证据不足", MATCHED: "校验通过，请仓库再次确认完成" };
  return code ? labels[code] ?? "待核实" : "尚未同步";
}
