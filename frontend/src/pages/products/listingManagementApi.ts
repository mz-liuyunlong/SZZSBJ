import { backendRequest } from "@/api/backendApi";
import { getCachedResource, preloadCachedResource, stableCacheKey } from "@/shared/preload/resourceCache";
import type { ReportFilterOption } from "@/shared/report-filters";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

interface BackendListingItem {
  id: string;
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
  sale_price_amount: string | null;
  listing_status: string | null;
  lifecycle_status: string | null;
  listing_start_at_utc: string | null;
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

interface BackendListingFilterOptionsData {
  stores: ReportFilterOption[];
  owners: ReportFilterOption[];
  product_types: ReportFilterOption[];
  tags?: ReportFilterOption[];
}

interface BackendListingTag {
  id: string;
  name: string;
  color: string;
  usage: number;
  sort_order: number;
  is_active: boolean;
}

interface BackendListingTagListData {
  items: BackendListingTag[];
}

export interface ListingCustomTag {
  id: string;
  name: string;
  color: string;
  usage: number;
}

export interface ListingTagMutationPayload {
  name: string;
  color: string;
}

const toListingCustomTag = (tag: BackendListingTag): ListingCustomTag => ({
  id: tag.id,
  name: tag.name,
  color: tag.color,
  usage: tag.usage,
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
}

export interface ListingManagementParams {
  stores?: string[];
  owners?: string[];
  productTypes?: string[];
  productStatuses?: string[];
  tagValues?: string[];
  searchType?: "sku" | "msku" | "productId" | "productName";
  keyword?: string;
  batchValues?: string[];
  summaryFilter?: string;
  page?: number;
  pageSize?: number;
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const toDateText = (value: string | null): string => {
  if (!value) return "";
  return value.slice(0, 10);
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

const toListingRow = (item: BackendListingItem): ListingManagementRow => ({
  id: item.id,
  image: item.picture_url ?? "▤",
  msku: item.msku ?? "-",
  productId: item.item_id,
  store: item.store_name ?? item.store_id,
  owner: item.owner_name ?? item.owner_ref ?? "未分配",
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? item.title ?? "-",
  title: item.title ?? item.local_name ?? "-",
  productType: item.category ?? "待分类",
  listPrice: numberValue(item.strike_price_amount),
  salePrice: numberValue(item.sale_price_amount),
  productStatus: item.disabled_reason ? "停用" : "启用",
  lifecycle: item.lifecycle_status ?? "待计算",
  listedAt: toDateText(item.listing_start_at_utc),
  category: item.category ?? "-",
  wfsAvailableInventory: numberValue(item.wfs_available_quantity),
  inboundInventory: numberValue(item.inbound_quantity),
  sales90Days: numberValue(item.sales_30d),
  adSpend30Days: numberValue(item.ad_spend_30d_amount),
  disabledReason: item.disabled_reason ?? "",
  listingStatus: normalizeListingStatus(item.listing_status),
  buyBoxStatus: normalizeBuyBoxStatus(item.buybox_status),
  walmartSeller: item.walmart_seller ?? "待确认",
  resold: item.is_hijacked ? "是" : "否",
  checkedAt: toCheckedText(item.calculated_at),
  rating: numberValue(item.average_rating),
  reviewCount: item.review_count ?? 0,
  brand: item.brand ?? "-",
  tags: item.tags,
  gtin: item.gtin ?? "-",
  productGrade: item.product_grade ?? "未分级",
});

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
  if (normalized.length > 0) search.set(key, normalized.join(","));
};

const appendListingFilters = (search: URLSearchParams, params: ListingManagementParams) => {
  appendMultiParam(search, "store_id", params.stores);
  appendMultiParam(search, "owner_ref", params.owners);
  appendMultiParam(search, "product_type", params.productTypes);
  appendMultiParam(search, "status", params.productStatuses);
  appendMultiParam(search, "tag", params.tagValues);

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

async function fetchListingManagementRowsFromApi(
  params: ListingManagementParams = {},
): Promise<ListingManagementApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;

  const search = new URLSearchParams();
  search.set("page", String(page));
  search.set("page_size", String(pageSize));
  appendListingFilters(search, params);

  const envelope = await backendRequest<BackendListingData, ListingManagementApiMeta>(
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

  const envelope = await backendRequest<BackendListingSummaryData>(
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

async function fetchListingManagementFilterOptionsFromApi(): Promise<ListingManagementFilterOptions> {
  const envelope = await backendRequest<BackendListingFilterOptionsData>(
    "/api/listings/walmart/filter-options",
  );

  return {
    stores: envelope.data.stores,
    owners: envelope.data.owners,
    productTypes: envelope.data.product_types,
    tags: envelope.data.tags ?? [],
  };
}


export async function fetchListingTags(): Promise<ListingCustomTag[]> {
  const envelope = await backendRequest<BackendListingTagListData>("/api/listings/tags");
  return envelope.data.items.map(toListingCustomTag);
}

export async function createListingTag(payload: ListingTagMutationPayload): Promise<ListingCustomTag> {
  const envelope = await backendRequest<BackendListingTag>("/api/listings/tags", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      color: payload.color,
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
    }),
  });

  return toListingCustomTag(envelope.data);
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
