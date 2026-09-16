import { backendRequest } from "@/api/backendApi";
import type { DailySalesRow } from "@/pages/sales/dailySalesTypes";

interface BackendTrendPoint {
  date: string;
  sales_qty: string;
}

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
  sample_amount: string | null;
  sales_amount_excluding_sample: string | null;
  return_qty: string | null;
  refund_amount: string | null;
  return_rate_30d: string | null;
  ad_spend_amount: string | null;
  ad_ratio: string | null;
  wfs_available_quantity: string | null;
  wfs_fee_unit_amount: string | null;
  wfs_fee_total_amount: string | null;
  purchase_cost_unit_cny: string | null;
  purchase_cost_total_usd: string | null;
  first_leg_cost_unit_cny: string | null;
  first_leg_cost_total_usd: string | null;
  storage_fee_unit_amount: string | null;
  storage_fee_total_amount: string | null;
  commission_fee_amount: string | null;
  gross_profit_amount: string | null;
  gross_margin: string | null;
  roi: string | null;
  cost_status: "complete" | "partial" | "missing";
  missing_cost_codes: string[];
  sales_7d_trend: BackendTrendPoint[];
}

interface BackendDailySalesData {
  items: BackendDailySalesItem[];
}

export interface DailySalesApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
  partial: boolean;
  input_missing: boolean;
}

export interface DailySalesApiResult {
  rows: DailySalesRow[];
  meta: DailySalesApiMeta;
}

interface DailySalesParams {
  startDate?: string;
  endDate?: string;
  pageSize?: number;
}

const platformLabel = (platformCode: string | null): DailySalesRow["platform"] => {
  if (platformCode === "10008") return "Walmart";
  return "Walmart";
};

const currencyLabel = (currencyCode: string | null): DailySalesRow["currency"] => (
  currencyCode === "CNY" ? "CNY" : "USD"
);

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const costStatusLabel = (
  status: BackendDailySalesItem["cost_status"],
  missingCodes: string[],
): DailySalesRow["costStatus"] => {
  if (missingCodes.length > 0) return "部分缺失";
  if (status === "complete") return "已完成";
  if (status === "partial") return "部分缺失";
  return "待补齐";
};

const toDailySalesRow = (item: BackendDailySalesItem): DailySalesRow => ({
  id: item.id,
  date: item.business_date_la,
  store: item.store_name ?? item.store_id,
  owner: item.owner_ref ?? "未分配",
  sevenDayDates: item.sales_7d_trend.map((point) => point.date),
  sevenDaySales: item.sales_7d_trend.map((point) => numberValue(point.sales_qty)),
  msku: item.msku ?? "-",
  productId: item.item_id,
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? item.title ?? "-",
  platform: platformLabel(item.platform_code),
  currency: currencyLabel(item.sales_currency_code),
  salesVolume: numberValue(item.sales_qty),
  orderCount: numberValue(item.order_count),
  salesAmount: numberValue(item.sales_amount),
  sampleExcludedAmount: numberValue(item.sales_amount_excluding_sample),
  returnCount: numberValue(item.return_qty),
  refundAmount: numberValue(item.refund_amount),
  returnRate30Days: numberValue(item.return_rate_30d) * 100,
  adSpend: numberValue(item.ad_spend_amount),
  adRatio: numberValue(item.ad_ratio) * 100,
  wfsDeliveryFee: numberValue(item.wfs_fee_total_amount),
  wfsDeliveryUnitPrice: numberValue(item.wfs_fee_unit_amount),
  commission: numberValue(item.commission_fee_amount),
  purchaseCost: numberValue(item.purchase_cost_total_usd),
  purchaseUnitPriceCny: numberValue(item.purchase_cost_unit_cny),
  firstLegCost: numberValue(item.first_leg_cost_total_usd),
  firstLegUnitPriceCny: numberValue(item.first_leg_cost_unit_cny),
  storageFee: numberValue(item.storage_fee_total_amount),
  storageUnitPrice: numberValue(item.storage_fee_unit_amount),
  wfsAvailableInventory: numberValue(item.wfs_available_quantity),
  legacyGrossProfit: numberValue(item.gross_profit_amount),
  orderProfit: numberValue(item.gross_profit_amount),
  profitMargin: numberValue(item.gross_margin) * 100,
  roi: numberValue(item.roi) * 100,
  costStatus: costStatusLabel(item.cost_status, item.missing_cost_codes),
  systemOperationLog: "系统运营日志待接入",
  operationLog: "运营日志待接入",
});

export async function fetchDailySalesRows(params: DailySalesParams): Promise<DailySalesApiResult> {
  const search = new URLSearchParams();
  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  search.set("page", "1");
  search.set("page_size", String(params.pageSize ?? 500));

  const envelope = await backendRequest<BackendDailySalesData, DailySalesApiMeta>(
    `/api/sales/daily-sales?${search.toString()}`,
  );

  return {
    rows: envelope.data.items.map(toDailySalesRow),
    meta: envelope.meta,
  };
}
