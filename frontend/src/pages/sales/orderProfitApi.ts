import { backendRequest } from "@/api/backendApi";
import { normalizeReportFilterOptions } from "@/shared/report-filters";
import type { SalesFilterOptions } from "@/pages/sales/salesFilterOptionsApi";
import type {
  OrderProfitCostStatus,
  OrderProfitCurrency,
  OrderProfitRow,
} from "@/pages/sales/orderProfitTypes";

interface BackendOrderProfitItem {
  id: string;
  business_date_la: string;
  business_timezone: string;
  local_sku: string;
  item_ids: string[];
  store_ids: string[];
  store_names: string[];
  owner_refs: string[];
  mskus: string[];
  product_name: string | null;
  store_count: number;
  item_count: number;
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  sample_qty: string | null;
  sample_amount: string | null;
  return_qty: string;
  refund_amount: string | null;
  refund_loss_amount: string | null;
  return_rate_30d: string | null;
  ad_spend_amount: string | null;
  sem_ad_spend_amount: string | null;
  total_ad_spend_amount: string | null;
  ad_ratio: string | null;
  wfs_available_quantity: string | null;
  wfs_fee_unit_amount: string | null;
  commission_fee_amount: string | null;
  wfs_fee_total_amount: string | null;
  wfs_low_price_surcharge_amount: string;
  purchase_cost_unit_cny: string | null;
  purchase_cost_total_usd: string | null;
  first_leg_cost_unit_cny: string | null;
  first_leg_cost_total_usd: string | null;
  storage_fee_unit_amount: string | null;
  storage_fee_total_amount: string | null;
  gross_profit_amount: string | null;
  gross_profit_currency_code: string | null;
  total_cost_amount: string | null;
  average_profit_per_order: string | null;
  gross_margin: string | null;
  roi: string | null;
  cost_status: "complete" | "partial" | "missing";
  missing_cost_codes: string[];
  calc_version: string;
  calculated_at: string;
}

interface BackendOrderProfitSummary {
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  return_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
  refund_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  ad_spend_amount: string;
  sem_ad_spend_amount: string;
  total_ad_spend_amount: string;
  ad_spend_currency_code: string | null;
  ad_ratio: string | null;
}

interface BackendOrderProfitData {
  items: BackendOrderProfitItem[];
  summary?: BackendOrderProfitSummary;
}

interface BackendOrderProfitTrendPoint {
  date: string;
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  return_qty: string;
  refund_amount: string;
  refund_loss_amount: string;
  refund_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  profit_margin: string | null;
  ad_spend_amount: string;
  sem_ad_spend_amount: string;
  total_ad_spend_amount: string;
  ad_spend_currency_code: string | null;
  ad_ratio: string | null;
}

interface BackendOrderProfitTrendData {
  items: BackendOrderProfitTrendPoint[];
}

export interface OrderProfitApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
  partial: boolean;
  input_missing: boolean;
}

export interface OrderProfitServerSummary {
  salesQuantity: number;
  orderCount: number;
  salesAmount: number;
  salesCurrency: OrderProfitCurrency;
  refundQuantity: number;
  refundAmount: number;
  refundLossAmount: number;
  refundCurrency: OrderProfitCurrency;
  orderProfitAmount: number;
  orderProfitCurrency: OrderProfitCurrency;
  adSpendAmount: number;
  semAdSpendAmount: number;
  totalAdSpendAmount: number;
  adSpendCurrency: OrderProfitCurrency;
  adRatio: number | null;
}

export interface OrderProfitApiResult {
  rows: OrderProfitRow[];
  summary: OrderProfitServerSummary | null;
  meta: OrderProfitApiMeta;
}

export interface OrderProfitTrendPoint {
  date: string;
  salesVolume: number;
  orderCount: number;
  salesAmount: number;
  salesCurrency: OrderProfitCurrency;
  refundAmount: number;
  refundQuantity: number;
  refundLossAmount: number;
  refundCurrency: OrderProfitCurrency;
  orderProfit: number;
  orderProfitCurrency: OrderProfitCurrency;
  profitMargin: number | null;
  adSpend: number;
  semAdSpend: number;
  totalAdSpend: number;
  adSpendCurrency: OrderProfitCurrency;
  adRatio: number | null;
}

