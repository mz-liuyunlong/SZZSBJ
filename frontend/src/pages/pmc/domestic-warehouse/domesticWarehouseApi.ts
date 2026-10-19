/** Only the existing read-only domestic contract is called; unsupported filters are never sent. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { DomesticBatch, DomesticFilters, DomesticFilterOptions, DomesticMeta, DomesticSummary, DomesticTrace } from "./domesticWarehouseTypes";

export function domesticFilterQuery(filters: DomesticFilters) {
  if (filters.businessStatus) throw new Error("DOMESTIC_BUSINESS_STATUS_NOT_SUPPORTED");
  const params = new URLSearchParams();
  filters.storeIds.forEach((id) => params.append("store_id", id));
  filters.ownerUids?.forEach((uid) => params.append("owner_uid", uid));
  filters.warehouseIds.forEach((id) => params.append("warehouse_id", id));
  const searchType = filters.searchType ?? "all";
  const values = filters.batchValues?.length ? [...new Set(filters.batchValues)] : filters.search.trim() ? [filters.search.trim()] : [];
  const exactField = ({ sku: "sku", purchase: "purchase_order_sn", receipt: "receipt_order_sn" } as Record<string, string>)[searchType];
  if (values.length > 50) throw new Error("DOMESTIC_BATCH_SEARCH_LIMIT");
  if (exactField) values.forEach((value) => params.append(exactField, value));
  else if (values.length) {
    if (!["all", "inbound"].includes(searchType) || values.length > 1) throw new Error("DOMESTIC_SEARCH_TYPE_NOT_SUPPORTED");
    // The existing generic search includes inbound numbers; it is not a field-exact inbound filter.
    params.set("search", values[0]);
  }
  if (filters.mappingStatus) params.set("mapping_status", filters.mappingStatus);
  if (filters.receivedFrom) params.set("received_from", filters.receivedFrom);
  if (filters.receivedTo) params.set("received_to", filters.receivedTo);
  return params;
}
export function getDomesticFilterOptions(signal?: AbortSignal) {
  return backendRequest<DomesticFilterOptions, DomesticMeta>("/api/pmc/domestic/filter-options", { signal });
}
export function listDomesticBatches(filters: DomesticFilters, page: number, pageSize: number, signal?: AbortSignal) {
  const params = domesticFilterQuery(filters);
  params.set("page", String(page)); params.set("page_size", String(pageSize)); params.set("sort", filters.sort);
  return backendRequest<{ items: DomesticBatch[]; total: number }, DomesticMeta>(
    `/api/pmc/domestic/batches?${params}`, { signal },
  );
}
export function getDomesticSummary(filters: DomesticFilters, signal?: AbortSignal) {
  return backendRequest<DomesticSummary, DomesticMeta>(
    `/api/pmc/domestic/batches/summary?${domesticFilterQuery(filters)}`, { signal },
  );
}
export function getDomesticTrace(id: string, signal?: AbortSignal) {
  return backendRequest<DomesticTrace, DomesticMeta>(`/api/pmc/domestic/batches/${encodeURIComponent(id)}/trace`, { signal });
}
export function domesticErrorText(error: unknown) {
  if (error instanceof BackendRequestError) {
    if (error.status === 403) return "没有国内仓批次的查看权限，请联系管理员配置权限与数据范围。";
    if (error.status === 404 || error.status === 503) return "国内仓数据服务尚未就绪，请稍后重试。";
    if (error.status === 422) return "筛选条件无效，请检查日期范围和输入内容。";
  }
  return "国内仓数据加载失败，请检查网络后重试。";
}
