from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

CENT = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
SIX_PLACES = Decimal("0.000001")
CM_PER_INCH = Decimal("2.54")
CUBIC_INCHES_PER_CUBIC_FOOT = Decimal("1728")


@dataclass(frozen=True, slots=True)
class ListingWfsOverride:
    listing_id: UUID
    amount: Decimal | None
    currency_code: str | None
    is_primary: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class WfsFulfillmentRate:
    rate_key: str
    amount: Decimal
    currency_code: Literal["USD", "CNY"]
    min_weight_kg: Decimal | None = None
    max_weight_kg: Decimal | None = None
    max_longest_side_cm: Decimal | None = None


@dataclass(frozen=True, slots=True)
class IdentityWfsOverride:
    identity_id: UUID
    amount: Decimal
    currency_code: Literal["USD", "CNY"]
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class WfsFeeResult:
    status: Literal["ok", "missing_rate", "missing_dimension", "missing_weight", "needs_confirm"]
    reason: str | None
    source: str
    amount: Decimal | None
    currency_code: str | None
    rule_key: str | None = None


@dataclass(frozen=True, slots=True)
class StorageResult:
    status: Literal["ok", "missing_rate", "missing_dimension"]
    package_volume_cuft: Decimal | None
    daily_fee_usd: Decimal | None
    estimated_fee_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class PricingRule:
    usd_cny_rate: Decimal | None
    platform_commission_rate: Decimal | None
    first_leg_cost_per_kg_cny: Decimal
    suggested_margin: Decimal
    minimum_margin: Decimal
    clearance_margin: Decimal
    storage_month_basis_days: int
    pricing_storage_days: int
    include_first_leg_fee: bool
    include_wfs_fulfillment_fee: bool
    include_storage_fee: bool
    other_fixed_cost_cny: Decimal
    roi_base: Literal["purchase_cost", "total_cost"]
    grade_a_min_margin: Decimal
    grade_a_min_roi: Decimal
    grade_b_min_margin: Decimal
    grade_b_min_roi: Decimal
    rounding_mode: Literal["none"] = "none"


@dataclass(frozen=True, slots=True)
class PricingResult:
    status: str
    first_leg_status: str
    first_leg_fee_cny: Decimal | None
    suggested_price_usd: Decimal | None
    minimum_price_usd: Decimal | None
    clearance_price_usd: Decimal | None
    suggested_gross_margin_rate: Decimal | None
    suggested_roi: Decimal | None
    product_grade: str
    grade_reason: str
    commission_source: str
    breakdown: dict[str, object]


