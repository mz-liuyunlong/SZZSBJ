import { backendRequest } from "@/api/backendApi";
import type {
  RefundDetailApiResult,
  RefundDetailRow,
  RefundFilterOption,
  RefundFilters,
  RefundLagAnalysis,
  RefundLagDatum,
  RefundOverviewView,
  RefundProductAnalysisViewData,
  RefundProductDatum,
  RefundProductDetail,
  RefundReasonDatum,
  RefundReasonTag,
  RefundResponsibilityDatum,
  RefundResponsibilityTag,
} from "@/pages/aftersales/refundManagementTypes";

interface BackendFilterOption {
  value: string;
  label: string;
  color: string | null;
}

interface BackendRefundSummary {
  refund_orders: number;
  refund_item_rows: number;
  refund_qty: string;
  refund_amount: string;
  refund_currency_code: string | null;
  refund_loss_amount: string;
  sales_qty: string;
  refund_rate: string | null;
  avg_refund_amount_per_unit: string | null;
  avg_refund_loss_per_unit: string | null;
}

interface BackendRefundComparison {
  previous_start_date: string;
  previous_end_date: string;
  refund_orders_change_rate: string | null;
  refund_qty_change_rate: string | null;
  refund_loss_change_rate: string | null;
  refund_rate_change_pp: string | null;
}

interface BackendRefundTrendPoint {
  date: string;
  refund_orders: number;
  refund_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
  sales_qty: string;
  refund_rate: string | null;
}

interface BackendRefundReasonTag {
  code: string;
  name: string;
  category_code: string;
  category_name: string;
  color: string;
}

interface BackendRefundResponsibilityTag {
  code: string;
  name: string;
  color: string;
  source: string;
  confidence: string;
  editable: boolean;
}

interface BackendRefundReason extends BackendRefundReasonTag {
  refund_orders: number;
  refund_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
}

interface BackendRefundResponsibility {
  code: string;
  name: string;
  color: string;
  refund_orders: number;
  refund_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
}

interface BackendRefundOverviewData {
  summary: BackendRefundSummary;
  comparison: BackendRefundComparison;
  trend: BackendRefundTrendPoint[];
  reasons: BackendRefundReason[];
  responsibilities: BackendRefundResponsibility[];
  facets: {
    stores: BackendFilterOption[];
    owners: BackendFilterOption[];
    reasons: BackendFilterOption[];
    responsibilities: BackendFilterOption[];
  };
}

interface BackendRefundReadMeta {
  source_objects: string[];
  start_date: string;
  end_date: string;
  latest_updated_at: string | null;
}

interface BackendRefundProduct {
  product_key: string;
  store_id: string;
  store_name: string | null;
  local_sku: string | null;
  msku: string | null;
  item_id: string | null;
  product_name: string | null;
  owner_ref: string | null;
  refund_orders: number;
  refund_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
  sales_qty: string;
  refund_rate: string | null;
  top_reason: BackendRefundReasonTag | null;
  top_responsibility: BackendRefundResponsibilityTag | null;
  risk_level: "pending";
}

interface BackendRefundProductTrendPoint {
  date: string;
  refund_qty: string;
  refund_orders: number;
  refund_amount: string;
  refund_loss_amount: string;
  sales_qty: string;
  refund_rate: string | null;
}

interface BackendRefundLagBucket {
  key: "0_3" | "4_7" | "8_14" | "15_30" | "31_plus";
  refund_orders: number;
  refund_qty: string;
  ratio: string | null;
  refund_amount: string;
  refund_loss_amount: string;
}

interface BackendRefundLagAnalysis {
  average_days: string | null;
  median_days: string | null;
  main_bucket: BackendRefundLagBucket["key"] | null;
  main_bucket_ratio: string | null;
  eligible_item_rows: number;
  missing_time_rows: number;
  buckets: BackendRefundLagBucket[];
}

interface BackendRefundProductDetail extends BackendRefundProduct {
  trend: BackendRefundProductTrendPoint[];
  reasons: BackendRefundReason[];
  lag: BackendRefundLagAnalysis;
}

