import { backendRequest } from "@/api/backendApi";
import type {
  OrderProfitCurrency,
  OrderProfitSourceRecord,
} from "@/pages/sales/orderProfitTypes";

interface BackendDailySalesItem {
  id: string;
  business_date_la: string;
  store_id: string;
  store_name: string | null;
  owner_ref: string | null;
  item_id: string;
  msku: string | null;
  local_sku: string | null;
  local_name: string | null;
  title: string | null;
  platform_code: string | null;
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  return_qty: string | null;
  refund_amount: string | null;
  ad_spend_amount: string | null;
  commission_fee_amount: string | null;
  wfs_fee_total_amount: string | null;
  purchase_cost_total_usd: string | null;
  first_leg_cost_total_usd: string | null;
  storage_fee_total_amount: string | null;
  cost_status: "complete" | "partial" | "missing";
  missing_cost_codes: string[];
}

interface BackendDailySalesSummary {
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  refund_event_qty: string;
  refund_event_amount: string;
  refund_event_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  ad_spend_amount: string;
  ad_spend_currency_code: string | null;
}

interface BackendDailySalesData {
  items: BackendDailySalesItem[];
  summary?: BackendDailySalesSummary;
}

interface BackendOrderProfitTrendPoint {
  date: string;
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  refund_amount: string;
  refund_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  profit_margin: string | null;
  ad_spend_amount: string;
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
  refundCurrency: OrderProfitCurrency;
  orderProfitAmount: number;
  orderProfitCurrency: OrderProfitCurrency;
  adSpendAmount: number;
  adSpendCurrency: OrderProfitCurrency;
}

export interface OrderProfitApiResult {
  records: OrderProfitSourceRecord[];
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
  refundCurrency: OrderProfitCurrency;
  orderProfit: number;
  orderProfitCurrency: OrderProfitCurrency;
  profitMargin: number | null;
  adSpend: number;
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

const platformLabel = (platformCode: string | null): OrderProfitSourceRecord["platform"] => {
  if (platformCode === "amazon") return "Amazon";
  if (platformCode === "temu") return "TEMU";
  return "Walmart";
};

const costStatusLabel = (
  status: BackendDailySalesItem["cost_status"],
  missingCodes: string[],
): OrderProfitSourceRecord["costStatus"] => {
  if (missingCodes.length > 0) return "部分缺失";
  if (status === "complete") return "已完成";
  if (status === "partial") return "部分缺失";
  return "待补齐";
};

const toOrderProfitTrendPoint = (
  item: BackendOrderProfitTrendPoint,
): OrderProfitTrendPoint => ({
  date: item.date,
  salesVolume: numberValue(item.sales_qty),
  orderCount: numberValue(item.order_count),
  salesAmount: numberValue(item.sales_amount),
  salesCurrency: currencyLabel(item.sales_currency_code),
  refundAmount: numberValue(item.refund_amount),
  refundCurrency: currencyLabel(item.refund_currency_code),
  orderProfit: numberValue(item.order_profit_amount),
  orderProfitCurrency: currencyLabel(item.order_profit_currency_code),
  profitMargin: nullableNumberValue(item.profit_margin),
  adSpend: numberValue(item.ad_spend_amount),
  adSpendCurrency: currencyLabel(item.ad_spend_currency_code),
  adRatio: nullableNumberValue(item.ad_ratio),
});

const toOrderProfitSourceRecord = (item: BackendDailySalesItem): OrderProfitSourceRecord => ({
  id: item.id,
  date: item.business_date_la,
  store: item.store_name ?? item.store_id,
  owner: item.owner_ref ?? "未分配",
  msku: item.msku ?? "-",
  productId: item.item_id,
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? item.title ?? item.local_sku ?? item.item_id,
  platform: platformLabel(item.platform_code),
  currency: currencyLabel(item.sales_currency_code),
  salesVolume: numberValue(item.sales_qty),
  orderCount: numberValue(item.order_count),
  salesAmount: numberValue(item.sales_amount),
  refundQuantity: numberValue(item.return_qty),
  refundAmount: numberValue(item.refund_amount),
  adSpend: numberValue(item.ad_spend_amount),
  wfsDeliveryFee: nullableNumberValue(item.wfs_fee_total_amount),
  commission: numberValue(item.commission_fee_amount),
  purchaseCost: nullableNumberValue(item.purchase_cost_total_usd),
  firstLegCost: nullableNumberValue(item.first_leg_cost_total_usd),
  storageFee: nullableNumberValue(item.storage_fee_total_amount),
  costStatus: costStatusLabel(item.cost_status, item.missing_cost_codes),
});

const toOrderProfitServerSummary = (
  summary: BackendDailySalesSummary | undefined,
): OrderProfitServerSummary | null => {
  if (!summary) return null;

  return {
    salesQuantity: numberValue(summary.sales_qty),
    orderCount: numberValue(summary.order_count),
    salesAmount: numberValue(summary.sales_amount),
    salesCurrency: currencyLabel(summary.sales_currency_code),
    refundQuantity: numberValue(summary.refund_event_qty),
    refundAmount: numberValue(summary.refund_event_amount),
    refundCurrency: currencyLabel(summary.refund_event_currency_code),
    orderProfitAmount: numberValue(summary.order_profit_amount),
    orderProfitCurrency: currencyLabel(summary.order_profit_currency_code),
    adSpendAmount: numberValue(summary.ad_spend_amount),
    adSpendCurrency: currencyLabel(summary.ad_spend_currency_code),
  };
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

export async function fetchOrderProfitSourceRecords(
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

  const envelope = await backendRequest<BackendDailySalesData, OrderProfitApiMeta>(
    `/api/sales/daily-sales?${search.toString()}`,
    requestOptions,
  );

  const items = Array.isArray(envelope.data.items) ? envelope.data.items : [];

  return {
    records: items.map(toOrderProfitSourceRecord),
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

export function preloadOrderProfitSourceRecords(params: OrderProfitParams): void {
  void fetchOrderProfitSourceRecords(params).catch(() => undefined);
}
