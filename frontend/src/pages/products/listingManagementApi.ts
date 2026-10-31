import { backendDownload, backendRequest } from "@/api/backendApi";
import { getCachedResource, preloadCachedResource, stableCacheKey } from "@/shared/preload/resourceCache";
import type { ReportFilterOption } from "@/shared/report-filters";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

interface BackendListingItem {
  id: string;
  source_account_ref: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  msku: string | null;
  local_sku: string | null;
  local_name: string | null;
  title: string | null;
  picture_url: string | null;
  owner_ref: string | null;
  owner_uid: string | null;
  owner_name: string | null;
  product_developer_uid: string | null;
  product_developer_name: string | null;
  product_grade: string | null;
  tags: string[];
  strike_price_amount: string | null;
  strike_price_currency_code?: string | null;
  sale_price_amount: string | null;
  sale_price_currency_code?: string | null;
  listing_status: string | null;
  lifecycle_status: string | null;
  fulfillment_type: string | null;
  fulfillment_type_name: string | null;
  listing_start_at_utc: string | null;
  listing_start_source_raw?: string | null;
  launch_date_cn?: string | null;
  first_wfs_seen_at_utc?: string | null;
  monitor_observed_at?: string | null;
  monitor_source?: string | null;
  monitor_outcome?: string | null;
  monitor_error_code?: string | null;
  monitor_image_urls?: string[];
  category: string | null;
  wfs_available_quantity: string | null;
  inbound_quantity: string | null;
  sales_30d: string;
  ad_spend_30d_amount: string | null;
  buybox_status: string | null;
  walmart_seller: string | null;
  is_hijacked: boolean | null;
  average_rating: string | null;
  review_count: number | null;
  brand: string | null;
  disabled_reason: string | null;
  gtin: string | null;
  calculated_at: string;
  archive_reason?: string | null;
  is_archived?: boolean;
  archive_state_known?: boolean;
}

interface BackendListingData {
  items: BackendListingItem[];
}

interface BackendListingSummaryData {
  total: number;
  online: number;
  buybox_exception: number;
  rating_warning: number;
  resold_warning: number;
  strike_price_exception: number;
}

interface BackendListingArchiveActionData {
  listing_id: string;
  is_archived: boolean;
  archive_reason?: string | null;
  archived_at?: string | null;
  archived_by?: string | null;
  restored_at?: string | null;
  restored_by?: string | null;
}

interface BackendListingFilterOptionsData {
  stores: ReportFilterOption[];
  owners: ReportFilterOption[];
  product_types: ReportFilterOption[];
  tags?: ReportFilterOption[];
  archive_statuses?: ReportFilterOption[];
}

interface BackendListingTag {
  id: string;
  source_account_ref: string;
  name: string;
  color: string;
  usage: number;
  sort_order: number;
  is_active: boolean;
}

interface BackendListingTagListData {
  items: BackendListingTag[];
  source_account_refs: string[];
}

export interface ListingCustomTag {
  id: string;
  sourceAccountRef: string;
  name: string;
  color: string;
  usage: number;
  isActive: boolean;
}

export interface ListingTagMutationPayload {
  name: string;
  color: string;
  sourceAccountRef?: string;
  isActive?: boolean;
}

const toListingCustomTag = (tag: BackendListingTag): ListingCustomTag => ({
  id: tag.id,
  sourceAccountRef: tag.source_account_ref,
  name: tag.name,
  color: tag.color,
  usage: tag.usage,
  isActive: tag.is_active,
});

export interface ListingManagementApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
}

export interface ListingManagementApiResult {
  rows: ListingManagementRow[];
  meta: ListingManagementApiMeta;
}

interface BackendListingGptAnalysisLink {
  listing_id: string;
  keyword_analysis_url: string;
  ad_analysis_url: string;
  updated_by: string | null;
  updated_at: string | null;
}

export interface ListingGptAnalysisLink {
  listingId: string;
  keywordAnalysisUrl: string;
  adAnalysisUrl: string;
  updatedBy: string | null;
  updatedAt: string | null;
}

export interface ListingGptAnalysisPayload {
  keywordAnalysisUrl: string;
  adAnalysisUrl: string;
}

