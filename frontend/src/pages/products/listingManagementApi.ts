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
  product_tags?: Array<{ id: string | null; label: string; color: string | null }>;
  product_tags_match_status?: string;
  strike_price_amount: string | null;
  sale_price_amount: string | null;
  listing_status: string | null;
  lifecycle_status: string | null;
  fulfillment_type: string | null;
  fulfillment_type_name: string | null;
  listing_start_at_utc: string | null;
  listing_start_source_raw?: string | null;
  launch_date_cn?: string | null;
  first_wfs_available_date_la?: string | null;
  monitor_checked_at?: string | null;
  monitor_source?: string | null;
  monitor_has_strikethrough?: boolean | null;
  monitor_strikethrough_source?: string | null;
  monitor_seller_names?: string[];
  monitor_seller_offer_count?: number | null;
  monitor_other_sellers_present?: boolean | null;
  monitor_image_urls?: string[];
  monitor_image_count?: number | null;
  monitor_key_features?: string[];
  monitor_review_fetch_status?: string | null;
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
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const toDateText = (value: string | null): string => {
  if (!value) return "";
  return value.slice(0, 10);
};

// WFS launch is the first positive inventory date in America/Los_Angeles.
 // Never substitute the ERP Listing creation timestamp or China date.
export const toListingStartText = (firstWfsDateLa: string | null): string => {
  return toDateText(firstWfsDateLa);
};

const toCheckedText = (value?: string | null): string => {
  if (!value) return "未检测";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未检测";
  // Business operations display China local time, not UTC ISO text.
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date);
};

const normalizeListingStatus = (
  value: string | null,
  cartValue: string | null,
): string => {
  const cart = normalizeBuyBoxStatus(cartValue);
  if ([
    "购物车丢失",
    "未拥有购物车",
    "未找到购物车",
    "缺货",
    "不可购买",
  ].includes(cart)) {
    return "异常";
  }

  const status = value?.trim().toUpperCase() ?? "";
  if ([
    "OFFLINE", "UNPUBLISHED", "INACTIVE",
    "DELISTED", "离线", "下架", "已下架", "异常",
  ].includes(status)) {
    return "异常";
  }

  if ([
    "ONLINE", "PUBLISHED", "PUBLISH",
    "在售", "在线", "正常",
  ].includes(status)) {
    return "正常";
  }

  if (cart === "正常" || cart === "拥有") {
    return "正常";
  }
  return "待确认";
};

const normalizeBuyBoxStatus = (value: string | null): string => {
  const key = value?.trim().toUpperCase() ?? "";
  const names: Record<string, string> = {
    NORMAL: "正常",
    "正常": "正常",
    PRIMARY: "拥有",
    WON: "拥有",
    WINNING: "拥有",
    OWNED: "拥有",
    "拥有": "拥有",
    LOST: "购物车丢失",
    NOT_OWNED: "未拥有购物车",
    SECONDARY: "未拥有购物车",
    OTHER: "未拥有购物车",
    "未拥有": "未拥有购物车",
    NOT_FOUND: "未找到购物车",
    CART_NOT_FOUND: "未找到购物车",
    OUT_OF_STOCK: "缺货",
    UNAVAILABLE: "不可购买",
    FETCH_ERROR: "检测失败",
    ERROR: "检测失败",
    TIMEOUT: "检测失败",
  };
  return names[key] ?? "待确认";
};