interface OrderProfitParams {
  startDate?: string;
  endDate?: string;
  page?: number;
  pageSize?: number;
  platforms?: string[];
  owners?: string[];
  stores?: string[];
  searchField?: string;
  keyword?: string;
  signal?: AbortSignal;
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);
const nullableNumberValue = (value: string | null | undefined) => (
  value == null ? null : Number(value)
);

const currencyLabel = (currencyCode: string | null): OrderProfitCurrency => (
  currencyCode === "CNY" ? "CNY" : "USD"
);

const costStatusLabel = (
  status: BackendOrderProfitItem["cost_status"],
  missingCodes: string[],
): OrderProfitCostStatus => {
  if (missingCodes.length > 0) return "部分缺失";
  if (status === "complete") return "已完成";
  if (status === "partial") return "部分缺失";
  return "待补齐";
};

const backendSearchField = (field: string | undefined) => {
  if (field === "productId") return "item_id";
  if (field === "productName") return "product_name";
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

const appendOrderProfitFilters = (search: URLSearchParams, params: OrderProfitParams) => {
  appendMultiParam(search, "platform", params.platforms);
  appendMultiParam(search, "owner_ref", params.owners);
  appendMultiParam(search, "store_id", params.stores);

  const keyword = params.keyword?.trim();
  if (keyword) {
    search.set("search_field", backendSearchField(params.searchField));
    search.set("keyword", keyword);
  }
};

const normalizedTextValues = (values: string[]) => (
  values.map((value) => String(value).trim()).filter(Boolean)
);

const joinedText = (values: string[], fallback = "-") => {
  const clean = normalizedTextValues(values);
  if (clean.length === 0) return fallback;
  if (clean.length <= 2) return clean.join(" / ");
  return `${clean[0]} / ${clean[1]} 等${clean.length}个`;
};

const fullJoinedText = (values: string[], fallback = "-") => {
  const clean = normalizedTextValues(values);
  return clean.length > 0 ? clean.join(" / ") : fallback;
};

const toOrderProfitRow = (item: BackendOrderProfitItem): OrderProfitRow => {
  const itemIds = Array.isArray(item.item_ids) ? item.item_ids : [];
  const storeIds = Array.isArray(item.store_ids) ? item.store_ids : [];
  const storeNames = Array.isArray(item.store_names) ? item.store_names : [];
  const ownerRefs = Array.isArray(item.owner_refs) ? item.owner_refs : [];
  const mskus = Array.isArray(item.mskus) ? item.mskus : [];
  const productId = itemIds[0] ?? item.local_sku;
  const salesVolume = numberValue(item.sales_qty);
  const salesAmount = numberValue(item.sales_amount);
  const refundAmount = nullableNumberValue(item.refund_amount);
  const adSpend = numberValue(item.ad_spend_amount);
  const semAdSpend = numberValue(item.sem_ad_spend_amount);
  const totalAdSpend = numberValue(item.total_ad_spend_amount);
  const displayStores = storeNames.length > 0 ? storeNames : storeIds;
  const displayMskus = mskus.length > 0 ? mskus : itemIds;

  return {
    id: item.id,
    productId,
    productName: item.product_name ?? item.local_sku ?? productId,
    sku: item.local_sku,
    skuFullText: item.local_sku,
    msku: joinedText(displayMskus),
    mskuFullText: fullJoinedText(displayMskus),
    platform: "Walmart",
    store: joinedText(displayStores),
    storeFullText: fullJoinedText(displayStores),
    owner: joinedText(ownerRefs),
    ownerFullText: fullJoinedText(ownerRefs),
    currency: currencyLabel(item.sales_currency_code),
    salesVolume,
    orderCount: numberValue(item.order_count),
    salesAmount,
    averagePrice: salesVolume ? salesAmount / salesVolume : null,

    sampleQuantity: numberValue(item.sample_qty),
    sampleAmount: nullableNumberValue(item.sample_amount),

    refundQuantity: numberValue(item.return_qty),
    refundAmount,
    refundLossAmount: refundAmount,
    returnRate30Days: item.return_rate_30d == null ? null : numberValue(item.return_rate_30d) * 100,

    adSpend,
    semAdSpend,
    totalAdSpend,
    adRatio: salesAmount ? totalAdSpend / salesAmount * 100 : null,

    wfsDeliveryFee: nullableNumberValue(item.wfs_fee_total_amount),
    wfsLowPriceSurcharge: numberValue(item.wfs_low_price_surcharge_amount),
    wfsDeliveryUnitPrice: nullableNumberValue(item.wfs_fee_unit_amount),

    commission: numberValue(item.commission_fee_amount),

    purchaseCost: nullableNumberValue(item.purchase_cost_total_usd),
    purchaseUnitPriceCny: nullableNumberValue(item.purchase_cost_unit_cny),

    firstLegCost: nullableNumberValue(item.first_leg_cost_total_usd),
    firstLegUnitPriceCny: nullableNumberValue(item.first_leg_cost_unit_cny),

    storageFee: nullableNumberValue(item.storage_fee_total_amount),
    storageUnitPrice: nullableNumberValue(item.storage_fee_unit_amount),

    wfsAvailableInventory: numberValue(item.wfs_available_quantity),
    totalCost: nullableNumberValue(item.total_cost_amount),
    orderProfit: nullableNumberValue(item.gross_profit_amount),
    averageProfitPerOrder: nullableNumberValue(item.average_profit_per_order),
    profitMargin: item.gross_margin == null ? null : numberValue(item.gross_margin) * 100,
    roi: item.roi == null ? null : numberValue(item.roi),
    costStatus: costStatusLabel(item.cost_status, item.missing_cost_codes),
    sevenDayDates: [],
    sevenDaySales: [],
  };
};

const toOrderProfitServerSummary = (
  summary: BackendOrderProfitSummary | undefined,
): OrderProfitServerSummary | null => {
  if (!summary) return null;

  return {
    salesQuantity: numberValue(summary.sales_qty),
    orderCount: numberValue(summary.order_count),
    salesAmount: numberValue(summary.sales_amount),
    salesCurrency: currencyLabel(summary.sales_currency_code),
    refundQuantity: numberValue(summary.return_qty),
    refundAmount: numberValue(summary.refund_amount),
    refundLossAmount: numberValue(summary.refund_amount),
    refundCurrency: currencyLabel(summary.refund_currency_code),
    orderProfitAmount: numberValue(summary.order_profit_amount),
    orderProfitCurrency: currencyLabel(summary.order_profit_currency_code),
    adSpendAmount: numberValue(summary.ad_spend_amount),
    semAdSpendAmount: numberValue(summary.sem_ad_spend_amount),
    totalAdSpendAmount: numberValue(summary.total_ad_spend_amount),
    adSpendCurrency: currencyLabel(summary.ad_spend_currency_code),
    adRatio: numberValue(summary.sales_amount)
      ? numberValue(summary.total_ad_spend_amount) / numberValue(summary.sales_amount) * 100
      : null,
  };
};

const toOrderProfitTrendPoint = (
  item: BackendOrderProfitTrendPoint,
): OrderProfitTrendPoint => {
  const salesAmount = numberValue(item.sales_amount);
  const refundAmount = numberValue(item.refund_amount);
  const totalAdSpend = numberValue(item.total_ad_spend_amount);

  return {
    date: item.date,
    salesVolume: numberValue(item.sales_qty),
    orderCount: numberValue(item.order_count),
    salesAmount,
    salesCurrency: currencyLabel(item.sales_currency_code),
    refundQuantity: numberValue(item.return_qty),
    refundAmount,
    refundLossAmount: refundAmount,
    refundCurrency: currencyLabel(item.refund_currency_code),
    orderProfit: numberValue(item.order_profit_amount),
    orderProfitCurrency: currencyLabel(item.order_profit_currency_code),
    profitMargin: nullableNumberValue(item.profit_margin),
    adSpend: numberValue(item.ad_spend_amount),
    semAdSpend: numberValue(item.sem_ad_spend_amount),
    totalAdSpend,
    adSpendCurrency: currencyLabel(item.ad_spend_currency_code),
    adRatio: salesAmount ? totalAdSpend / salesAmount * 100 : null,
  };
};

export async function fetchOrderProfitFilterOptions(
  params: OrderProfitParams,
): Promise<SalesFilterOptions> {
  const search = new URLSearchParams();

  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  appendOrderProfitFilters(search, params);

  const suffix = search.toString();
  const requestOptions = params.signal ? { signal: params.signal } : undefined;

  const envelope = await backendRequest<SalesFilterOptions, unknown>(
    `/api/sales/order-profit/filter-options${suffix ? `?${suffix}` : ""}`,
    requestOptions,
  );

  return {
    platforms: normalizeReportFilterOptions(envelope.data.platforms),
    owners: normalizeReportFilterOptions(envelope.data.owners),
    stores: normalizeReportFilterOptions(envelope.data.stores),
  };
}


export type OrderProfitExportPeriod = "day" | "month";
export type OrderProfitExportDimension = "item_id" | "sku" | "msku";

export interface OrderProfitExportParams extends OrderProfitParams {
  period: OrderProfitExportPeriod;
  dimension: OrderProfitExportDimension;
  columns: string[];
}

export async function downloadOrderProfitExportCsv(
  params: OrderProfitExportParams,
): Promise<void> {
  const search = new URLSearchParams();

  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  search.set("period", params.period);
  search.set("dimension", params.dimension);

  if (params.columns.length > 0) {
    search.set("columns", params.columns.join(","));
  }

  appendOrderProfitFilters(search, params);

  const previewToken = import.meta.env.VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN;
  const response = await fetch(`/api/sales/order-profit/export?${search.toString()}`, {
    credentials: "same-origin",
    headers: {
      ...(previewToken ? { "X-Product-Management-Preview-Token": previewToken } : {}),
    },
  });

  if (!response.ok) {
    throw new Error(`ORDER_PROFIT_EXPORT_FAILED_${response.status}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = /filename="?([^"]+)"?/i.exec(disposition);
  const filename = filenameMatch?.[1] ?? `order-profit-${params.period}.csv`;
  const url = URL.createObjectURL(blob);

  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}


export async function fetchOrderProfitRows(
  params: OrderProfitParams,
): Promise<OrderProfitApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;

  const search = new URLSearchParams();
  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  appendOrderProfitFilters(search, params);
  search.set("page", String(page));
  search.set("page_size", String(pageSize));

  const requestOptions = params.signal ? { signal: params.signal } : undefined;

  const envelope = await backendRequest<BackendOrderProfitData, OrderProfitApiMeta>(
    `/api/sales/order-profit?${search.toString()}`,
    requestOptions,
  );

  const items = Array.isArray(envelope.data.items) ? envelope.data.items : [];

  return {
    rows: items.map(toOrderProfitRow),
    summary: toOrderProfitServerSummary(envelope.data.summary),
    meta: envelope.meta,
  };
}

export async function fetchOrderProfitTrendPoints(
  params: OrderProfitParams,
): Promise<OrderProfitTrendPoint[]> {
  const search = new URLSearchParams();
  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  appendOrderProfitFilters(search, params);

  const requestOptions = params.signal ? { signal: params.signal } : undefined;

  const envelope = await backendRequest<BackendOrderProfitTrendData>(
    `/api/sales/order-profit/trend?${search.toString()}`,
    requestOptions,
  );

  const items = Array.isArray(envelope.data.items) ? envelope.data.items : [];
  return items.map(toOrderProfitTrendPoint);
}

export function preloadOrderProfitRows(params: OrderProfitParams): void {
  void fetchOrderProfitRows(params).catch(() => undefined);
}

export function preloadOrderProfitSourceRecords(params: OrderProfitParams): void {
  preloadOrderProfitRows(params);
}
