/** Backend full-filter footer values; never derive totals from current table rows. */
export interface BackendReportTableTotals {
  usd: Record<string, string | number | null>;
  cny: Record<string, string | number | null>;
  sample_evidence?: "pending" | "unknown" | null;
}

export interface ReportTableTotals {
  usd: Record<string, number | null>;
  cny: Record<string, number | null>;
  sampleEvidence?: "pending" | "unknown" | null;
}

function parseValues(values: BackendReportTableTotals["usd"] | undefined) {
  return Object.fromEntries(Object.entries(values ?? {}).map(([key, value]) => {
    const number = value === null || value === "" ? null : Number(value);
    return [key, number !== null && Number.isFinite(number) ? number : null];
  }));
}

export function decodeReportTableTotals(data?: BackendReportTableTotals | null): ReportTableTotals | null {
  if (!data) return null;
  return { usd: parseValues(data.usd), cny: parseValues(data.cny), sampleEvidence: data.sample_evidence };
}

const footerFields: Readonly<Record<string, string>> = {
  salesVolume: "sales_qty", orderCount: "order_count", salesAmount: "sales_amount",
  averagePrice: "avg_price", sampleQuantity: "sample_qty", sampleExcludedAmount: "sample_amount",
  sampleAmount: "sample_amount", returnCount: "return_qty", refundQuantity: "return_qty",
  refundLossAmount: "refund_amount", returnRate30Days: "return_rate_30d",
  adSpend: "ad_spend", semAdSpend: "sem_ad_spend", totalAdSpend: "total_ad_spend", adRatio: "ad_ratio",
  wfsDeliveryFee: "wfs_fee_total", wfsLowPriceSurcharge: "wfs_low_price_surcharge", commission: "commission",
  purchaseCost: "purchase_cost_total", firstLegCost: "first_leg_cost_total", storageFee: "storage_fee_total",
  wfsAvailableInventory: "wfs_inventory", totalCost: "total_cost", orderProfit: "order_profit",
  averageProfitPerOrder: "avg_profit_per_order", profitMargin: "gross_margin", roi: "roi",
};

export function reportTotalValue(totals: ReportTableTotals | null | undefined, currency: "USD" | "CNY", columnKey: string): number | null {
  const key = footerFields[columnKey];
  if (!totals || !key) return null;
  return (currency === "CNY" ? totals.cny : totals.usd)[key] ?? null;
}
