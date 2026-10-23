/** Authenticated same-origin requests only; never falls back to WFS sample rows. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { DraftCommand, DraftRead, IdentityChoice, IdentityFields, PendingFilters, PendingRow, PendingSummary } from "./pendingPackingTypes";
export const pendingPrefix = "/api/pmc/wfs/pending-packing";
const query = (f: PendingFilters) => new URLSearchParams({ keyword: f.keyword, only_test: String(f.only_test), ...(f.store_id ? { store_id: f.store_id } : {}) });
export const listPending = (f: PendingFilters, page: number, size: number, signal?: AbortSignal) => backendRequest<{ items: PendingRow[]; total: number }>(`${pendingPrefix}/orders?${query(f)}&page=${page}&page_size=${size}`, { signal });
export const pendingSummary = (f: PendingFilters, signal?: AbortSignal) => backendRequest<PendingSummary>(`${pendingPrefix}/summary?${query(f)}`, { signal });
export const pendingOptions = (signal?: AbortSignal) => backendRequest<{ stores: { value: string; label: string }[] }>(`${pendingPrefix}/filter-options`, { signal });
export const getPending = (id: string, signal?: AbortSignal) => backendRequest<PendingRow>(`${pendingPrefix}/orders/${encodeURIComponent(id)}`, { signal });
export const identityOptions = (id: string, signal?: AbortSignal) => backendRequest<{ listings: IdentityChoice[] }>(`${pendingPrefix}/orders/${encodeURIComponent(id)}/identity-options`, { signal });
export const submitDrafts = (body: DraftCommand) => backendRequest<{ drafts: DraftRead[] }>(`${pendingPrefix}/drafts`, { method: "POST", body: JSON.stringify(body) });
export const switchIdentity = (row: PendingRow, fields: IdentityFields, key: string) => backendRequest<PendingRow>(`${pendingPrefix}/orders/${row.order.id}/identity`, { method: "POST", body: JSON.stringify({ ...fields, source_account_ref: row.order.source_account_ref, expected_version: row.order.version, expected_box_version: row.order.box_set!.version, idempotency_key: key }) });
export function pendingError(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有操作权限、来源账号或店铺数据权限";
    if (error.status === 404) return "单据已变化或不在当前权限范围，请刷新";
    if (error.status === 409) return "单据版本、装箱占用或商品身份已变化，请刷新核对";
    if (error.status === 422) return "请检查退货地址、装箱选择及必填原因";
  }
  return "待发货服务请求失败，请重试；本页不会使用示例数据替代";
}
