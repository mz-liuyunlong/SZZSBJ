/** Binds real, RBAC-scoped clearance API facts into the exact pre-V2 UI model.
 * No demo data, fabricated financial values, state-table writes or CSS.
 */
import type { ClearanceListing } from "./clearanceApi";
import type { ClearanceProduct, PeriodDays, SalesPeriod } from "./clearanceModel";

function real(value: unknown): number {
  if (value === null || value === undefined || value === "") return Number.NaN;
  const n = Number(value);
  return Number.isFinite(n) ? n : Number.NaN;
}
function metric(row: ClearanceListing, key: string): number {
  return real(row.metrics[key]);
}
function period(row: ClearanceListing, days: PeriodDays): SalesPeriod {
  return {
    units: metric(row, `sales_${days}d`),
    revenue: metric(row, `revenue_${days}d_usd`),
    ads: metric(row, `ad_spend_${days}d_usd`),
    profit: metric(row, `profit_${days}d_usd`),
    adRate: Number.isFinite(metric(row, `ad_ratio_${days}d_percent`))
      ? metric(row, `ad_ratio_${days}d_percent`) : null,
    margin: Number.isFinite(metric(row, `margin_${days}d_percent`))
      ? metric(row, `margin_${days}d_percent`) : null,
  };
}
export function fromLiveListing(row: ClearanceListing): ClearanceProduct {
  const capital = metric(row, "capital_at_cost_usd");
  const available = real(row.available);
  // The original 'cost' field explicitly means purchase cost, which is
  // different from purchase + first-leg inventory valuation. Do not conflate.
  const risk = row.risk ?? "unknown";
  return {
    id: `${row.source_account_ref}::${row.store_id}::${row.item_id}`,
    item: row.item_id,
    sku: row.sku || "—",
    msku: row.msku || "—",
    // Prefer the real Product Management name for an exact mapped product.
    // Listing local_name can itself be a copy of the English marketing title.
    // Only use it when it is distinguishable from title; never use title as 品名.
    name: row.product_name?.trim() ||
      (row.local_name?.trim() && row.local_name.trim() !== row.title?.trim()
        ? row.local_name.trim() : "—"),
    store: row.store_name || row.store_id,
    owner: row.owner_name?.trim() || row.owner?.trim() || "未分配",
    avail: available,
    res: Number.NaN,
    bad: Number.NaN,
    inbound: Number.NaN,
    age: metric(row, "listing_days"), // Listing start-based age as requested; not warehouse lot age.
    listingDays: metric(row, "listing_days"),
    ageLots: [],
    returns: metric(row, "returns_30d"),
    rating: metric(row, "rating"),
    reviewCount: metric(row, "review_count"),
    price: real(row.price_amount),
    cost: metric(row, "purchase_unit_cost_usd"),
    liveCapitalAtCostUsd:Number.isFinite(capital)?capital:null,
    per: {7:period(row,7),14:period(row,14),30:period(row,30)},
    liveSelloutDays: row.metrics["sellout_is_infinite"] === true
      ? Number.POSITIVE_INFINITY
      : Number.isFinite(metric(row, "sellout_days")) ? metric(row, "sellout_days") : null,
    riskDetailPayload: row as unknown as { risk?: string; rule_hits?: unknown[]; evaluated_at?: string; time_evidence?: Record<string, unknown>; rule_version?: number },
    liveRisk: { level:risk, reasons:row.reasons, business:row.signals.map(x=>x.reason) },
  };
}