interface BackendRefundProductAnalysisData {
  dates: string[];
  items: BackendRefundProduct[];
  heat: { product_key: string; values: string[] }[];
  lag: BackendRefundLagAnalysis;
  selected: BackendRefundProductDetail | null;
}

interface BackendRefundItem {
  id: string;
  store_id: string;
  store_name: string | null;
  owner_ref: string | null;
  item_id: string | null;
  product_name: string | null;
  local_sku: string | null;
  msku: string | null;
  return_order_id: string;
  customer_order_id: string | null;
  purchase_order_id: string | null;
  platform_order_id: string;
  purchase_time_at: string | null;
  refund_time_at: string | null;
  refund_lag_days: string | null;
  return_qty: string;
  refund_amount: string | null;
  refund_currency_code: string | null;
  refund_loss_amount: string | null;
  return_reason_code: string | null;
  return_description: string | null;
  reason: BackendRefundReasonTag;
  responsibility: BackendRefundResponsibilityTag;
  current_refund_status: string | null;
  refund_completed: boolean;
}

interface BackendRefundItemData {
  items: BackendRefundItem[];
}

interface BackendRefundItemMeta extends BackendRefundReadMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface RefundApiParams {
  filters: RefundFilters;
  page?: number;
  pageSize?: number;
  selectedProductKey?: string;
  productKey?: string;
  signal?: AbortSignal;
}

const numberValue = (value: string | number | null | undefined) => Number(value ?? 0);
const nullableNumberValue = (value: string | number | null | undefined) => (
  value == null ? null : Number(value)
);

const lagLabels: Record<BackendRefundLagBucket["key"], string> = {
  "0_3": "0–3天",
  "4_7": "4–7天",
  "8_14": "8–14天",
  "15_30": "15–30天",
  "31_plus": "30天以上",
};

const toReasonTag = (item: BackendRefundReasonTag): RefundReasonTag => ({
  code: item.code,
  name: item.name,
  categoryCode: item.category_code,
  categoryName: item.category_name,
  color: item.color,
});

const toResponsibilityTag = (
  item: BackendRefundResponsibilityTag,
): RefundResponsibilityTag => ({
  code: item.code,
  name: item.name,
  color: item.color,
  source: item.source,
  confidence: item.confidence,
  editable: item.editable,
});

const toFilterOptions = (items: BackendFilterOption[]): RefundFilterOption[] => items.map((item) => ({
  value: item.value,
  label: item.label,
  color: item.color ?? undefined,
}));

const appendMulti = (search: URLSearchParams, key: string, values: string[]) => {
  const normalized = values.map((value) => value.trim()).filter(Boolean);
  if (normalized.length > 0) search.set(key, normalized.join(","));
};

const backendSearchField = (value: RefundFilters["searchField"]) => {
  if (value === "productId") return "item_id";
  if (value === "productName") return "product_name";
  if (value === "orderId") return "order_id";
  return value;
};

const buildRefundSearch = (filters: RefundFilters) => {
  const search = new URLSearchParams();
  const [startDate, endDate] = filters.dateRange ?? [];
  if (!startDate || !endDate) throw new Error("REFUND_DATE_RANGE_REQUIRED");

  search.set("start_date", startDate);
  search.set("end_date", endDate);
  appendMulti(search, "store_id", filters.stores);
  appendMulti(search, "owner_ref", filters.owners);
  appendMulti(search, "reason", filters.reasons);
  appendMulti(search, "responsibility", filters.responsibilities);

  const keyword = filters.keyword.trim();
  const batchValues = (filters.batchValues ?? []).map((value) => value.trim()).filter(Boolean);
  if (keyword || batchValues.length > 0) {
    search.set("search_field", backendSearchField(filters.searchField));
  }
  if (keyword) search.set("keyword", keyword);
  if (batchValues.length > 0) search.set("batch_values", batchValues.join(","));
  return search;
};

