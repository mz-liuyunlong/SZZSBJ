from decimal import Decimal

from app.modules.product_management.field_access import (
    filter_export_request,
    filter_list_item,
    filter_pricing_breakdown,
)
from app.modules.product_management.schemas import (
    ExportRequest,
    PricingBreakdownRead,
    ProductManagementListItem,
)


def _item() -> ProductManagementListItem:
    return ProductManagementListItem.model_construct(
        purchase_cost_cny=Decimal("10"),
        unit_first_leg_cost=Decimal("2"),
        unit_first_leg_currency_code="CNY",
        wfs_fulfillment_fee=Decimal("3"),
        wfs_fulfillment_fee_currency_code="USD",
        wfs_daily_storage_fee=Decimal("1"),
        wfs_daily_storage_fee_currency_code="USD",
        first_leg_fee_cny=Decimal("2"),
        wfs_base_fee_usd=Decimal("3"),
        storage_fee_usd=Decimal("1"),
        suggested_price_usd=Decimal("20"),
        minimum_price_usd=Decimal("18"),
        clearance_price_usd=Decimal("15"),
        price_currency_code="USD",
        fixed_cost_usd=Decimal("1"),
        costs_visible=True,
    )


def _pricing() -> PricingBreakdownRead:
    return PricingBreakdownRead.model_construct(
        purchase_cost_cny=Decimal("10"),
        purchase_cost_currency_code="CNY",
        wfs_fulfillment_fee_usd=Decimal("3"),
        wfs_fulfillment_fee_cny=Decimal("21"),
        daily_storage_fee_per_unit_usd=Decimal("1"),
        daily_storage_fee_per_unit_cny=Decimal("7"),
        estimated_storage_fee_usd=Decimal("2"),
        estimated_storage_fee_cny=Decimal("14"),
        first_leg_cost_per_kg_cny=Decimal("12"),
        first_leg_fee_cny=Decimal("2"),
        wfs_base_fee_usd=Decimal("3"),
        storage_fee_usd=Decimal("1"),
        suggested_price_usd=Decimal("20"),
        minimum_price_usd=Decimal("18"),
        clearance_price_usd=Decimal("15"),
        price_currency_code="USD",
        suggested_gross_margin_rate=Decimal("0.2"),
        suggested_roi=Decimal("1.1"),
        fixed_cost_usd=Decimal("1"),
        usd_cny_rate=Decimal("7"),
        components=[],
    )


def test_purchase_and_logistics_fields_are_independent() -> None:
    filtered = filter_list_item(
        _item(),
        can_view_purchase_cost=True,
        can_view_logistics_cost=False,
    )

    assert filtered.purchase_cost_cny == Decimal("10")
    assert filtered.first_leg_fee_cny is None
    assert filtered.wfs_fulfillment_fee is None
    assert filtered.suggested_price_usd is None
    assert filtered.costs_visible is True


def test_pricing_requires_both_grants_for_derived_values() -> None:
    filtered = filter_pricing_breakdown(
        _pricing(),
        can_view_purchase_cost=False,
        can_view_logistics_cost=True,
    )

    assert filtered.purchase_cost_cny is None
    assert filtered.wfs_fulfillment_fee_usd == Decimal("3")
    assert filtered.suggested_price_usd is None
    assert filtered.suggested_gross_margin_rate is None
    assert filtered.components is None


def test_export_columns_drop_unauthorized_cost_fields() -> None:
    payload = ExportRequest(
        columns=[
            "sku",
            "purchase_cost_cny",
            "first_leg_fee_cny",
            "suggested_price_usd",
        ]
    )

    filtered = filter_export_request(
        payload,
        can_view_purchase_cost=True,
        can_view_logistics_cost=False,
    )

    assert filtered.columns == ["sku", "purchase_cost_cny"]
