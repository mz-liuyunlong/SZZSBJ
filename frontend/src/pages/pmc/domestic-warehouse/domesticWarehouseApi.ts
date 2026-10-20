/** Only the independent inbound contract is consumed by the batch board. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { DomesticBatch, DomesticFilterOptions, DomesticFilters, DomesticMeta, DomesticSummary, DomesticTrace } from "./domesticWarehouseTypes";

export function domesticFilterQuery(filters: DomesticFilters) {
  const params = new URLSearchParams();
  for (const [key, values] of [["owner_uid", filters.ownerUids ?? []], ["store_id", filters.storeIds], ["warehouse_id", filters.warehouseIds]] as const) {
    if (values.length > 50) throw new Error("DOMESTIC_BATCH_SEARCH_LIMIT");
    values.forEach((id) => params.append(key, id));
  }
  const values = filters.batchValues?.length ? [...new Set(filters.batchValues)] : filters.search.trim() ? [filters.search.trim()] : [];
  if (values.length > 50) throw new Error("DOMESTIC_BATCH_SEARCH_LIMIT");
  const exactField = { sku: "sku", purchase: "purchase_order_sn", inbound: "inbound_order_sn", all: "search" }[filters.searchType];
  if (!exactField || (filters.searchType === "all" && values.length > 1)) throw new Error("DOMESTIC_SEARCH_TYPE_NOT_SUPPORTED");
  values.forEach((value) => params.append(exactField, value));
  if (filters.inventoryStatus) params.set("inventory_status", filters.inventoryStatus);
  if (filters.inboundFrom) params.set("inbound_from", filters.inboundFrom);
  if (filters.inboundTo) params.set("inbound_to", filters.inboundTo);
  return params;
}
export function listDomesticBatches(filters: DomesticFilters, page: number, pageSize: number, signal?: AbortSignal) {
  const params = domesticFilterQuery(filters);
  params.set("page", String(page)); params.set("page_size", String(pageSize)); params.set("sort", filters.sort);
  return backendRequest<{ items: DomesticBatch[]; total: number }, DomesticMeta>(`/api/pmc/domestic/inbound-batches?${params}`, { signal });
}
export function getDomesticSummary(filters: DomesticFilters, signal?: AbortSignal) {
  return backendRequest<DomesticSummary, DomesticMeta>(`/api/pmc/domestic/inbound-batches/summary?${domesticFilterQuery(filters)}`, { signal });
}
export function getDomesticFilterOptions(warehouseIds: string[], signal?: AbortSignal) {
  const params = new URLSearchParams();
  warehouseIds.forEach((id) => params.append("warehouse_id", id));
  return backendRequest<DomesticFilterOptions, DomesticMeta>(`/api/pmc/domestic/inbound-batches/filter-options?${params}`, { signal });
}
export function getDomesticTrace(id: string, signal?: AbortSignal) {
  return backendRequest<DomesticTrace, DomesticMeta>(`/api/pmc/domestic/inbound-batches/${encodeURIComponent(id)}/trace`, { signal });
}
export function domesticErrorText(error: unknown) {
  if (error instanceof BackendRequestError) {
    if (error.status === 401) return "登录已失效，请重新登录。";
    if (error.status === 403) return "没有国内仓批次的查看权限，请联系管理员配置权限与数据范围。";
    if (error.status === 404) return "数据服务或当前批次不存在；若数据刚发布，请刷新列表后重试。";
    if (error.status === 422) return "筛选条件无效，请检查日期范围和输入内容。";
    if (error.status >= 500) return "入库数据服务暂不可用，请检查服务及数据库迁移状态后重试。";
  }
  return "国内仓数据加载失败，请检查网络后重试。";
}