def select_wfs_fee(
    *,
    identity_id: UUID,
    identity_overrides: tuple[IdentityWfsOverride, ...],
    listing_overrides: tuple[ListingWfsOverride, ...],
    rates: tuple[WfsFulfillmentRate, ...],
    gross_weight_kg: Decimal | None,
    dimensions_cm: tuple[Decimal | None, Decimal | None, Decimal | None],
) -> WfsFeeResult:
    identity_matches = [
        item for item in identity_overrides if item.identity_id == identity_id and item.is_active
    ]
    if len(identity_matches) > 1:
        return _wfs_conflict()
    if identity_matches:
        identity_item = identity_matches[0]
        return WfsFeeResult(
            "ok",
            None,
            "manual_sku_override",
            _money(identity_item.amount),
            identity_item.currency_code,
        )

    active = [
        item
        for item in listing_overrides
        if item.is_active and item.amount is not None and item.currency_code is not None
    ]
    primary = [item for item in active if item.is_primary]
    if len(primary) == 1:
        listing_item = primary[0]
        assert listing_item.amount is not None
        return WfsFeeResult(
            "ok",
            None,
            "manual_primary_listing_override",
            _money(listing_item.amount),
            listing_item.currency_code,
        )
    if len(primary) > 1:
        return _wfs_conflict()
    if len(active) == 1:
        listing_item = active[0]
        assert listing_item.amount is not None
        return WfsFeeResult(
            "ok",
            None,
            "manual_single_listing_override",
            _money(listing_item.amount),
            listing_item.currency_code,
        )
    if len(active) > 1:
        values = {(item.amount, item.currency_code) for item in active}
        if len(values) != 1:
            return _wfs_conflict()
        amount, currency = values.pop()
        assert amount is not None
        return WfsFeeResult(
            "ok", None, "manual_consistent_listing_override", _money(amount), currency
        )

    if not rates:
        return WfsFeeResult(
            "missing_rate", "rate_config_not_available", "calculated_rule", None, None
        )
    needs_weight = any(
        rate.min_weight_kg is not None or rate.max_weight_kg is not None for rate in rates
    )
    if needs_weight and (gross_weight_kg is None or gross_weight_kg <= 0):
        return WfsFeeResult("missing_weight", "gross_weight_missing", "calculated_rule", None, None)
    needs_dimension = any(rate.max_longest_side_cm is not None for rate in rates)
    if needs_dimension and any(value is None or value <= 0 for value in dimensions_cm):
        return WfsFeeResult(
            "missing_dimension", "package_dimension_missing", "calculated_rule", None, None
        )
    longest = max((value for value in dimensions_cm if value is not None), default=None)
    matches: list[WfsFulfillmentRate] = []
    for rate in rates:
        if rate.amount < 0:
            continue
        if rate.min_weight_kg is not None and gross_weight_kg is not None:
            if gross_weight_kg < rate.min_weight_kg:
                continue
        if rate.max_weight_kg is not None and gross_weight_kg is not None:
            if gross_weight_kg > rate.max_weight_kg:
                continue
        if rate.max_longest_side_cm is not None and longest is not None:
            if longest > rate.max_longest_side_cm:
                continue
        matches.append(rate)
    if len(matches) > 1:
        return WfsFeeResult(
            "needs_confirm",
            "multiple_matching_wfs_rates",
            "needs_confirm",
            None,
            None,
        )
    if matches:
        rate = matches[0]
        return WfsFeeResult(
            "ok", None, "calculated_rule", _money(rate.amount), rate.currency_code, rate.rate_key
        )
    return WfsFeeResult(
        "missing_rate", "matching_rate_not_available", "calculated_rule", None, None
    )


def calculate_storage(
    *,
    dimensions_cm: tuple[Decimal | None, Decimal | None, Decimal | None],
    monthly_rate_usd_per_cuft: Decimal | None,
    storage_month_basis_days: int,
    pricing_storage_days: int,
) -> StorageResult:
    if monthly_rate_usd_per_cuft is None:
        return StorageResult("missing_rate", None, None, None)
    if any(value is None or value <= 0 for value in dimensions_cm):
        return StorageResult("missing_dimension", None, None, None)
    if monthly_rate_usd_per_cuft < 0 or storage_month_basis_days <= 0 or pricing_storage_days < 0:
        return StorageResult("missing_rate", None, None, None)
    length, width, height = (value for value in dimensions_cm if value is not None)
    volume_cuft = (
        (length / CM_PER_INCH)
        * (width / CM_PER_INCH)
        * (height / CM_PER_INCH)
        / CUBIC_INCHES_PER_CUBIC_FOOT
    )
    daily = volume_cuft * monthly_rate_usd_per_cuft / Decimal(storage_month_basis_days)
    return StorageResult(
        "ok",
        volume_cuft.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
        _money(daily),
        _money(daily * Decimal(pricing_storage_days)),
    )


