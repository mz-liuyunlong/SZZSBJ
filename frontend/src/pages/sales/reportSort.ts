/** Single active server-side sort for the sales report tables. */
export type SalesReportSort = { field: string; direction: "asc" | "desc" };
export type SalesSortCurrency = "USD" | "CNY";

const common = {
  platform: "platform", salesVolume: "sales_qty",
  orderCount: "order_count", salesAmount: "sales_amount", averagePrice: "avg_price",
  sampleQuantity: "sample_qty", refundLossAmount: "refund_amount", returnRate30Days: "return_rate_30d",
  adSpend: "ad_spend", semAdSpend: "sem_ad_spend", totalAdSpend: "total_ad_spend", adRatio: "ad_ratio",
  wfsDeliveryFee: "wfs_fee_total", wfsLowPriceSurcharge: "wfs_low_price_surcharge",
  wfsDeliveryUnitPrice: "wfs_fee_unit", commission: "commission", purchaseCost: "purchase_cost_total",
  purchaseUnitPriceCny: "purchase_unit_cny", firstLegCost: "first_leg_cost_total",
  firstLegUnitPriceCny: "first_leg_unit_cny", storageFee: "storage_fee_total", storageUnitPrice: "storage_unit",
  wfsAvailableInventory: "wfs_inventory", orderProfit: "order_profit", profitMargin: "gross_margin",
  roi: "roi", costStatus: "cost_status",
};
export const dailySalesSortFields: Readonly<Record<string, string>> = {
  ...common, date: "period",
  sampleExcludedAmount: "sample_amount", returnCount: "return_qty",
};
export const orderProfitSortFields: Readonly<Record<string, string>> = {
  ...common, sampleAmount: "sample_amount",
  refundQuantity: "return_qty", totalCost: "total_cost", averageProfitPerOrder: "avg_profit_per_order",
};

export function nextSalesReportSort(current: SalesReportSort | null, field: string): SalesReportSort | null {
  if (current?.field !== field) return { field, direction: "asc" };
  return current.direction === "asc" ? { field, direction: "desc" } : null;
}

export function appendSalesReportSort(search: URLSearchParams, sort?: SalesReportSort | null, currency?: SalesSortCurrency) {
  if (!sort) return;
  search.set("sort_field", sort.field);
  search.set("sort_direction", sort.direction);
  search.set("sort_currency", currency ?? "USD");
}