export const toListingRow = (item: BackendListingItem): ListingManagementRow => ({
  id: item.id,
  sourceAccountRef: item.source_account_ref,
  image: item.picture_url ?? "▤",
  msku: item.msku ?? "-",
  productId: item.item_id,
  store: item.store_name ?? item.store_id,
  owner: item.owner_name ?? item.owner_ref ?? "未分配",
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? item.title ?? "-",
  title: item.title ?? item.local_name ?? "-",
  productType: item.category ?? "待分类",
  listPrice: item.strike_price_amount == null ? null : numberValue(item.strike_price_amount),
  salePrice: item.sale_price_amount == null ? null : numberValue(item.sale_price_amount),
  productStatus: item.disabled_reason ? "停用" : "启用",
  lifecycle: item.lifecycle_status ?? "待判定",
  fulfillmentMethod: item.fulfillment_type_name?.trim() || item.fulfillment_type?.trim() || "待确认",
  listedAt: toListingStartText(item.first_wfs_available_date_la ?? null),
  category: item.category ?? "-",
  wfsAvailableInventory: numberValue(item.wfs_available_quantity),
  inboundInventory: numberValue(item.inbound_quantity),
  sales90Days: numberValue(item.sales_30d),
  adSpend30Days: numberValue(item.ad_spend_30d_amount),
  disabledReason: item.disabled_reason ?? "",
  listingStatus: normalizeListingStatus(item.listing_status, item.buybox_status),
  buyBoxStatus: normalizeBuyBoxStatus(item.buybox_status),
  walmartSeller: item.walmart_seller ?? "待确认",
  resold: item.is_hijacked == null ? "待检测" : item.is_hijacked ? "是" : "否",
  checkedAt: toCheckedText(item.monitor_checked_at),
  rating: item.average_rating == null ? null : numberValue(item.average_rating),
  reviewCount: item.review_count,
  hasStrikethrough: item.monitor_has_strikethrough ?? null,
  strikethroughSource: item.monitor_strikethrough_source ?? "",
  sellerNames: item.monitor_seller_names ?? [],
  sellerOfferCount: item.monitor_seller_offer_count ?? null,
  otherSellersPresent: item.monitor_other_sellers_present ?? null,
  imageUrls: item.monitor_image_urls ?? [],
  imageCount: item.monitor_image_count ?? null,
  keyFeatures: item.monitor_key_features ?? [],
  reviewFetchStatus: item.monitor_review_fetch_status ?? "",
  monitorSource: item.monitor_source ?? "",
  brand: item.brand ?? "-",
  tags: item.tags,
  productTags: (item.product_tags ?? []).filter((tag) => Boolean(tag.label?.trim())),
  productTagMatchStatus: item.product_tags_match_status ?? "pending",
  gtin: item.gtin ?? "-",
  productGrade: item.product_grade ?? "未分级",
  archiveReason: item.archive_reason ?? null,
  isArchived: Boolean(item.is_archived ?? (item as { isArchived?: boolean }).isArchived ?? false),
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
  appendMultiParam(search, "archive_status", params.archiveStatuses);

  if (params.summaryFilter && params.summaryFilter !== "total") {
    search.set("summary_filter", params.summaryFilter);
  }

  const keyword = params.keyword?.trim();
  if (keyword) {
    search.set("search_field", backendSearchField(params.searchType));
    search.set("keyword", keyword);
  }

  if ((params.batchValues ?? []).some((value) => value.trim())) {
    search.set("search_field", backendSearchField(params.searchType));
  }
};

const listingBatchValues = (params: ListingManagementParams): string[] =>
  (params.batchValues ?? []).map((value) => value.trim()).filter(Boolean);

const listingBatchBody = (search: URLSearchParams, batchValues: string[], columns: string[] = []) =>
  JSON.stringify({ query: Object.fromEntries(search.entries()), batch_values: batchValues, columns });

async function fetchListingManagementRowsFromApi(
  params: ListingManagementParams = {},
): Promise<ListingManagementApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;

  const search = new URLSearchParams();
  search.set("page", String(page));
  search.set("page_size", String(pageSize));
  appendListingFilters(search, params);

  const batchValues = listingBatchValues(params);
  const envelope = batchValues.length > 0
    ? await backendRequest<BackendListingData, ListingManagementApiMeta>(
      "/api/listings/walmart/batch-search",
      { method: "POST", body: listingBatchBody(search, batchValues) },
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

  const batchValues = listingBatchValues(params);
  const envelope = batchValues.length > 0
    ? await backendRequest<BackendListingSummaryData>(
      "/api/listings/walmart/summary/batch-search",
      { method: "POST", body: listingBatchBody(search, batchValues) },
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
): Promise<void> {
  const search = new URLSearchParams();
  appendListingFilters(search, params);
  const batchValues = listingBatchValues(params);
  if (batchValues.length > 0) {
    await backendDownload(
      "/api/listings/walmart/export/batch-search",
      "listing-management-export.csv",
      { method: "POST", body: listingBatchBody(search, batchValues, columns ?? []) },
    );
  } else {
    if (columns && columns.length > 0) {
      search.set("columns", columns.join(","));
    }
    await backendDownload(
      `/api/listings/walmart/export?${search.toString()}`,
      "listing-management-export.csv",
    );
  }
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

// Persisted manual lifecycle. The request never changes Listing creation dates or grades.
export async function setListingLifecycleBatch(
  listingIds: string[], stage: string, reason = "运营人工调整",
): Promise<{ updated_listings: number; unchanged_listings: number; stage: string }> {
  const response = await backendRequest<{
    updated_listings: number;
    unchanged_listings: number;
    stage: string;
  }>("/api/listings/walmart/lifecycle/batch-set", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds, stage, reason }),
  });
  return response.data;
}

// LISTING_DIAGNOSTIC_PRODUCTION_API_V1
// The API returns read-only candidate evidence, never a published grade.
export interface ListingEvaluationPreviewResult {
  listing_id: string;
  cutoff_la: string;
  current_lifecycle: string | null;
  current_grade: string | null;
  lifecycle_candidate: string | null;
  lifecycle_evidence_reason: string | null;
  first_positive_date_la: string | null;
  cutoff_wfs_available_quantity: string | null;
  consecutive_low_stock_days: number;
  grade_candidate: string | null;
  valid_short: number;
  valid_medium: number;
  weighted_margin_percent: string | null;
  valid_stock_days_30: number;
  observed_stock_days_7: number;
  low_stock_days_7: number;
  prior_effective_stock: boolean;
  currently_archived: boolean;
  rule_version: number;
  missing_evidence: string[];
  published: boolean;
}