def calculate_pricing(
    *,
    purchase_cost_cny: Decimal | None,
    gross_weight_kg: Decimal | None,
    wfs: WfsFeeResult,
    storage: StorageResult,
    rule: PricingRule,
    manual_min_price_usd: Decimal | None = None,
    purchase_cost_source: str = "input",
) -> PricingResult:
    commission_rate = rule.platform_commission_rate or Decimal(0)
    commission_source = "default_zero" if rule.platform_commission_rate is None else "configured"
    first_leg_fee: Decimal | None = None
    first_leg_status = "not_included" if not rule.include_first_leg_fee else "not_calculated"

    def failure(status: str) -> PricingResult:
        return _pricing_failure(
            status,
            commission_source,
            wfs,
            storage,
            rule=rule,
            purchase_cost_cny=purchase_cost_cny,
            purchase_cost_source=purchase_cost_source,
            first_leg_fee_cny=first_leg_fee,
            first_leg_status=first_leg_status,
        )

    if rule.usd_cny_rate is None:
        return failure("missing_fx_rate")
    if purchase_cost_cny is None:
        return failure("missing_purchase_cost")
    if rule.include_first_leg_fee:
        if gross_weight_kg is None or gross_weight_kg <= 0:
            first_leg_status = "missing_weight"
            return failure("missing_weight")
        first_leg_fee = (gross_weight_kg * rule.first_leg_cost_per_kg_cny).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        first_leg_status = "ok"
    if rule.include_wfs_fulfillment_fee and wfs.status != "ok":
        wfs_status = "missing_wfs_rate" if wfs.status == "missing_rate" else wfs.status
        return failure(wfs_status)
    if rule.include_storage_fee and storage.status != "ok":
        storage_status = (
            "missing_storage_rate" if storage.status == "missing_rate" else storage.status
        )
        return failure(storage_status)
    if not (rule.suggested_margin >= rule.minimum_margin >= rule.clearance_margin):
        return failure("invalid_pricing_rule_config")

    wfs_cny = _to_cny(wfs.amount, wfs.currency_code, rule.usd_cny_rate)
    if rule.include_wfs_fulfillment_fee and wfs_cny is None:
        return failure("needs_confirm")
    storage_cny = (
        _money(storage.estimated_fee_usd * rule.usd_cny_rate)
        if storage.estimated_fee_usd is not None
        else None
    )
    included_costs = purchase_cost_cny + rule.other_fixed_cost_cny
    if rule.include_first_leg_fee and first_leg_fee is not None:
        included_costs += first_leg_fee
    if rule.include_wfs_fulfillment_fee and wfs_cny is not None:
        included_costs += wfs_cny
    if rule.include_storage_fee and storage_cny is not None:
        included_costs += storage_cny
    included_costs = _money(included_costs)

    prices: list[Decimal] = []
    targets = (rule.suggested_margin, rule.minimum_margin, rule.clearance_margin)
    price_breakdowns: list[dict[str, object]] = []
    for target in targets:
        denominator = rule.usd_cny_rate * (Decimal(1) - commission_rate - target)
        if denominator <= 0:
            return failure("invalid_pricing_denominator")
        raw_price = included_costs / denominator
        final_price = _round_price_up(raw_price)
        prices.append(final_price)
        price_breakdowns.append(
            {
                "target_margin_rate": _decimal_text(target),
                "denominator": _decimal_text(denominator),
                "raw_price_usd": _decimal_text(raw_price),
                "final_price_usd": _decimal_text(final_price),
                "rounding_mode": rule.rounding_mode,
                "source": "calculated_rule",
            }
        )
    if manual_min_price_usd is not None:
        floor = max(prices[2], _round_price_up(manual_min_price_usd))
        calculated_prices = prices
        prices = [max(price, floor) for price in calculated_prices]
        for index, price in enumerate(prices):
            price_breakdowns[index]["final_price_usd"] = _decimal_text(price)
            price_breakdowns[index]["source"] = (
                "manual_override" if price > calculated_prices[index] else "calculated_rule"
            )
    if not prices[0] >= prices[1] >= prices[2]:
        return failure("invalid_pricing_rule_config")

    revenue = prices[0] * rule.usd_cny_rate
    if revenue <= 0:
        return failure("invalid_revenue")
    commission = revenue * commission_rate
    gross_profit = revenue - commission - included_costs
    margin = gross_profit / revenue
    roi_denominator = purchase_cost_cny if rule.roi_base == "purchase_cost" else included_costs
    if roi_denominator <= 0:
        roi_status = (
            "missing_purchase_cost" if rule.roi_base == "purchase_cost" else "invalid_roi_base"
        )
        return failure(roi_status)
    roi = gross_profit / roi_denominator
    grade = "C"
    if margin >= rule.grade_a_min_margin and roi >= rule.grade_a_min_roi:
        grade = "A"
    elif margin >= rule.grade_b_min_margin and roi >= rule.grade_b_min_roi:
        grade = "B"

    breakdown: dict[str, object] = {
        "currency_code": "CNY",
        "price_currency_code": "USD",
        "usd_cny_rate": _decimal_text(rule.usd_cny_rate),
        "commission_source": commission_source,
        "platform_commission_rate": _decimal_text(commission_rate),
        "purchase_cost_cny": _decimal_text(purchase_cost_cny),
        "purchase_cost_source": purchase_cost_source,
        "first_leg_fee_cny": _optional_decimal_text(first_leg_fee),
        "first_leg_included": rule.include_first_leg_fee,
        "wfs_fulfillment_fee_cny": _optional_decimal_text(wfs_cny),
        "wfs_fee_source": wfs.source,
        "wfs_included": rule.include_wfs_fulfillment_fee,
        "package_volume_cuft": _optional_decimal_text(storage.package_volume_cuft),
        "daily_storage_fee_per_unit_usd": _optional_decimal_text(storage.daily_fee_usd),
        "daily_storage_fee_per_unit_cny": _optional_decimal_text(
            _money(storage.daily_fee_usd * rule.usd_cny_rate)
            if storage.daily_fee_usd is not None
            else None
        ),
        "estimated_storage_fee_usd": _optional_decimal_text(storage.estimated_fee_usd),
        "estimated_storage_fee_cny": _optional_decimal_text(storage_cny),
        "storage_included": rule.include_storage_fee,
        "other_fixed_cost_cny": _decimal_text(rule.other_fixed_cost_cny),
        "included_costs_cny": _decimal_text(included_costs),
        "revenue_cny": _decimal_text(revenue),
        "commission_cny": _decimal_text(commission),
        "gross_profit_cny": _decimal_text(gross_profit),
        "gross_margin_rate": _decimal_text(margin),
        "roi": _decimal_text(roi),
        "roi_base": rule.roi_base,
        "price_calculations": price_breakdowns,
        "manual_min_price_usd": _optional_decimal_text(manual_min_price_usd),
        "components": _cost_components(
            rule=rule,
            purchase_cost_cny=purchase_cost_cny,
            purchase_cost_source=purchase_cost_source,
            first_leg_fee_cny=first_leg_fee,
            first_leg_status=first_leg_status,
            wfs=wfs,
            storage=storage,
            commission_cny=commission,
            commission_source=commission_source,
        ),
    }
    return PricingResult(
        status="ok",
        first_leg_status=first_leg_status,
        first_leg_fee_cny=first_leg_fee,
        suggested_price_usd=prices[0],
        minimum_price_usd=prices[1],
        clearance_price_usd=prices[2],
        suggested_gross_margin_rate=margin.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
        suggested_roi=roi.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
        product_grade=grade,
        grade_reason=f"calculated_grade_{grade.lower()}",
        commission_source=commission_source,
        breakdown=breakdown,
    )


