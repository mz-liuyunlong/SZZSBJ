import { backendRequest } from "@/api/backendApi";
import type {
  DailySalesCurrency,
  DailySalesRefundSummary,
  DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

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
  gross_sales_qty: string;
  gross_order_count: string;
  gross_sales_amount: string;
  sample_order_count: string;
  sample_qty: string;
  cost_quantity: string;
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
  wfs_fee_expected_unit_amount: string | null;
  wfs_fee_expected_total_amount: string | null;
  wfs_fee_actual_total_amount: string | null;
  wfs_fee_variance_amount: string | null;
  wfs_fee_variance_rate: string | null;
  wfs_fee_source: string | null;
  purchase_cost_unit_cny: string | null;
  purchase_cost_total_usd: string | null;
  first_leg_cost_unit_cny: string | null;
  first_leg_cost_total_usd: string | null;
  storage_fee_unit_amount: string | null;
  storage_fee_total_amount: string | null;
  commission_fee_amount: string | null;
  commission_source: string | null;
  exchange_rate: string | null;
  fx_source: string | null;
  purchase_cost_source: string | null;
  first_leg_cost_source: string | null;
  storage_fee_source: string | null;
  gross_profit_amount: string | null;
  gross_margin: string | null;
  roi: string | null;
  cost_status: "complete" | "partial" | "missing";
  missing_cost_codes: string[];
  calculation_warnings: string[];
  sales_7d_trend: BackendTrendPoint[];
}

interface BackendDailySalesSummary {
  sales_qty: string;
  order_count: string;
  sales_amount: string;
  sales_currency_code: string | null;
  order_profit_amount: string;
  order_profit_currency_code: string | null;
  ad_spend_amount: string;
  ad_spend_currency_code: string | null;
  refund_event_qty: string;
  refund_event_amount: string;
  refund_event_currency_code: string | null;
  wfs_available_quantity: string | null;
}

interface BackendDailySalesData {
  items: BackendDailySalesItem[];
  summary?: BackendDailySalesSummary;
}

export interface DailySalesApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
  partial: boolean;
  input_missing: boolean;
}

export interface DailySalesServerSummary {
  salesQuantity: number;
  orderCount: number;
  salesAmount: number;
  salesCurrency: DailySalesCurrency;
  orderProfitAmount: number;
  orderProfitCurrency: DailySalesCurrency;
  adSpendAmount: number;
  adSpendCurrency: DailySalesCurrency;
  refundEventQuantity: number;
  refundEventAmount: number;
  refundEventCurrency: DailySalesCurrency;
  wfsAvailableInventory?: number | null;
}

export interface DailySalesApiResult {
  rows: DailySalesRow[];
  summary: DailySalesServerSummary | null;
  refundSummary: DailySalesRefundSummary | null;
  meta: DailySalesApiMeta;
}

interface DailySalesParams {
  startDate?: string;
  endDate?: string;
  page?: number;
  pageSize?: number;
  platforms?: string[];
  owners?: string[];
  stores?: string[];
  searchField?: string;
  keyword?: string;
  batchValues?: string[];
  signal?: AbortSignal;
}


const platformLabel = (platformCode: string | null): DailySalesRow["platform"] => {
  if (platformCode === "10008") return "Walmart";
  return "Walmart";
};

const currencyLabel = (currencyCode: string | null): DailySalesRow["currency"] => (
  currencyCode === "CNY" ? "CNY" : "USD"
);

