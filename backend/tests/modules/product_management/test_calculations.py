from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.product_management.calculations import (
    IdentityWfsOverride,
    ListingWfsOverride,
    PricingRule,
    SkuPricingRule,
    StorageResult,
    WfsFeeResult,
    WfsFulfillmentRate,
    calculate_pricing,
    calculate_sku_pricing,
    calculate_storage,
    select_wfs_fee,
)
from app.modules.product_management.schemas import CostComponentRead

SKU_ID = UUID("00000000-0000-0000-0000-000000000001")
LISTING_1 = UUID("00000000-0000-0000-0000-000000000002")
LISTING_2 = UUID("00000000-0000-0000-0000-000000000003")


def _rule(**changes: object) -> PricingRule:
    values: dict[str, object] = {
        "usd_cny_rate": Decimal("7"),
        "platform_commission_rate": Decimal("0.15"),
        "first_leg_cost_per_kg_cny": Decimal("12"),
        "suggested_margin": Decimal("0.20"),
        "minimum_margin": Decimal("0.10"),
        "clearance_margin": Decimal("0"),
        "storage_month_basis_days": 30,
        "pricing_storage_days": 30,
        "include_first_leg_fee": True,
        "include_wfs_fulfillment_fee": True,
        "include_storage_fee": True,
        "other_fixed_cost_cny": Decimal("0"),
        "roi_base": "purchase_cost",
        "grade_a_min_margin": Decimal("0.20"),
        "grade_a_min_roi": Decimal("1"),
        "grade_b_min_margin": Decimal("0.10"),
        "grade_b_min_roi": Decimal("0.50"),
        "rounding_mode": "none",
    }
    values.update(changes)
    return PricingRule(**values)  # type: ignore[arg-type]


def _wfs_ok() -> WfsFeeResult:
    return WfsFeeResult("ok", None, "calculated_rule", Decimal("5"), "USD", "synthetic")


def _storage_ok() -> StorageResult:
    return calculate_storage(
        dimensions_cm=(Decimal("30.48"), Decimal("30.48"), Decimal("30.48")),
        monthly_rate_usd_per_cuft=Decimal("1.50"),
        storage_month_basis_days=30,
        pricing_storage_days=30,
    )


def _listing(
    listing_id: UUID,
    amount: str,
    *,
    primary: bool = False,
) -> ListingWfsOverride:
    return ListingWfsOverride(
        listing_id=listing_id,
        amount=Decimal(amount),
        currency_code="USD",
        is_primary=primary,
        is_active=True,
    )


def test_sku_pricing_reproduces_wfs_formula_and_three_price_tiers() -> None:
    result = calculate_sku_pricing(
        purchase_cost_cny=Decimal("20"),
        product_gross_weight_g=Decimal("800"),
        dimensions_cm=(Decimal("16"), Decimal("13"), Decimal("13")),
        image_count=2,
        storage_fee_usd=Decimal("0.3"),
    )

    assert result.wfs_actual_weight_lb == Decimal("1.763668")
    assert result.wfs_dimensional_weight_lb == Decimal("1.187110")
    assert result.wfs_chargeable_weight_lb == Decimal("3")
    assert result.wfs_base_fee_usd == Decimal("4.25")
    assert result.wfs_fulfillment_fee_usd == Decimal("5.4500")
    assert result.gross_weight_kg == Decimal("0.800000")
    assert result.first_leg_volume_weight_kg == Decimal("0.450667")
    assert result.first_leg_chargeable_weight_kg == Decimal("0.800000")
    assert result.first_leg_fee_cny == Decimal("9.6000")
    assert result.fixed_cost_usd == Decimal("10.1679")
    assert result.suggested_price_usd == Decimal("22.60")
    assert result.minimum_price_usd == Decimal("18.49")
    assert result.clearance_price_usd == Decimal("11.96")
    assert result.calculation_status == "ok"
    assert result.pricing_available is True


