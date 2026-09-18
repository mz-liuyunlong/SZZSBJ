import { backendRequest } from "@/api/backendApi";
import type { OrderProfitSourceRecord } from "@/pages/sales/orderProfitTypes";

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

const MAX_API_PAGES = 10_000;
const numberValue = (value: string | null | undefined) => Number(value ?? 0);
const nullableNumberValue = (value: string | null | undefined) => (
  value == null ? null : Number(value)
);

const currencyLabel = (currencyCode: string | null): OrderProfitSourceRecord["currency"] => (
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

export async function fetchOrderProfitSourceRecords(
  params: OrderProfitParams,
): Promise<OrderProfitApiResult> {
  const pageSize = params.pageSize ?? 500;
  const items: BackendDailySalesItem[] = [];
  let firstMeta: OrderProfitApiMeta | null = null;

  for (let page = 1; page <= MAX_API_PAGES; page += 1) {
    const search = new URLSearchParams();
    if (params.startDate) search.set("start_date", params.startDate);
    if (params.endDate) search.set("end_date", params.endDate);
    search.set("page", String(page));
    search.set("page_size", String(pageSize));

    const envelope = await backendRequest<BackendDailySalesData, OrderProfitApiMeta>(
      `/api/sales/daily-sales?${search.toString()}`,
    );

    firstMeta ??= envelope.meta;
    items.push(...envelope.data.items);

    if (
      envelope.data.items.length === 0 ||
      items.length >= envelope.meta.total ||
      envelope.data.items.length < envelope.meta.page_size
    ) {
      const meta = firstMeta ?? envelope.meta;
      return {
        records: items.map(toOrderProfitSourceRecord),
        meta: {
          ...meta,
          page: 1,
          page_size: items.length,
          total: envelope.meta.total,
          partial: meta.partial || envelope.meta.partial,
          input_missing: meta.input_missing || envelope.meta.input_missing,
        },
      };
    }
  }

  throw new Error("Order Profit source pagination exceeded the safety limit");
}
