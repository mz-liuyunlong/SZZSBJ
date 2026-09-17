from decimal import Decimal

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    _cost_totals,
    _money_decimal,
)
from app.modules.product_management.daily_sales_costs import DailySalesCostResolution


def test_money_decimal_accepts_currency_formatted_zero() -> None:
    assert _money_decimal("$0.000000") == Decimal("0.000000")
    assert _money_decimal("USD 1,234.50") == Decimal("1234.50")
    assert _money_decimal("¥9.90") == Decimal("9.90")


def test_daily_sales_cost_totals_use_product_management_units_and_sales_qty() -> None:
    cost = DailySalesCostResolution(
        owner_ref="owner-a",
        purchase_cost_unit_cny=Decimal("14"),
        first_leg_cost_unit_cny=Decimal("7"),
        wfs_fee_unit_usd=Decimal("4.25"),
        storage_fee_unit_usd=Decimal("0.08"),
        exchange_rate=Decimal("7"),
        fx_date=None,
        fx_source="sku-pricing-defaults-v1",
        rule_version="sku-pricing-defaults-v1",
        calculation_status="ok",
        root_missing_codes=(),
    )

    purchase, first_leg, wfs, storage = _cost_totals(cost, Decimal("3"))

    assert purchase == Decimal("6")
    assert first_leg == Decimal("3")
    assert wfs == Decimal("12.75")
    assert storage == Decimal("0.24")