const toReason = (item: BackendRefundReason): RefundReasonDatum => ({
  ...toReasonTag(item),
  count: item.refund_orders,
  qty: numberValue(item.refund_qty),
  amount: numberValue(item.refund_amount),
  loss: numberValue(item.refund_loss_amount),
});

const toResponsibility = (
  item: BackendRefundResponsibility,
): RefundResponsibilityDatum => ({
  code: item.code,
  name: item.name,
  color: item.color,
  count: item.refund_orders,
  qty: numberValue(item.refund_qty),
  amount: numberValue(item.refund_amount),
  loss: numberValue(item.refund_loss_amount),
});

const toProduct = (item: BackendRefundProduct): RefundProductDatum => ({
  productKey: item.product_key,
  storeId: item.store_id,
  store: item.store_name ?? "未匹配店铺",
  sku: item.local_sku ?? "-",
  msku: item.msku ?? "-",
  productId: item.item_id ?? "-",
  name: item.product_name ?? "未匹配商品名称",
  owner: item.owner_ref ?? "未分配",
  sales: numberValue(item.sales_qty),
  orders: item.refund_orders,
  qty: numberValue(item.refund_qty),
  amount: numberValue(item.refund_amount),
  rate: nullableNumberValue(item.refund_rate),
  loss: numberValue(item.refund_loss_amount),
  topReason: item.top_reason ? toReasonTag(item.top_reason) : null,
  topResponsibility: item.top_responsibility
    ? toResponsibilityTag(item.top_responsibility)
    : null,
  risk: "pending",
});

const toLag = (item: BackendRefundLagAnalysis): RefundLagAnalysis => ({
  averageDays: nullableNumberValue(item.average_days),
  medianDays: nullableNumberValue(item.median_days),
  mainBucket: item.main_bucket,
  mainBucketRatio: nullableNumberValue(item.main_bucket_ratio),
  eligibleItemRows: item.eligible_item_rows,
  missingTimeRows: item.missing_time_rows,
  buckets: item.buckets.map((bucket): RefundLagDatum => ({
    key: bucket.key,
    name: lagLabels[bucket.key],
    orders: bucket.refund_orders,
    count: numberValue(bucket.refund_qty),
    ratio: nullableNumberValue(bucket.ratio),
    amount: numberValue(bucket.refund_amount),
    loss: numberValue(bucket.refund_loss_amount),
  })),
});

const toProductDetail = (item: BackendRefundProductDetail): RefundProductDetail => ({
  ...toProduct(item),
  trend: item.trend.map((point) => numberValue(point.refund_qty)),
  reasons: item.reasons.map(toReason),
  lag: toLag(item.lag),
});

const toDateTime = (value: string | null) => {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 16);
};

const toDetailRow = (item: BackendRefundItem): RefundDetailRow => ({
  id: item.id,
  store: item.store_name ?? "未匹配店铺",
  storeId: item.store_id,
  productId: item.item_id ?? "-",
  productName: item.product_name ?? "未匹配商品名称",
  sku: item.local_sku ?? "-",
  msku: item.msku ?? "-",
  owner: item.owner_ref ?? "未分配",
  orderId: item.platform_order_id,
  returnOrderId: item.return_order_id,
  orderedAt: toDateTime(item.purchase_time_at),
  refundedAt: toDateTime(item.refund_time_at),
  refundLagDays: nullableNumberValue(item.refund_lag_days),
  qty: numberValue(item.return_qty),
  amount: nullableNumberValue(item.refund_amount),
  currency: "USD",
  loss: nullableNumberValue(item.refund_loss_amount),
  rawReasonCode: item.return_reason_code ?? "",
  rawDescription: item.return_description ?? "",
  reason: toReasonTag(item.reason),
  responsibility: toResponsibilityTag(item.responsibility),
  status: item.current_refund_status ?? "",
  completed: item.refund_completed,
});

