"""Pure deterministic WFS clearance risk evaluator; never submits a request.

UNKNOWN differs from zero. The unit tested function consumes source-backed
facts only, respects LA observed business days and deduplicates profit signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from typing import Any

from .rules import ClearanceRules

ZERO = Decimal("0")


@dataclass(frozen=True)
class SalesWindow:
    units: Decimal | None = None
    revenue: Decimal | None = None
    ads: Decimal | None = None
    profit: Decimal | None = None
    returns: Decimal | None = None
    observed_days: int = 0
    effective_days: int = 0
    complete: bool = False
    ad_clicks: int | None = None
    attributed_orders: int | None = None
    active_sales_days: int | None = None
    net_units: Decimal | None = None

    @property
    def margin_percent(self) -> Decimal | None:
        if not self.complete or self.revenue is None or self.revenue <= ZERO or self.profit is None:
            return None
        return self.profit / self.revenue * 100

    @property
    def ad_ratio_percent(self) -> Decimal | None:
        if not self.complete or self.ads is None or self.revenue is None or self.revenue <= ZERO:
            return None
        return self.ads / self.revenue * 100


@dataclass(frozen=True)
class ProductFacts:
    source_account_ref: str
    store_id: str
    item_id: str
    available: int | None
    first_wfs_days: int | None
    windows: dict[int, SalesWindow] = field(default_factory=dict)
    rating: Decimal | None = None
    review_count: int | None = None
    buybox: bool | None = None
    inbound_qty: int | None = None
    open_purchase_qty: int | None = None
    last_sale_days: int | None = None
    unit_inventory_cost_usd: Decimal | None = None
    fulfillment_fee_usd: Decimal | None = None
    commission_rate: Decimal | None = None
    current_price_usd: Decimal | None = None
    consecutive_risk_days: int | None = None
    holding_cost30_usd: Decimal | None = None


@dataclass(frozen=True)
class RiskOutcome:
    level: str
    reasons: list[str]
    signals: list[dict[str, str]]
    gaps: list[str]
    metrics: dict[str, Any]


def _metric(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def evaluate(f: ProductFacts, r: ClearanceRules) -> RiskOutcome:
    reasons: list[str] = []
    gaps: list[str] = []
    signals: dict[str, str] = {}
    priority: list[str] = []
    w7 = f.windows.get(7, SalesWindow())
    w14 = f.windows.get(14, SalesWindow())
    w30 = f.windows.get(30, SalesWindow())
    wc = f.windows.get(r.coverageLookback, SalesWindow())
    wz = f.windows.get(r.zeroLookback, SalesWindow())
    coverage: int | None = None
    high = False
    medium = False
    has_decision_data = False

    if f.available is None:
        return RiskOutcome("unknown", ["WFS可售库存数据缺失"], [], ["wfs_available_quantity"], {"available": None})
    if f.available <= 0:
        return RiskOutcome("low", ["WFS可售库存为0，不进入风险候选"], [], [], {"available": f.available})

    if f.first_wfs_days is None:
        gaps.append("first_wfs_available_date_la")

    if wc.complete and wc.units is not None and wc.effective_days > 0:
        has_decision_data = True
        if wc.units > ZERO:
            coverage = int((Decimal(f.available) * wc.effective_days / wc.units).to_integral_value(rounding=ROUND_CEILING))
        # Verified zero sales has no finite sellout estimate.
    else:
        gaps.append(f"sales_{r.coverageLookback}d_completeness")
    if r.enableZero:
        if f.first_wfs_days is None or not wz.complete or wz.units is None:
            gaps.append(f"zero_sales_{r.zeroLookback}d_evidence")
        elif f.first_wfs_days >= r.minListingDays:
            has_decision_data = True
            if wz.units == ZERO:
                high = True
                reasons.append(f"已达到最低上架天数，近{r.zeroLookback}天经核实零销量")
    if r.enableCoverage:
        if coverage is not None:
            has_decision_data = True
            if coverage >= r.highCoverage:
                high = True
                reasons.append(f"预计售罄{coverage}天，达到高风险{r.highCoverage}天")
            elif coverage >= r.mediumCoverage:
                medium = True
                reasons.append(f"预计售罄{coverage}天，达到中风险{r.mediumCoverage}天")

    # Two independent toggles, one profit-related anomaly category.
    if r.enableProfit and w7.complete and w14.complete and w7.profit is not None and w14.profit is not None and w14.units is not None:
        if w7.profit < ZERO and w14.profit < ZERO and w14.units >= 3:
            signals["profit"] = "近7天、近14天持续亏损"
    if r.enableMargin30 and w30.margin_percent is not None and w30.margin_percent < Decimal(str(r.margin30Threshold)):
        signals["profit"] = (signals.get("profit", "") + "；" if "profit" in signals else "") + f"30天利润率低于{r.margin30Threshold}%"

    if r.enableDecline and w7.complete and w14.complete and w7.units is not None and w14.units is not None:
        baseline = w14.units - w7.units
        decline = baseline - w7.units
        if baseline >= r.minBaselineSales7 and decline >= r.minSalesDropUnits7 and decline * 100 >= baseline * Decimal(str(r.salesDropPercent)):
            signals["sales_decline"] = f"近7天销量较前7天下降至少{r.salesDropPercent}%"
    if r.enableAd and w7.ad_ratio_percent is not None and w30.ad_ratio_percent is not None and w7.profit is not None:
        if w7.ad_ratio_percent - w30.ad_ratio_percent >= Decimal(str(r.adRateIncrease)) and w7.profit < ZERO:
            signals["advertising"] = f"广告费占比上升至少{r.adRateIncrease}个百分点且近7天亏损"
    if r.enableReturns and w30.complete and w30.units is not None and w30.returns is not None:
        if w30.units >= r.minReturnSales30 and w30.returns >= r.minReturns30 and w30.units > ZERO:
            if w30.returns * 100 / w30.units >= Decimal(str(r.returnRate)):
                signals["returns"] = f"30天退货率达到{r.returnRate}%"
    if r.enableRating and f.rating is not None and f.review_count is not None:
        if f.review_count >= r.minReviewCount and f.rating < Decimal(str(r.ratingThreshold)):
            signals["rating"] = f"Listing评分低于{r.ratingThreshold}分"
    if r.enableAdConversion and w30.ad_clicks is not None and w30.attributed_orders is not None and w30.ad_clicks >= r.minAdClicks30:
        if Decimal(w30.attributed_orders) * 100 / w30.ad_clicks < Decimal(str(r.maxAdConversionPercent)):
            signals["ad_conversion"] = "广告点击充足但转化率过低"
    if r.enableNetSales and w30.net_units is not None and w30.complete and w30.net_units <= r.maxNetUnits30:
        signals["net_sales"] = "30天净销量偏低"
    # Last-sale and active-days warnings require inventory coverage; no standalone admission.
    if coverage is not None and coverage >= r.assistCoverage:
        if r.enableLastSale and f.last_sale_days is not None and f.last_sale_days >= r.lastSaleDaysLimit:
            medium = True
            reasons.append(f"最后出单距今{f.last_sale_days}天且库存积压")
        if r.enableActiveDays and w30.complete and w30.active_sales_days is not None and w30.active_sales_days <= r.maxActiveSalesDays30:
            medium = True
            reasons.append("30天有效出单天数过少且库存积压")
        if r.enableAssisted and len(signals) >= r.minBusinessSignals:
            medium = True
            reasons.append(f"预计售罄不少于{r.assistCoverage}天，命中{len(signals)}类经营异常")

    # Explicit hard risk is immutable under protection. Protection handles ordinary medium only.
    if not high and medium:
        protection: list[str] = []
        if r.enableNewProductProtection and f.first_wfs_days is not None and f.first_wfs_days < r.newProductProtectionDays:
            protection.append(f"新品保护期{r.newProductProtectionDays}天")
        if r.enableRecoveryProtection and w7.complete and w14.complete and w7.units is not None and w14.units is not None:
            baseline = w14.units - w7.units
            if baseline >= r.minSalesForRecovery and w7.units >= r.minSalesForRecovery and w7.units * 100 >= baseline * (100 + Decimal(str(r.salesRecoveryPercent))):
                protection.append("近7天销量恢复保护")
        if r.enableBuyBoxProtection and f.buybox is False:
            protection.append("Buy Box状态异常保护")
        if protection:
            medium = False
            reasons.append("；".join(protection) + "，暂缓普通中风险入池")

    if r.enableCapitalPriority and f.unit_inventory_cost_usd is not None and f.available * f.unit_inventory_cost_usd >= Decimal(str(r.minStockCapital)):
        priority.append("库存资金占用较高")
    if r.enableInboundConflict and f.inbound_qty is not None and f.inbound_qty >= r.inboundConflictMin and (coverage is None or coverage >= r.assistCoverage):
        priority.append("存在在途补货，建议与采购协调")
    if r.enablePurchaseConflict and f.open_purchase_qty is not None and f.open_purchase_qty >= r.purchaseConflictMin:
        priority.append("存在尚未完成的采购任务")
    if r.enableRiskDuration and f.consecutive_risk_days is not None and f.consecutive_risk_days >= r.riskDaysThreshold:
        priority.append("风险持续天数较长")
    if r.enableHoldingCost and f.holding_cost30_usd is not None and f.holding_cost30_usd >= Decimal(str(r.holdingCost30Threshold)):
        priority.append("预计30天持有费用较高")
    reasons += [x + "（仅影响优先级）" for x in priority]

    suggested_qty: int | None = None
    if r.enableQtySuggestion and wc.complete and wc.units is not None and wc.effective_days > 0:
        demand = int((wc.units * r.targetHoldingDays / wc.effective_days).to_integral_value(rounding=ROUND_CEILING))
        suggested_qty = max(0, min(f.available, f.available - demand - r.safetyStockUnits))
    floor_price: Decimal | None = None
    if (r.enableFloorPrice and f.unit_inventory_cost_usd is not None and f.fulfillment_fee_usd is not None
        and f.commission_rate is not None and ZERO <= f.commission_rate < 1):
        floor_price = max(ZERO, (f.unit_inventory_cost_usd + f.fulfillment_fee_usd - Decimal(str(r.allowedClearanceLoss))) / (1 - f.commission_rate))
        floor_price = floor_price.quantize(Decimal("0.01"), rounding=ROUND_CEILING)

    level = "high" if high else "medium" if medium else "low" if has_decision_data else "unknown"
    if level == "unknown":
        reasons.append("可用数据不足，风险待评估")
    elif level == "low" and not reasons:
        reasons.append("尚未达到风险候选条件")
    metrics = {
        "wfs_available": f.available,
        "listing_days": f.first_wfs_days,
        "sellout_days": coverage,
        "coverage_lookback": r.coverageLookback,
        "sales_7d": _metric(w7.units),
        "sales_14d": _metric(w14.units),
        "sales_30d": _metric(w30.units),
        "profit_7d_usd": _metric(w7.profit),
        "profit_14d_usd": _metric(w14.profit),
        "profit_30d_usd": _metric(w30.profit),
        "margin_30d_percent": _metric(w30.margin_percent),
        "ad_ratio_7d_percent": _metric(w7.ad_ratio_percent),
        "ad_ratio_30d_percent": _metric(w30.ad_ratio_percent),
        "returns_30d": _metric(w30.returns),
        "capital_at_cost_usd": _metric(f.unit_inventory_cost_usd * f.available if f.unit_inventory_cost_usd is not None else None),
        "unit_inventory_cost_usd": _metric(f.unit_inventory_cost_usd),
        "unit_full_sale_cost_usd": _metric(f.unit_inventory_cost_usd + f.fulfillment_fee_usd + (f.current_price_usd * f.commission_rate) if all(x is not None for x in (f.unit_inventory_cost_usd, f.fulfillment_fee_usd, f.current_price_usd, f.commission_rate)) else None),
        "unit_margin_usd": _metric(f.current_price_usd - (f.unit_inventory_cost_usd + f.fulfillment_fee_usd + (f.current_price_usd * f.commission_rate)) if all(x is not None for x in (f.unit_inventory_cost_usd, f.fulfillment_fee_usd, f.current_price_usd, f.commission_rate)) else None),
        "suggested_clearance_qty": suggested_qty,
        "suggested_floor_price_usd": _metric(floor_price),
        "rating": _metric(f.rating),
        "review_count": f.review_count,
        "has_buybox": f.buybox,
        "inbound_qty": f.inbound_qty,
        "priority_reasons": priority,
    }
    return RiskOutcome(level, reasons, [{"kind": k, "reason": v} for k, v in signals.items()], sorted(set(gaps)), metrics)