def _wfs_conflict() -> WfsFeeResult:
    return WfsFeeResult(
        "needs_confirm",
        "multiple_listing_wfs_overrides",
        "needs_confirm",
        None,
        None,
    )


def _pricing_failure(
    status: str,
    commission_source: str,
    wfs: WfsFeeResult,
    storage: StorageResult,
    *,
    rule: PricingRule,
    purchase_cost_cny: Decimal | None,
    purchase_cost_source: str,
    first_leg_fee_cny: Decimal | None,
    first_leg_status: str = "not_calculated",
) -> PricingResult:
    return PricingResult(
        status=status,
        first_leg_status=first_leg_status,
        first_leg_fee_cny=None,
        suggested_price_usd=None,
        minimum_price_usd=None,
        clearance_price_usd=None,
        suggested_gross_margin_rate=None,
        suggested_roi=None,
        product_grade="exception",
        grade_reason=status,
        commission_source=commission_source,
        breakdown={
            "status": status,
            "wfs_calc_status": wfs.status,
            "wfs_calc_reason": wfs.reason,
            "storage_calc_status": storage.status,
            "components": _cost_components(
                rule=rule,
                purchase_cost_cny=purchase_cost_cny,
                purchase_cost_source=purchase_cost_source,
                first_leg_fee_cny=first_leg_fee_cny,
                first_leg_status=first_leg_status,
                wfs=wfs,
                storage=storage,
                commission_cny=None,
                commission_source=commission_source,
            ),
        },
    )