const numberValue = (value: string | null | undefined) => Number(value ?? 0);
const nullableNumberValue = (value: string | null | undefined) => (
  value == null ? null : Number(value)
);

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
  grossSalesVolume: numberValue(item.gross_sales_qty),
  grossOrderCount: numberValue(item.gross_order_count),
  grossSalesAmount: numberValue(item.gross_sales_amount),
  sampleOrderCount: numberValue(item.sample_order_count),
  sampleQuantity: numberValue(item.sample_qty),
  sampleAmount: nullableNumberValue(item.sample_amount),
  costQuantity: numberValue(item.cost_quantity),
  salesVolume: numberValue(item.sales_qty),
  orderCount: numberValue(item.order_count),
  salesAmount: numberValue(item.sales_amount),
  sampleExcludedAmount: nullableNumberValue(item.sample_amount),
  returnCount: numberValue(item.return_qty),
  refundAmount: nullableNumberValue(item.refund_amount),
  returnRate30Days: numberValue(item.return_rate_30d) * 100,
  adSpend: numberValue(item.ad_spend_amount),
  adRatio: numberValue(item.ad_ratio) * 100,
  wfsDeliveryFee: nullableNumberValue(item.wfs_fee_total_amount),
  wfsDeliveryUnitPrice: nullableNumberValue(item.wfs_fee_unit_amount),
  wfsExpectedFee: numberValue(item.wfs_fee_expected_total_amount),
  wfsActualFee: item.wfs_fee_actual_total_amount == null ? null : numberValue(item.wfs_fee_actual_total_amount),
  wfsVarianceAmount: item.wfs_fee_variance_amount == null ? null : numberValue(item.wfs_fee_variance_amount),
  wfsVarianceRate: item.wfs_fee_variance_rate == null ? null : numberValue(item.wfs_fee_variance_rate) * 100,
  wfsFeeSource: item.wfs_fee_source ?? "product_management",
  commission: nullableNumberValue(item.commission_fee_amount),
  purchaseCost: nullableNumberValue(item.purchase_cost_total_usd),
  purchaseUnitPriceCny: nullableNumberValue(item.purchase_cost_unit_cny),
  firstLegCost: nullableNumberValue(item.first_leg_cost_total_usd),
  firstLegUnitPriceCny: nullableNumberValue(item.first_leg_cost_unit_cny),
  storageFee: nullableNumberValue(item.storage_fee_total_amount),
  storageUnitPrice: nullableNumberValue(item.storage_fee_unit_amount),
  wfsAvailableInventory: nullableNumberValue(item.wfs_available_quantity),
  legacyGrossProfit: nullableNumberValue(item.gross_profit_amount),
  orderProfit: nullableNumberValue(item.gross_profit_amount),
  profitMargin: item.gross_margin == null ? null : numberValue(item.gross_margin) * 100,
  roi: item.roi == null ? null : numberValue(item.roi) * 100,
  exchangeRate: numberValue(item.exchange_rate),
  fxSource: item.fx_source ?? "daily-sales-default-fx-6.6",
  commissionSource: item.commission_source ?? "default_15_percent",
  purchaseCostSource: item.purchase_cost_source ?? "product_management",
  firstLegCostSource: item.first_leg_cost_source ?? "product_management",
  storageFeeSource: item.storage_fee_source ?? "product_management",
  calculationWarnings: item.calculation_warnings,
  costStatus: costStatusLabel(item.cost_status, item.missing_cost_codes),
  systemOperationLog: "系统运营日志待接入",
  operationLog: "运营日志待接入",
});

const toDailySalesServerSummary = (
  summary: BackendDailySalesSummary | undefined,
): DailySalesServerSummary | null => {
  if (!summary) return null;

  return {
    salesQuantity: numberValue(summary.sales_qty),
    orderCount: numberValue(summary.order_count),
    salesAmount: numberValue(summary.sales_amount),
    salesCurrency: currencyLabel(summary.sales_currency_code),
    orderProfitAmount: numberValue(summary.order_profit_amount),
    orderProfitCurrency: currencyLabel(summary.order_profit_currency_code),
    adSpendAmount: numberValue(summary.ad_spend_amount),
    adSpendCurrency: currencyLabel(summary.ad_spend_currency_code),
    refundEventQuantity: numberValue(summary.refund_event_qty),
    refundEventAmount: numberValue(summary.refund_event_amount),
    refundEventCurrency: currencyLabel(summary.refund_event_currency_code),
    wfsAvailableInventory: nullableNumberValue(
      summary.wfs_available_quantity,
    ),
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

const appendDailySalesFilters = (search: URLSearchParams, params: DailySalesParams) => {
  appendMultiParam(search, "platform", params.platforms);
  appendMultiParam(search, "owner_ref", params.owners);
  appendMultiParam(search, "store_id", params.stores);
  appendMultiParam(search, "batch_values", params.batchValues);

  const keyword = params.keyword?.trim();
  const hasBatchValues = (params.batchValues ?? [])
    .map((value) => value.trim())
    .some(Boolean);

  if (keyword || hasBatchValues) {
    search.set("search_field", backendSearchField(params.searchField));
  }
  if (keyword) {
    search.set("keyword", keyword);
  }
};

async function fetchDailySalesRowsFromApi(
  params: DailySalesParams,
): Promise<DailySalesApiResult> {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;
  const search = new URLSearchParams();

  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  appendDailySalesFilters(search, params);
  search.set("page", String(page));
  search.set("page_size", String(pageSize));

  const envelope = await backendRequest<BackendDailySalesData, DailySalesApiMeta>(
    `/api/sales/daily-sales?${search.toString()}`,
    params.signal ? { signal: params.signal } : undefined,
  );

  const items = Array.isArray(envelope.data.items) ? envelope.data.items : [];
  const summary = toDailySalesServerSummary(envelope.data.summary);
  const refundSummary = summary
    ? {
        quantity: summary.refundEventQuantity,
        amount: summary.refundEventAmount,
        currency: summary.refundEventCurrency,
      }
    : null;

  return {
    rows: items.map(toDailySalesRow),
    summary,
    refundSummary,
    meta: envelope.meta,
  };
}




export function fetchDailySalesRows(
  params: DailySalesParams,
): Promise<DailySalesApiResult> {
  return fetchDailySalesRowsFromApi(params);
}


export function preloadDailySalesRows(params: DailySalesParams): void {
  void fetchDailySalesRows(params).catch(() => undefined);
}