const toListingGptAnalysisLink = (item: BackendListingGptAnalysisLink): ListingGptAnalysisLink => ({
  listingId: item.listing_id,
  keywordAnalysisUrl: item.keyword_analysis_url ?? "",
  adAnalysisUrl: item.ad_analysis_url ?? "",
  updatedBy: item.updated_by,
  updatedAt: item.updated_at,
});

export interface ListingManagementSummary {
  total: number;
  online: number;
  buyboxException: number;
  ratingWarning: number;
  resoldWarning: number;
  strikePriceException: number;
}

export interface ListingManagementFilterOptions {
  stores: ReportFilterOption[];
  owners: ReportFilterOption[];
  productTypes: ReportFilterOption[];
  tags: ReportFilterOption[];
  archiveStatuses?: ReportFilterOption[];
}

export interface ListingManagementParams {
  stores?: string[];
  owners?: string[];
  productTypes?: string[];
  productStatuses?: string[];
  tagValues?: string[];
  archiveStatuses?: string[];
  searchType?: "sku" | "msku" | "productId" | "productName";
  keyword?: string;
  batchValues?: string[];
  summaryFilter?: string;
  page?: number;
  pageSize?: number;
  sortField?: string;
  sortOrder?: "asc" | "desc";
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

export const toListingStartText = (normalizedValue: string | null, sourceRawValue: string | null = null): string => {
  if (!normalizedValue) {
    const raw = sourceRawValue?.trim() ?? "";
    return /^(\d{4}-\d{2}-\d{2})/.exec(raw)?.[1] ?? raw;
  }
  // The API field is explicitly UTC. Normalize offset-aware timestamps to UTC;
  // preserve date-only payloads instead of guessing their original timezone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalizedValue)) return normalizedValue;
  const parsed = new Date(normalizedValue);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString().slice(0, 10);
};

const toCheckedText = (value: string): string => value.replace("T", " ").slice(0, 16);

const normalizeListingStatus = (value: string | null) => {
  const raw = value?.trim();
  if (!raw) return "待确认";
  const normalized = raw.toLocaleLowerCase();
  if (["online", "published", "publish", "在售", "在线"].includes(normalized)) return "在线";
  if (["offline", "unpublished", "离线"].includes(normalized)) return "离线";
  return raw;
};

const normalizeBuyBoxStatus = (value: string | null) => {
  const raw = value?.trim();
  if (!raw) return "待确认";
  const normalized = raw.toLocaleLowerCase();
  if (["primary", "won", "winning", "owned", "拥有"].includes(normalized)) return "拥有";
  if (["lost", "not_owned", "secondary", "other", "未拥有"].includes(normalized)) return "未拥有";
  return raw;
};

export const safeListingImageUrls = (urls: Array<string | null | undefined>): string[] =>
  urls.filter((url): url is string => typeof url === "string" && /^https:\/\//i.test(url));

const toListingRow = (item: BackendListingItem): ListingManagementRow => {
  const monitorImages = safeListingImageUrls(item.monitor_image_urls ?? []);
  return {
  id: item.id,
  sourceAccountRef: item.source_account_ref,
  image: monitorImages[0] ?? safeListingImageUrls([item.picture_url])[0] ?? "▤",
  monitorImages,
  msku: item.msku ?? "-",
  productId: item.item_id,
  store: item.store_name ?? item.store_id,
  owner: item.owner_name ?? item.owner_ref ?? "未分配",
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? "未设置本地品名",
  title: item.title ?? "暂无平台标题",
  productType: item.category ?? "待分类",
  listPrice: numberValue(item.strike_price_amount),
  salePrice: numberValue(item.sale_price_amount),
  listPriceKnown: item.strike_price_amount !== null,
  salePriceKnown: item.sale_price_amount !== null,
  listPriceCurrency: item.strike_price_currency_code ?? "",
  salePriceCurrency: item.sale_price_currency_code ?? "",
  productStatus: item.disabled_reason ? "停用" : "启用",
  lifecycle: item.lifecycle_status ?? "待计算",
  fulfillmentMethod: item.fulfillment_type_name?.trim() || item.fulfillment_type?.trim() || "待确认",
  listedAt: toListingStartText(item.listing_start_at_utc, item.listing_start_source_raw),
  listingDateSource: item.listing_start_at_utc ? "平台标准化日期" : item.listing_start_source_raw ? "原始日期待核实" : "未知",
  listingStartRaw: item.listing_start_source_raw ?? "",
  firstWfsAvailableAt: item.launch_date_cn ?? "",
  firstWfsObservedAt: item.first_wfs_seen_at_utc ?? "",
  category: item.category ?? "-",
  wfsAvailableInventory: numberValue(item.wfs_available_quantity),
  wfsAvailableInventoryKnown: item.wfs_available_quantity != null,
  inboundInventory: numberValue(item.inbound_quantity),
  inboundInventoryKnown: item.inbound_quantity != null,
  sales30Days: numberValue(item.sales_30d),
  adSpend30Days: numberValue(item.ad_spend_30d_amount),
  adSpend30DaysKnown: item.ad_spend_30d_amount !== null,
  disabledReason: item.disabled_reason ?? "",
  listingStatus: normalizeListingStatus(item.listing_status),
  buyBoxStatus: normalizeBuyBoxStatus(item.buybox_status),
  walmartSeller: item.walmart_seller ?? "待确认",
  resold: item.is_hijacked == null ? "待确认" : item.is_hijacked ? "是" : "否",
  checkedAt: item.monitor_observed_at ? toCheckedText(item.monitor_observed_at) : "未监控",
  dataUpdatedAt: toCheckedText(item.calculated_at),
  monitorSource: item.monitor_source ?? "未监控",
  monitorStatus: item.monitor_outcome ?? "未监控",
  monitorError: item.monitor_error_code ?? "",
  monitorImageCount: monitorImages.length,
  monitorAgeHours: item.monitor_observed_at && Number.isFinite(Date.parse(item.monitor_observed_at))
    ? Math.max(0, Math.floor((Date.now() - Date.parse(item.monitor_observed_at)) / 3600000))
    : null,
  rating: numberValue(item.average_rating),
  ratingKnown: item.average_rating != null,
  reviewCount: item.review_count ?? 0,
  reviewCountKnown: item.review_count != null,
  brand: item.brand ?? "-",
  tags: item.tags,
  gtin: item.gtin ?? "-",
  productGrade: item.product_grade ?? "未分级",
  archiveReason: item.archive_reason ?? null,
  isArchived: Boolean(item.is_archived ?? (item as { isArchived?: boolean }).isArchived ?? false),
  archiveStateKnown: item.archive_state_known ?? false,
  };
};

const backendSearchField = (field: ListingManagementParams["searchType"] | undefined) => {
  if (field === "productId") return "item_id";
  if (field === "productName") return "title";
  return field ?? "sku";
};

const appendMultiParam = (
  search: URLSearchParams,
  key: string,
  values: string[] | undefined,
) => {
  const normalized = (values ?? []).map((value) => value.trim()).filter(Boolean);
  if (normalized.length > 0) search.set(key, JSON.stringify(normalized));
};

const appendListingFilters = (search: URLSearchParams, params: ListingManagementParams) => {
  appendMultiParam(search, "store_id", params.stores);
  appendMultiParam(search, "owner_ref", params.owners);
  appendMultiParam(search, "product_type", params.productTypes);
  appendMultiParam(search, "status", params.productStatuses);
  appendMultiParam(search, "tag", params.tagValues);
  appendMultiParam(search, "archive_status", params.archiveStatuses);

  if (params.summaryFilter && params.summaryFilter !== "total") {
    search.set("summary_filter", params.summaryFilter);
  }

  const keyword = params.keyword?.trim();
  if (keyword) {
    search.set("search_field", backendSearchField(params.searchType));
    search.set("keyword", keyword);
  }

  const batchValues = (params.batchValues ?? []).map((value) => value.trim()).filter(Boolean);
  if (batchValues.length > 0) {
    search.set("search_field", backendSearchField(params.searchType));
    search.set("batch_values", batchValues.join(","));
  }
};

const buildBatchSearchPayload = (
  search: URLSearchParams,
  params: ListingManagementParams,
) => {
  const filters = new URLSearchParams(search);
  filters.delete("batch_values");
  filters.delete("selected_ids");
  filters.delete("columns");
  filters.set("search_field", backendSearchField(params.searchType));
  return {
    filters: Object.fromEntries(filters.entries()),
    batch_values: (params.batchValues ?? []).map((value) => value.trim()).filter(Boolean),
  };
};

async function fetchListingManagementRowsFromApi(
  params: ListingManagementParams = {},
): Promise<ListingManagementApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;

  const search = new URLSearchParams();
  search.set("page", String(page));
  search.set("page_size", String(pageSize));
  if (params.sortField) {
    search.set("sort_field", params.sortField);
    search.set("sort_order", params.sortOrder ?? "asc");
  }
  appendListingFilters(search, params);

  const envelope = params.batchValues?.length
    ? await backendRequest<BackendListingData, ListingManagementApiMeta>(
        "/api/listings/walmart/search",
        { method: "POST", body: JSON.stringify(buildBatchSearchPayload(search, params)) },
      )
    : await backendRequest<BackendListingData, ListingManagementApiMeta>(
        `/api/listings/walmart?${search.toString()}`,
      );

  return {
    rows: envelope.data.items.map(toListingRow),
    meta: envelope.meta,
  };
}

async function fetchListingManagementSummaryFromApi(
  params: ListingManagementParams = {},
): Promise<ListingManagementSummary> {
  const search = new URLSearchParams();
  appendListingFilters(search, { ...params, summaryFilter: "total" });

  const envelope = params.batchValues?.length
    ? await backendRequest<BackendListingSummaryData>(
        "/api/listings/walmart/summary/search",
        { method: "POST", body: JSON.stringify(buildBatchSearchPayload(search, params)) },
      )
    : await backendRequest<BackendListingSummaryData>(
        `/api/listings/walmart/summary?${search.toString()}`,
      );

  return {
    total: envelope.data.total,
    online: envelope.data.online,
    buyboxException: envelope.data.buybox_exception,
    ratingWarning: envelope.data.rating_warning,
    resoldWarning: envelope.data.resold_warning,
    strikePriceException: envelope.data.strike_price_exception,
  };
}

export async function exportListingManagementRows(
  params: ListingManagementParams = {},
  columns?: string[],
  selectedIds?: string[],
): Promise<void> {
  const search = new URLSearchParams();
  appendListingFilters(search, params);
  if (columns && columns.length > 0) {
    search.set("columns", columns.join(","));
  }
  if (selectedIds?.length) search.set("selected_ids", selectedIds.join(","));

  if (params.batchValues?.length || selectedIds?.length) {
    const payload = buildBatchSearchPayload(search, params);
    await backendDownload(
      "/api/listings/walmart/export/search",
      "listing-management-export.csv",
      {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          selected_ids: selectedIds ?? [],
          columns: columns ?? [],
        }),
      },
    );
    return;
  }

  await backendDownload(
    `/api/listings/walmart/export?${search.toString()}`,
    "listing-management-export.csv",
  );
}

