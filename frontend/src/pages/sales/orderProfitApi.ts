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

interface BackendDailySalesData {
  items: BackendDailySalesItem[];
}

interface BackendOrderProfitSummary {
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  refund_amount: string;
  refund_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  ad_spend_amount: string;
  ad_spend_currency_code: string | null;
}

interface BackendOrderProfitData {
  items: unknown[];
  summary?: BackendOrderProfitSummary;
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

interface OrderProfitParams {
  startDate?: string;
  endDate?: string;
  page?: number;
  pageSize?: number;
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
  summary: BackendOrderProfitSummary | undefined,
): OrderProfitServerSummary | null => {
  if (!summary) return null;

  return {
    salesQuantity: numberValue(summary.sales_qty),
    orderCount: numberValue(summary.order_count),
    salesAmount: numberValue(summary.sales_amount),
    salesCurrency: currencyLabel(summary.sales_currency_code),
    refundAmount: numberValue(summary.refund_amount),
    refundCurrency: currencyLabel(summary.refund_currency_code),
    orderProfitAmount: numberValue(summary.order_profit_amount),
    orderProfitCurrency: currencyLabel(summary.order_profit_currency_code),
    adSpendAmount: numberValue(summary.ad_spend_amount),
    adSpendCurrency: currencyLabel(summary.ad_spend_currency_code),
  };
};

export async function fetchOrderProfitSourceRecords(
  params: OrderProfitParams,
): Promise<OrderProfitApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;

  const rowSearch = new URLSearchParams();
  if (params.startDate) rowSearch.set("start_date", params.startDate);
  if (params.endDate) rowSearch.set("end_date", params.endDate);
  rowSearch.set("page", String(page));
  rowSearch.set("page_size", String(pageSize));

  const summarySearch = new URLSearchParams();
  if (params.startDate) summarySearch.set("start_date", params.startDate);
  if (params.endDate) summarySearch.set("end_date", params.endDate);
  summarySearch.set("page", "1");
  summarySearch.set("page_size", "1");

  const requestOptions = params.signal ? { signal: params.signal } : undefined;

  const [rowsEnvelope, summaryEnvelope] = await Promise.all([
    backendRequest<BackendDailySalesData, OrderProfitApiMeta>(
      `/api/sales/daily-sales?${rowSearch.toString()}`,
      requestOptions,
    ),
    backendRequest<BackendOrderProfitData, OrderProfitApiMeta>(
      `/api/sales/order-profit?${summarySearch.toString()}`,
      requestOptions,
    ),
  ]);

  const items = Array.isArray(rowsEnvelope.data.items) ? rowsEnvelope.data.items : [];

  return {
    records: items.map(toOrderProfitSourceRecord),
    summary: toOrderProfitServerSummary(summaryEnvelope.data.summary),
    meta: rowsEnvelope.meta,
  };
}

export function preloadOrderProfitSourceRecords(params: OrderProfitParams): void {
  void fetchOrderProfitSourceRecords(params).catch(() => undefined);
}
