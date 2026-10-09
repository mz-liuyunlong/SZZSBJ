from decimal import Decimal

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DAILY_SALES_V2_VERSION,
    _low_price_delivery_surcharge,
)


def test_low_price_delivery_surcharge_applies_below_10_usd() -> None:
    assert _low_price_delivery_surcharge(Decimal("9.99"), Decimal("1")) == Decimal("1")
    assert _low_price_delivery_surcharge(Decimal("19.98"), Decimal("2")) == Decimal("2")


def test_low_price_delivery_surcharge_does_not_apply_at_10_usd_or_above() -> None:
    assert _low_price_delivery_surcharge(Decimal("10.00"), Decimal("1")) == Decimal("0")
    assert _low_price_delivery_surcharge(Decimal("30.00"), Decimal("2")) == Decimal("0")


def test_low_price_delivery_surcharge_ignores_zero_paid_quantity() -> None:
    assert _low_price_delivery_surcharge(Decimal("0"), Decimal("0")) == Decimal("0")


def test_low_price_delivery_surcharge_must_be_calculated_per_business_day() -> None:
    """Do not calculate the threshold from a multi-day aggregated average price.

    Day 1 average unit price is 9 USD, so it triggers 1 USD surcharge.
    Day 2 average unit price is 20 USD, so it triggers no surcharge.
    A wrong multi-day average would be (9 + 20) / 2 = 14.5 and incorrectly return 0.
    """

    day_1_surcharge = _low_price_delivery_surcharge(Decimal("9"), Decimal("1"))
    day_2_surcharge = _low_price_delivery_surcharge(Decimal("20"), Decimal("1"))

    assert day_1_surcharge + day_2_surcharge == Decimal("1")


def test_daily_sales_calc_version_keeps_room_for_persisted_varchar_64() -> None:
    assert DAILY_SALES_V2_VERSION.endswith("+refund-v3-lpds")
    assert len(DAILY_SALES_V2_VERSION) <= 64
