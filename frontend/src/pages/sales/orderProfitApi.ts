import { backendRequest } from "@/api/backendApi";
import type { OrderProfitSourceRecord } from "@/pages/sales/orderProfitTypes";

interface BackendOrderProfitItem {
  id: string;
  business_date_la: string;
  local_sku: string;
  item_ids: string[];
  store_ids: string[];
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
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

interface BackendOrderProfitData {
  items: BackendOrderProfitItem[];
}

export interface OrderProfitApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
  partial: boolean;
  input_missing: boolean;
}

export interface OrderProfitApiResult {
  records: OrderProfitSourceRecord[];
  meta: OrderProfitApiMeta;
}

interface OrderProfitParams {
  startDate?: string;
  endDate?: string;
  pageSize?: number;
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const currencyLabel = (currencyCode: string | null): OrderProfitSourceRecord["currency"] => (
  currencyCode === "CNY" ? "CNY" : "USD"
);

const costStatusLabel = (
  status: BackendOrderProfitItem["cost_status"],
  missingCodes: string[],
): OrderProfitSourceRecord["costStatus"] => {
  if (missingCodes.length > 0) return "部分缺失";
  if (status === "complete") return "已完成";
  if (status === "partial") return "部分缺失";
  return "待补齐";
};

const firstOrFallback = (values: string[], fallback: string) => values[0] ?? fallback;

const toOrderProfitSourceRecord = (item: BackendOrderProfitItem): OrderProfitSourceRecord => ({
  id: item.id,
  date: item.business_date_la,
  store: firstOrFallback(item.store_ids, "全部店铺"),
  owner: "未分配",
  msku: "-",
  productId: firstOrFallback(item.item_ids, item.local_sku),
  sku: item.local_sku,
  productName: item.local_sku,
  platform: "Walmart",
  currency: currencyLabel(item.sales_currency_code),
  salesVolume: numberValue(item.sales_qty),
  orderCount: numberValue(item.order_count),
  salesAmount: numberValue(item.sales_amount),
  refundAmount: numberValue(item.refund_amount),
  adSpend: numberValue(item.ad_spend_amount),
  wfsDeliveryFee: numberValue(item.wfs_fee_total_amount),
  commission: numberValue(item.commission_fee_amount),
  purchaseCost: numberValue(item.purchase_cost_total_usd),
  firstLegCost: numberValue(item.first_leg_cost_total_usd),
  storageFee: numberValue(item.storage_fee_total_amount),
  costStatus: costStatusLabel(item.cost_status, item.missing_cost_codes),
});

export async function fetchOrderProfitSourceRecords(
  params: OrderProfitParams,
): Promise<OrderProfitApiResult> {
  const search = new URLSearchParams();
  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  search.set("page", "1");
  search.set("page_size", String(params.pageSize ?? 500));

  const envelope = await backendRequest<BackendOrderProfitData, OrderProfitApiMeta>(
    `/api/sales/order-profit?${search.toString()}`,
  );

  return {
    records: envelope.data.items.map(toOrderProfitSourceRecord),
    meta: envelope.meta,
  };
}