def test_sku_pricing_uses_fixed_thirty_day_wfs_storage_rate() -> None:
    result = calculate_sku_pricing(
        purchase_cost_cny=Decimal("20"),
        product_gross_weight_g=Decimal("800"),
        dimensions_cm=(Decimal("30.48"), Decimal("30.48"), Decimal("30.48")),
        image_count=0,
    )

    assert result.package_volume_cuft == Decimal("1.000000")
    assert result.daily_storage_fee_per_unit_usd == Decimal("0.0250")
    assert result.storage_fee_usd == Decimal("0.7500")
    assert result.fixed_cost_usd == Decimal("21.5379")
    assert result.suggested_price_usd == Decimal("47.86")
    assert result.minimum_price_usd == Decimal("39.16")
    assert result.clearance_price_usd == Decimal("25.34")
    assert result.storage_calc_status == "ok"
    assert result.calculation_status == "ok"
    assert result.pricing_available is True
    assert result.root_missing_codes == ("missing_dimension_image",)


@pytest.mark.parametrize(
    ("changes", "missing_code"),
    [
        ({"purchase_cost_cny": None}, "missing_purchase_cost"),
        ({"product_gross_weight_g": None}, "missing_gross_weight"),
        ({"dimensions_cm": (Decimal("16"), None, Decimal("13"))}, "missing_package_dimensions"),
    ],
)
def test_sku_pricing_missing_billing_inputs_fail_closed(
    changes: dict[str, object], missing_code: str
) -> None:
    inputs: dict[str, object] = {
        "purchase_cost_cny": Decimal("20"),
        "product_gross_weight_g": Decimal("800"),
        "dimensions_cm": (Decimal("16"), Decimal("13"), Decimal("13")),
        "image_count": 2,
        "storage_fee_usd": Decimal("0.3"),
    }
    inputs.update(changes)

    result = calculate_sku_pricing(**inputs)  # type: ignore[arg-type]

    assert missing_code in result.root_missing_codes
    assert result.calculation_status == "pricing_unavailable"
    assert result.suggested_price_usd is None
    assert result.minimum_price_usd is None
    assert result.clearance_price_usd is None
    if missing_code == "missing_gross_weight":
        assert result.gross_weight_kg is None
        assert result.wfs_fulfillment_fee_usd is None
    if missing_code == "missing_package_dimensions":
        assert result.first_leg_volume_weight_kg is None
        assert result.first_leg_fee_cny is None
        assert result.storage_fee_usd is None


def test_missing_dimension_image_does_not_block_sku_pricing() -> None:
    result = calculate_sku_pricing(
        purchase_cost_cny=Decimal("20"),
        product_gross_weight_g=Decimal("800"),
        dimensions_cm=(Decimal("16"), Decimal("13"), Decimal("13")),
        image_count=1,
        storage_fee_usd=Decimal("0.3"),
    )

    assert result.root_missing_codes == ("missing_dimension_image",)
    assert result.billing_root_complete is True
    assert result.calculation_status == "ok"
    assert result.suggested_price_usd is not None


def test_invalid_sku_pricing_denominator_fails_closed() -> None:
    result = calculate_sku_pricing(
        purchase_cost_cny=Decimal("20"),
        product_gross_weight_g=Decimal("800"),
        dimensions_cm=(Decimal("16"), Decimal("13"), Decimal("13")),
        image_count=2,
        rule=SkuPricingRule(suggested_margin_rate=Decimal("0.70")),
        storage_fee_usd=Decimal("0.3"),
    )

    assert "invalid_pricing_rule" in result.root_missing_codes
    assert result.calculation_status == "invalid_denominator"
    assert result.suggested_price_usd is None


def test_synthetic_storage_formula_and_missing_states() -> None:
    result = _storage_ok()
    assert result.status == "ok"
    assert result.package_volume_cuft == Decimal("1.000000")
    assert result.daily_fee_usd == Decimal("0.0500")
    assert result.estimated_fee_usd == Decimal("1.5000")
    assert (
        calculate_storage(
            dimensions_cm=(None, Decimal("1"), Decimal("1")),
            monthly_rate_usd_per_cuft=Decimal("1"),
            storage_month_basis_days=30,
            pricing_storage_days=30,
        ).status
        == "missing_dimension"
    )
    assert (
        calculate_storage(
            dimensions_cm=(Decimal("1"), Decimal("1"), Decimal("1")),
            monthly_rate_usd_per_cuft=None,
            storage_month_basis_days=30,
            pricing_storage_days=30,
        ).status
        == "missing_rate"
    )


