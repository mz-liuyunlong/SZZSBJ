/** Governed local packing API; no browser calls to provider endpoints. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { PackingApprovalFilters } from "./packingApprovalTypes";
export interface ApprovalCandidate {
  id: string; candidate_version: string; source_account_ref: string; warehouse_id: string;
  publication_id: string; board_id: string; inbound_order_sn: string; sku: string; product_name: string | null;
  store_id: string | null; store_name: string | null; item_id: string | null; gtin: string | null; msku: string | null;
  purchase_order_sns: string[]; arrival_purchased: number | null; arrival_received: number | null; arrival_pending: number | null;
  arrival_status: "unknown"; candidate_created_on: string | null; overdue: boolean | null;
  stock_balance: number | null; available_quantity: number | null; default_quantity: number | null;
  can_approve: boolean; blocked_reasons: string[]; source_observed_at: string;
}
export interface PackingOrder {
  id: string; candidate_id: string; pk: string | null; status: "approved" | "rejected"; qty: number | null;
  version: number; is_test: boolean; customs_value: boolean | null; customs_src: string; rwh: string | null;
  actor_uid: string; note: string | null; created_at: string; snapshot: ApprovalCandidate;
}
export interface PackingSummary { pending: number; overdue: number; blocked: number; approved: number; rejected: number }
export interface PackingEvent { id: string; event_kind: string; actor_uid: string; order_version: number; occurred_at: string; note: string | null }
export type DecisionKind = "approve" | "reject";
export interface DecisionPayload {
  source_account_ref: string; warehouse_id: string; candidate_version: string; idempotency_key: string;
  qty?: number; customs?: "default" | "declare" | "skip"; rwh?: string; is_test?: true; note?: string;
}
const prefix = "/api/pmc/domestic/packing-approval";
export function approvalQuery(filters: PackingApprovalFilters, page?: number, pageSize?: number) {
  const q = new URLSearchParams();
  filters.storeIds.forEach((v) => q.append("store_id", v));
  q.set("overdue", filters.overdue); q.set("arrival", filters.arrival); q.set("keyword", filters.search);
  if (filters.createdFrom) q.set("created_from", filters.createdFrom);
  if (filters.createdTo) q.set("created_to", filters.createdTo);
  if (page !== undefined) { q.set("page", String(page)); q.set("page_size", String(pageSize ?? 50)); q.set("sort", filters.sort); }
  return q;
}
export const listApprovalCandidates = (f: PackingApprovalFilters, page: number, size: number, signal?: AbortSignal) => backendRequest<{ items: ApprovalCandidate[]; total: number }>(`${prefix}/pending?${approvalQuery(f, page, size)}`, { signal });
export const getApprovalSummary = (f: PackingApprovalFilters, signal?: AbortSignal) => backendRequest<PackingSummary>(`${prefix}/pending/summary?${approvalQuery(f)}`, { signal });
export const getApprovalOptions = (signal?: AbortSignal) => backendRequest<{ stores: { value: string; label: string }[] }>(`${prefix}/filter-options`, { signal });
export const listPackingOrders = (f: PackingApprovalFilters, page: number, signal?: AbortSignal) => backendRequest<{ items: PackingOrder[]; total: number }>(`${prefix}/orders?${approvalQuery(f, page, 20)}`, { signal });
export const getPackingEvents = (id: string, signal?: AbortSignal) => backendRequest<{ items: PackingEvent[] }>(`${prefix}/orders/${encodeURIComponent(id)}/events`, { signal });
export const decidePacking = (id: string, kind: DecisionKind, body: DecisionPayload) => backendRequest<PackingOrder>(`${prefix}/pending/${encodeURIComponent(id)}/${kind}`, { method: "POST", body: JSON.stringify(body) });
const reasons: Record<string, string> = { STORE_UNKNOWN: "店铺归属未知", ELIGIBLE_LISTING_MISSING: "无符合条件的在线商品", GTIN_INVALID: "GTIN缺失或格式无效", MSKU_MISSING: "MSKU缺失", STOCK_PROOF_UNKNOWN: "良品或锁定量未知", STOCK_FULLY_ALLOCATED: "可用库存已分配完" };
export const approvalBlockedText = (codes: string[]) => codes.map((code) => reasons[code] ?? code).join("；");
export function approvalErrorText(error: unknown) {
  if (error instanceof BackendRequestError) {
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有审批权限、数据范围，或当前连接不允许本地审批";
    if (error.status === 409) return "审批状态、库存或来源已变化；请刷新后核对。重试不会重复生成打包单。";
    if (error.status === 422) return "请检查备货数量、驳回原因及筛选日期";
  }
  return "打包审批服务请求失败，请重试；未确认成功前请勿重复创建其他审批。";
}
