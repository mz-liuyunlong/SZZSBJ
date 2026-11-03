/** Requests for the PMC 总看板; every call goes through `backendRequest` (read-only contract). */
import { backendRequest } from "@/api/backendApi";
import type {
  OverviewExportData,
  OverviewFilterOptions,
  OverviewFilters,
  OverviewItemDetail,
  OverviewItemPage,
  OverviewReadMeta,
  OverviewRules,
  OverviewSummary,
  OverviewWarehouseData,
} from "@/pages/pmc/overview/overviewTypes";

const BASE = "/api/pmc/overview";

export function buildOverviewFilterQuery(filters: OverviewFilters) {
  const query = new URLSearchParams();
  if (filters.storeId) query.set("store_id", filters.storeId);
  if (filters.owner) query.set("owner", filters.owner);
  for (const cat of filters.cats) query.append("cats", cat);
  const keyword = filters.keyword.trim();
  if (keyword) query.set("keyword", keyword);
  query.set("only_issue", String(filters.onlyIssue));
  return query;
}

export async function getOverviewSummary(signal?: AbortSignal): Promise<OverviewSummary> {
  return (await backendRequest<OverviewSummary, OverviewReadMeta>(`${BASE}/summary`, { signal })).data;
}

export async function listOverviewItems(
  filters: OverviewFilters,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<OverviewItemPage> {
  const query = buildOverviewFilterQuery(filters);
  query.set("page", String(page));
  query.set("page_size", String(pageSize));
  const response = await backendRequest<{ items: OverviewItemPage["rows"] }, OverviewReadMeta>(
    `${BASE}/items?${query.toString()}`,
    { signal },
  );
  return { rows: response.data.items, total: response.meta?.total ?? 0, meta: response.meta };
}

export async function getOverviewItem(itemId: string, signal?: AbortSignal): Promise<OverviewItemDetail> {
  return (
    await backendRequest<OverviewItemDetail, OverviewReadMeta>(
      `${BASE}/items/${encodeURIComponent(itemId)}`,
      { signal },
    )
  ).data;
}

export async function getOverviewFilterOptions(signal?: AbortSignal): Promise<OverviewFilterOptions> {
  return (await backendRequest<OverviewFilterOptions, OverviewReadMeta>(`${BASE}/filter-options`, { signal })).data;
}

export async function getOverviewWarehouses(signal?: AbortSignal): Promise<OverviewWarehouseData> {
  return (await backendRequest<OverviewWarehouseData, OverviewReadMeta>(`${BASE}/warehouses`, { signal })).data;
}

export async function getOverviewRules(signal?: AbortSignal): Promise<OverviewRules> {
  return (await backendRequest<OverviewRules, OverviewReadMeta>(`${BASE}/rules`, { signal })).data;
}

/** `filters` undefined = all ItemIDs (8088 「下载全部」). */
export async function getOverviewExport(filters?: OverviewFilters): Promise<OverviewExportData> {
  const query = filters ? buildOverviewFilterQuery(filters) : new URLSearchParams({ only_issue: "false" });
  return (
    await backendRequest<OverviewExportData, OverviewReadMeta>(`${BASE}/export?${query.toString()}`)
  ).data;
}

export function overviewErrorText(reason: unknown) {
  const error = reason as { status?: number; code?: string; message?: string } | undefined;
  const code = error?.code ?? error?.message ?? "";
  if (error?.status === 401 || code === "UNAUTHORIZED") return "当前账号未登录或授权已过期，请重新登录后查看总看板。";
  if (code === "DATA_SCOPE_DENIED") return "当前账号没有可访问的数据范围，请联系管理员配置账号范围。";
  if (error?.status === 403 || code === "FORBIDDEN") return "当前账号没有总看板查看权限（pmc:overview:read）。";
  if (error?.status === 503 || code === "PMC_OVERVIEW_NOT_READY") return "总看板数据未就绪：本机还没有放入 8088 数据日快照文件。";
  if (error?.status === 404 || code === "NOT_FOUND") return "未找到该 ItemID。";
  if (error?.status === 422 || code === "VALIDATION_ERROR") return "筛选条件不合法，请重置后重试。";
  if (code) return `总看板加载失败：${code}`;
  return "总看板加载失败，请稍后重试。";
}