export async function fetchRefundOverview(
  params: RefundApiParams,
): Promise<RefundOverviewView> {
  const search = buildRefundSearch(params.filters);
  const envelope = await backendRequest<BackendRefundOverviewData, BackendRefundReadMeta>(
    `/api/after-sales/refunds/overview?${search.toString()}`,
    params.signal ? { signal: params.signal } : undefined,
  );

  const summary = envelope.data.summary;
  const comparison = envelope.data.comparison;
  return {
    summary: {
      refundOrders: summary.refund_orders,
      refundItemRows: summary.refund_item_rows,
      refundQty: numberValue(summary.refund_qty),
      refundAmount: numberValue(summary.refund_amount),
      refundLossAmount: numberValue(summary.refund_loss_amount),
      salesQty: numberValue(summary.sales_qty),
      refundRate: nullableNumberValue(summary.refund_rate),
      avgRefundAmountPerUnit: nullableNumberValue(summary.avg_refund_amount_per_unit),
      avgRefundLossPerUnit: nullableNumberValue(summary.avg_refund_loss_per_unit),
      ordersChangeRate: nullableNumberValue(comparison.refund_orders_change_rate),
      qtyChangeRate: nullableNumberValue(comparison.refund_qty_change_rate),
      lossChangeRate: nullableNumberValue(comparison.refund_loss_change_rate),
      refundRateChangePp: nullableNumberValue(comparison.refund_rate_change_pp),
    },
    dates: envelope.data.trend.map((point) => point.date.slice(5)),
    trend: {
      qty: envelope.data.trend.map((point) => numberValue(point.refund_qty)),
      rate: envelope.data.trend.map((point) => nullableNumberValue(point.refund_rate) ?? 0),
      loss: envelope.data.trend.map((point) => numberValue(point.refund_loss_amount)),
    },
    reasons: envelope.data.reasons.map(toReason),
    responsibilities: envelope.data.responsibilities.map(toResponsibility),
    stores: toFilterOptions(envelope.data.facets.stores),
    owners: toFilterOptions(envelope.data.facets.owners),
    reasonOptions: toFilterOptions(envelope.data.facets.reasons),
    responsibilityOptions: toFilterOptions(envelope.data.facets.responsibilities),
    latestUpdatedAt: envelope.meta.latest_updated_at,
  };
}

export async function fetchRefundProductAnalysis(
  params: RefundApiParams,
): Promise<RefundProductAnalysisViewData> {
  const search = buildRefundSearch(params.filters);
  if (params.selectedProductKey?.trim()) {
    search.set("selected_product_key", params.selectedProductKey.trim());
  }
  search.set("limit", "100");
  const envelope = await backendRequest<BackendRefundProductAnalysisData, BackendRefundReadMeta>(
    `/api/after-sales/refunds/product-analysis?${search.toString()}`,
    params.signal ? { signal: params.signal } : undefined,
  );

  const heatByProduct = new Map<string, string[]>(
    envelope.data.heat.map((row) => [row.product_key, row.values] as const),
  );
  return {
    dates: envelope.data.dates.map((value) => value.slice(5)),
    items: envelope.data.items.map(toProduct),
    heat: envelope.data.items.map((item) => (
      heatByProduct.get(item.product_key)?.map(numberValue) ?? envelope.data.dates.map(() => 0)
    )),
    lag: toLag(envelope.data.lag),
    selected: envelope.data.selected ? toProductDetail(envelope.data.selected) : null,
    latestUpdatedAt: envelope.meta.latest_updated_at,
  };
}

export async function fetchRefundItems(
  params: RefundApiParams,
): Promise<RefundDetailApiResult> {
  const search = buildRefundSearch(params.filters);
  if (params.productKey?.trim()) search.set("product_key", params.productKey.trim());
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.pageSize ?? 50));
  search.set("sort_by", "refund_time");
  search.set("sort_order", "desc");
  const envelope = await backendRequest<BackendRefundItemData, BackendRefundItemMeta>(
    `/api/after-sales/refunds/items?${search.toString()}`,
    params.signal ? { signal: params.signal } : undefined,
  );
  return {
    rows: envelope.data.items.map(toDetailRow),
    page: envelope.meta.page,
    pageSize: envelope.meta.page_size,
    total: envelope.meta.total,
    latestUpdatedAt: envelope.meta.latest_updated_at,
  };
}