def test_wfs_override_priority_and_conflicts() -> None:
    identity = IdentityWfsOverride(SKU_ID, Decimal("4"), "USD")
    listings = (_listing(LISTING_1, "5", primary=True), _listing(LISTING_2, "6"))
    result = select_wfs_fee(
        identity_id=SKU_ID,
        identity_overrides=(identity,),
        listing_overrides=listings,
        rates=(),
        gross_weight_kg=None,
        dimensions_cm=(None, None, None),
    )
    assert result.source == "manual_sku_override"
    assert result.amount == Decimal("4.0000")

    primary = select_wfs_fee(
        identity_id=SKU_ID,
        identity_overrides=(),
        listing_overrides=listings,
        rates=(),
        gross_weight_kg=None,
        dimensions_cm=(None, None, None),
    )
    assert primary.source == "manual_primary_listing_override"

    conflict = select_wfs_fee(
        identity_id=SKU_ID,
        identity_overrides=(),
        listing_overrides=(_listing(LISTING_1, "5"), _listing(LISTING_2, "6")),
        rates=(),
        gross_weight_kg=None,
        dimensions_cm=(None, None, None),
    )
    assert conflict.status == "needs_confirm"
    assert conflict.reason == "multiple_listing_wfs_overrides"

    consistent = select_wfs_fee(
        identity_id=SKU_ID,
        identity_overrides=(),
        listing_overrides=(_listing(LISTING_1, "5"), _listing(LISTING_2, "5")),
        rates=(),
        gross_weight_kg=None,
        dimensions_cm=(None, None, None),
    )
    assert consistent.source == "manual_consistent_listing_override"


def test_synthetic_wfs_rule_never_supplies_unconfigured_real_rate() -> None:
    assert (
        select_wfs_fee(
            identity_id=SKU_ID,
            identity_overrides=(),
            listing_overrides=(),
            rates=(),
            gross_weight_kg=Decimal("1"),
            dimensions_cm=(Decimal("1"), Decimal("1"), Decimal("1")),
        ).status
        == "missing_rate"
    )
    synthetic = WfsFulfillmentRate(
        "synthetic-only",
        Decimal("5"),
        "USD",
        max_weight_kg=Decimal("2"),
        max_longest_side_cm=Decimal("50"),
    )
    assert (
        select_wfs_fee(
            identity_id=SKU_ID,
            identity_overrides=(),
            listing_overrides=(),
            rates=(synthetic,),
            gross_weight_kg=None,
            dimensions_cm=(Decimal("1"), Decimal("1"), Decimal("1")),
        ).status
        == "missing_weight"
    )
    assert (
        select_wfs_fee(
            identity_id=SKU_ID,
            identity_overrides=(),
            listing_overrides=(),
            rates=(synthetic,),
            gross_weight_kg=Decimal("1"),
            dimensions_cm=(None, Decimal("1"), Decimal("1")),
        ).status
        == "missing_dimension"
    )
    ambiguous = select_wfs_fee(
        identity_id=SKU_ID,
        identity_overrides=(),
        listing_overrides=(),
        rates=(synthetic, synthetic),
        gross_weight_kg=Decimal("1"),
        dimensions_cm=(Decimal("1"), Decimal("1"), Decimal("1")),
    )
    assert ambiguous.status == "needs_confirm"
    assert ambiguous.reason == "multiple_matching_wfs_rates"