def _cost_components(
    *,
    rule: PricingRule,
    purchase_cost_cny: Decimal | None,
    purchase_cost_source: str,
    first_leg_fee_cny: Decimal | None,
    first_leg_status: str,
    wfs: WfsFeeResult,
    storage: StorageResult,
    commission_cny: Decimal | None,
    commission_source: str,
) -> list[dict[str, object]]:
    return [
        {
            "name": "purchase_cost",
            "amount": _optional_decimal_text(purchase_cost_cny),
            "currency": "CNY" if purchase_cost_cny is not None else None,
            "source": _purchase_component_source(purchase_cost_source),
            "included": True,
            "status": "ok" if purchase_cost_cny is not None else "missing",
            "reason": None if purchase_cost_cny is not None else "purchase_cost_missing",
        },
        {
            "name": "first_leg",
            "amount": _optional_decimal_text(first_leg_fee_cny),
            "currency": "CNY",
            "source": "pricing_rule_config",
            "included": rule.include_first_leg_fee,
            "status": _component_status(first_leg_status, rule.include_first_leg_fee),
            "reason": first_leg_status if first_leg_status not in {"ok", "not_included"} else None,
        },
        {
            "name": "wfs_fulfillment",
            "amount": _optional_decimal_text(wfs.amount),
            "currency": wfs.currency_code if wfs.currency_code in {"USD", "CNY"} else None,
            "source": _wfs_component_source(wfs),
            "included": rule.include_wfs_fulfillment_fee,
            "status": _component_status(wfs.status, rule.include_wfs_fulfillment_fee),
            "reason": wfs.reason,
        },
        {
            "name": "estimated_storage",
            "amount": _optional_decimal_text(storage.estimated_fee_usd),
            "currency": "USD",
            "source": "storage_rate_config" if storage.status == "ok" else "missing",
            "included": rule.include_storage_fee,
            "status": _component_status(storage.status, rule.include_storage_fee),
            "reason": (
                None
                if storage.status == "ok"
                else "storage_rate_not_available"
                if storage.status == "missing_rate"
                else "package_dimension_missing"
            ),
        },
        {
            "name": "other_fixed_cost",
            "amount": _decimal_text(rule.other_fixed_cost_cny),
            "currency": "CNY",
            "source": "pricing_rule_config",
            "included": True,
            "status": "ok",
            "reason": None,
        },
        {
            "name": "commission",
            "amount": _optional_decimal_text(commission_cny),
            "currency": "CNY",
            "source": "default_zero"
            if commission_source == "default_zero"
            else "pricing_rule_config",
            "included": False,
            "status": "ok" if commission_cny is not None else "not_calculated",
            "reason": None if commission_cny is not None else "commission_not_calculated",
        },
    ]


def _purchase_component_source(source: str) -> str:
    if source == "product_core_manual":
        return "manual_override"
    if source == "lingxing_profile":
        return "lingxing_detail"
    return "missing"


def _wfs_component_source(wfs: WfsFeeResult) -> str:
    if wfs.source.startswith("manual_") or wfs.source == "manual_override":
        return "manual_override"
    if wfs.status == "ok" and wfs.source == "calculated_rule":
        return "wfs_rate_config"
    return "missing"


def _component_status(status: str, included: bool) -> str:
    if not included:
        return "not_included"
    if status == "ok":
        return "ok"
    if status == "needs_confirm":
        return "needs_confirm"
    if status.startswith("missing_"):
        return "missing"
    return "not_calculated"


def _to_cny(amount: Decimal | None, currency_code: str | None, fx: Decimal) -> Decimal | None:
    if amount is None or currency_code is None:
        return None
    if currency_code == "CNY":
        return _money(amount)
    if currency_code == "USD":
        return _money(amount * fx)
    return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def _round_price_up(value: Decimal) -> Decimal:
    rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return rounded if rounded >= value else rounded + CENT


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else _decimal_text(value)