export async function fetchListingEvaluationPreviews(
  listingIds: string[],
): Promise<ListingEvaluationPreviewResult[]> {
  if (!listingIds.length) return [];
  if (listingIds.length > 50) throw new Error("Listing diagnostic API accepts at most 50 IDs");
  const response = await backendRequest<{ items: ListingEvaluationPreviewResult[]; total: number }>(
    "/api/listings/evaluation-preview/batch",
    { method: "POST", body: JSON.stringify({ listing_ids: listingIds }) },
  );
  return response.data.items;
}

const diagnosticReasonCode = (reason: string | null, stage: string | null): string => {
  if (stage) return "TREND_CONFIRMED";
  if (!reason) return "OTHER_EVIDENCE_INCOMPLETE";
  if (reason.includes("HISTORICAL_FIRST_WFS")) return "HISTORICAL_LAUNCH_UNVERIFIED";
  if (reason.includes("FIRST_WFS_POSITIVE")) return "NO_POSITIVE_WFS_HISTORY";
  if (reason.includes("CUTOFF_WFS_SNAPSHOT")) return "CUTOFF_WFS_MISSING";
  if (reason.includes("ARCHIVED") || reason.includes("WORKFLOW_STAGE") || reason.includes("MANUAL_STAGE")) return "WORKFLOW_PROTECTED";
  if (reason.includes("STOCKOUT")) return "STOCKOUT_EVIDENCE_INCOMPLETE";
  if (reason.includes("SALES") || reason.includes("趋势") || reason.includes("有效")) return "SALES_VALID_DAYS_INSUFFICIENT";
  return "OTHER_EVIDENCE_INCOMPLETE";
};

export function withPendingListingDiagnostics(row: ListingManagementRow): ListingManagementRow {
  return {
    ...row,
    lifecycleDiagnostic: {
      reasonCode: "PREVIEW_NOT_AVAILABLE",
      reasons: [{ code: "PREVIEW_NOT_AVAILABLE", title: "尚未获取判定数据", detail: "", advice: "" }],
      evidence: [],
      cutoffLa: "",
      ruleVersion: 0,
    },
    gradeDiagnostic: {
      reason: "评级诊断尚未取得；正式评级未发布。",
      cutoffLa: "",
      sourceVerified: false,
    },
  };
}

export function applyListingEvaluationPreview(
  row: ListingManagementRow,
  preview: ListingEvaluationPreviewResult,
): ListingManagementRow {
  if (row.id !== preview.listing_id) return row;
  const candidate = preview.lifecycle_candidate;
  const reason = preview.lifecycle_evidence_reason;
  const reasonCode = diagnosticReasonCode(reason, candidate);
  const evidence = [
    { label: "截止日WFS可售", value: preview.cutoff_wfs_available_quantity == null ? "缺失" : `${preview.cutoff_wfs_available_quantity} 件` },
    { label: "近30天有效销量日", value: `${preview.valid_stock_days_30} / 30 天` },
    { label: "当前连续低库存", value: `${preview.consecutive_low_stock_days} 天` },
    { label: "历史首次有货观测", value: preview.first_positive_date_la ?? "缺失" },
  ];
  const hasPublishedGrade = !["", "未分级", "待评级"].includes(row.productGrade || "");
  const validCandidate = !preview.published && ["A", "B", "C", "D"].includes(preview.grade_candidate ?? "");
  const stageExcluded = preview.missing_evidence.includes("LIFECYCLE_EXCLUDED_FROM_GRADING");
  const gradeReason = stageExcluded
    ? "当前生命周期不参与评级。"
    : validCandidate
      ? "仅供诊断：广告、成本与财务数据的正式完整性尚未确认，候选等级未发布。"
      : "财务有效天数不足、利润率不可计算或正式发布证据未通过。";
  return {
    ...row,
    lifecycleDiagnostic: {
      reasonCode,
      candidateStage: candidate,
      reasons: [{ code: reasonCode, title: reason ?? "暂无可发布生命周期", detail: reason ?? "", advice: "" }],
      evidence,
      cutoffLa: preview.cutoff_la,
      ruleVersion: preview.rule_version,
    },
    productGrade: hasPublishedGrade
      ? row.productGrade
      : validCandidate ? preview.grade_candidate! : row.productGrade,
    gradePreviewCandidate: !hasPublishedGrade && validCandidate,
    gradeDiagnostic: {
      reason: gradeReason,
      cutoffLa: preview.cutoff_la,
      candidate: preview.grade_candidate ?? undefined,
      valid7: preview.valid_short,
      valid14: preview.valid_medium,
      weightedMargin: preview.weighted_margin_percent,
      sourceVerified: false,
    },
  };
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