def test_pricing_formula_rounding_roi_and_grade_are_decimal_only() -> None:
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1.5"),
        wfs=_wfs_ok(),
        storage=_storage_ok(),
        rule=_rule(),
    )
    assert result.status == "ok"
    assert result.suggested_price_usd is not None
    assert result.minimum_price_usd is not None
    assert result.clearance_price_usd is not None
    assert result.suggested_price_usd >= result.minimum_price_usd >= result.clearance_price_usd
    assert result.suggested_gross_margin_rate is not None
    assert result.suggested_gross_margin_rate >= Decimal("0.20")
    assert result.suggested_roi is not None and result.suggested_roi >= Decimal("1")
    assert result.product_grade == "A"
    assert result.first_leg_fee_cny == Decimal("18.00")
    assert result.breakdown["commission_source"] == "configured"
    components = result.breakdown["components"]
    assert isinstance(components, list)
    assert all(
        set(component) == {"name", "amount", "currency", "source", "included", "status", "reason"}
        for component in components
    )
    parsed = [CostComponentRead.model_validate(component) for component in components]
    assert {component.name for component in parsed} == {
        "purchase_cost",
        "first_leg",
        "wfs_fulfillment",
        "estimated_storage",
        "other_fixed_cost",
        "commission",
    }
    assert all(component.source and isinstance(component.included, bool) for component in parsed)
    commission = next(component for component in parsed if component.name == "commission")
    assert commission.included is False
    assert Decimal(str(result.breakdown["included_costs_cny"])) == Decimal("73.5000")
    assert Decimal(str(result.breakdown["gross_profit_cny"])) == (
        Decimal(str(result.breakdown["revenue_cny"]))
        - Decimal(str(result.breakdown["commission_cny"]))
        - Decimal(str(result.breakdown["included_costs_cny"]))
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"usd_cny_rate": None}, "missing_fx_rate"),
        ({"platform_commission_rate": Decimal("0.80")}, "invalid_pricing_denominator"),
        (
            {
                "suggested_margin": Decimal("0.10"),
                "minimum_margin": Decimal("0.20"),
            },
            "invalid_pricing_rule_config",
        ),
    ],
)
def test_pricing_safe_failures(changes: dict[str, object], expected: str) -> None:
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1"),
        wfs=_wfs_ok(),
        storage=_storage_ok(),
        rule=_rule(**changes),
    )
    assert result.status == expected
    assert result.product_grade == "exception"
    assert result.suggested_price_usd is None
    components = result.breakdown["components"]
    assert isinstance(components, list)
    assert len([CostComponentRead.model_validate(component) for component in components]) == 6


def test_pricing_missing_inputs_and_default_zero_commission() -> None:
    assert (
        calculate_pricing(
            purchase_cost_cny=None,
            gross_weight_kg=Decimal("1"),
            wfs=_wfs_ok(),
            storage=_storage_ok(),
            rule=_rule(),
        ).status
        == "missing_purchase_cost"
    )
    assert (
        calculate_pricing(
            purchase_cost_cny=Decimal("10"),
            gross_weight_kg=None,
            wfs=_wfs_ok(),
            storage=_storage_ok(),
            rule=_rule(),
        ).status
        == "missing_weight"
    )
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1"),
        wfs=_wfs_ok(),
        storage=_storage_ok(),
        rule=_rule(platform_commission_rate=None, roi_base="total_cost"),
    )
    assert result.status == "ok"
    assert result.commission_source == "default_zero"
    assert result.breakdown["roi_base"] == "total_cost"


def test_pricing_rejects_unconvertible_wfs_currency() -> None:
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1"),
        wfs=WfsFeeResult("ok", None, "manual_override", Decimal("5"), "EUR"),
        storage=_storage_ok(),
        rule=_rule(),
    )

    assert result.status == "needs_confirm"
    assert result.suggested_price_usd is None


@pytest.mark.parametrize(
    ("grade_thresholds", "expected_grade"),
    [
        ({"grade_a_min_roi": Decimal("100"), "grade_b_min_roi": Decimal("0")}, "B"),
        (
            {
                "grade_a_min_roi": Decimal("100"),
                "grade_b_min_margin": Decimal("0.90"),
            },
            "C",
        ),
    ],
)
def test_product_grade_thresholds_are_versioned_inputs(
    grade_thresholds: dict[str, object], expected_grade: str
) -> None:
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1"),
        wfs=_wfs_ok(),
        storage=_storage_ok(),
        rule=_rule(**grade_thresholds),
    )

    assert result.status == "ok"
    assert result.product_grade == expected_grade


def test_manual_minimum_price_is_a_floor() -> None:
    result = calculate_pricing(
        purchase_cost_cny=Decimal("10"),
        gross_weight_kg=Decimal("1"),
        wfs=_wfs_ok(),
        storage=_storage_ok(),
        rule=_rule(),
        manual_min_price_usd=Decimal("99.001"),
    )
    assert result.status == "ok"
    assert result.clearance_price_usd == Decimal("99.01")
    assert result.minimum_price_usd == Decimal("99.01")
    assert result.suggested_price_usd == Decimal("99.01")
    prices = result.breakdown["price_calculations"]
    assert isinstance(prices, list)
    assert prices[0]["final_price_usd"] == "99.01"
    assert prices[0]["source"] == "manual_override"