async function fetchListingManagementFilterOptionsFromApi(): Promise<ListingManagementFilterOptions> {
  const envelope = await backendRequest<BackendListingFilterOptionsData>(
    "/api/listings/walmart/filter-options",
  );

  return {
    stores: envelope.data.stores,
    owners: envelope.data.owners,
    productTypes: envelope.data.product_types,
    tags: envelope.data.tags ?? [],
    archiveStatuses: envelope.data.archive_statuses ?? [],
  };
}


export async function fetchListingTags(): Promise<{ items: ListingCustomTag[]; sourceAccountRefs: string[] }> {
  const envelope = await backendRequest<BackendListingTagListData>("/api/listings/tags");
  return {
    items: envelope.data.items.map(toListingCustomTag),
    sourceAccountRefs: envelope.data.source_account_refs,
  };
}

export async function createListingTag(payload: ListingTagMutationPayload): Promise<ListingCustomTag> {
  const envelope = await backendRequest<BackendListingTag>("/api/listings/tags", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      color: payload.color,
      source_account_ref: payload.sourceAccountRef,
    }),
  });

  return toListingCustomTag(envelope.data);
}

export async function updateListingTag(
  tagId: string,
  payload: ListingTagMutationPayload,
): Promise<ListingCustomTag> {
  const envelope = await backendRequest<BackendListingTag>(`/api/listings/tags/${tagId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: payload.name,
      color: payload.color,
      is_active: payload.isActive,
    }),
  });

  return toListingCustomTag(envelope.data);
}

export async function archiveListingManagementRow(
  listingId: string,
  reason: string,
): Promise<BackendListingArchiveActionData> {
  const envelope = await backendRequest<BackendListingArchiveActionData>(
    `/api/listings/walmart/${listingId}/archive`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
  );

  return envelope.data;
}

export async function restoreListingManagementRow(
  listingId: string,
): Promise<BackendListingArchiveActionData> {
  const envelope = await backendRequest<BackendListingArchiveActionData>(
    `/api/listings/walmart/${listingId}/restore`,
    {
      method: "POST",
    },
  );

  return envelope.data;
}

export async function fetchListingGptAnalysisLink(listingId: string): Promise<ListingGptAnalysisLink> {
  const envelope = await backendRequest<BackendListingGptAnalysisLink>(
    `/api/listings/walmart/${encodeURIComponent(listingId)}/gpt-analysis`,
  );
  return toListingGptAnalysisLink(envelope.data);
}

export async function saveListingGptAnalysisLink(
  listingId: string,
  payload: ListingGptAnalysisPayload,
): Promise<ListingGptAnalysisLink> {
  const envelope = await backendRequest<BackendListingGptAnalysisLink>(
    `/api/listings/walmart/${encodeURIComponent(listingId)}/gpt-analysis`,
    {
      method: "PUT",
      body: JSON.stringify({
        keyword_analysis_url: payload.keywordAnalysisUrl,
        ad_analysis_url: payload.adAnalysisUrl,
      }),
    },
  );
  return toListingGptAnalysisLink(envelope.data);
}

export async function deleteListingTag(tagId: string): Promise<void> {
  await backendRequest<{ deleted: boolean }>(`/api/listings/tags/${tagId}`, {
    method: "DELETE",
  });
}

export interface BatchSetListingTagsPayload {
  listingIds: string[];
  tagValues: string[];
  mode?: "replace" | "append" | "remove";
}

export async function batchSetListingTags({
  listingIds,
  tagValues,
  mode = "append",
}: BatchSetListingTagsPayload): Promise<void> {
  await backendRequest<unknown>("/api/listings/tags/batch-set", {
    method: "POST",
    body: JSON.stringify({
      listing_ids: listingIds,
      tag_values: tagValues,
      mode,
    }),
  });
}

const cacheKey = (...parts: unknown[]) => "listing-management:" + stableCacheKey(parts);

export function fetchListingManagementRows(
  ...args: Parameters<typeof fetchListingManagementRowsFromApi>
): ReturnType<typeof fetchListingManagementRowsFromApi> {
  return getCachedResource(
    cacheKey("rows", ...args),
    () => fetchListingManagementRowsFromApi(...args),
  ) as ReturnType<typeof fetchListingManagementRowsFromApi>;
}

export function fetchListingManagementSummary(
  ...args: Parameters<typeof fetchListingManagementSummaryFromApi>
): ReturnType<typeof fetchListingManagementSummaryFromApi> {
  return getCachedResource(
    cacheKey("summary", ...args),
    () => fetchListingManagementSummaryFromApi(...args),
  ) as ReturnType<typeof fetchListingManagementSummaryFromApi>;
}

export function fetchListingManagementFilterOptions(): ReturnType<typeof fetchListingManagementFilterOptionsFromApi> {
  return getCachedResource(
    cacheKey("filter-options"),
    () => fetchListingManagementFilterOptionsFromApi(),
  ) as ReturnType<typeof fetchListingManagementFilterOptionsFromApi>;
}

export function preloadListingManagementRows(...args: Parameters<typeof fetchListingManagementRowsFromApi>) {
  preloadCachedResource(
    cacheKey("rows", ...args),
    () => fetchListingManagementRowsFromApi(...args),
  );
}
