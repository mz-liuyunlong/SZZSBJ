"""V14 source field contract: zero vs unknown; Item ID identity."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.modules.clearance import read_only_listings as read


def listing(**kwargs):
    facts = dict(
        source_account_ref="HK2613",
        store_id="store-1",
        item_id="12345",
        msku="msku",
        local_sku="sku",
        store_name="One",
        platform_code="WM",
        listing_start_at_utc=datetime(2026, 9, 1, tzinfo=UTC),
    )
    facts.update(kwargs)
    return SimpleNamespace(**facts)


def test_listing_age_comes_from_listing_start_not_wfs_date():
    assert read._listing_age_days(listing(), date(2026, 11, 7)) == 68
    assert read._listing_age_days(listing(listing_start_at_utc=None), date(2026, 11, 7)) is None


def test_unit_cost_requires_verified_positive_quantity():
    assert read._safe_per_unit(Decimal("20"), Decimal("4")) == 5
    assert read._safe_per_unit(None, Decimal("4")) is None
    assert read._safe_per_unit(Decimal("20"), Decimal("0")) is None


def test_source_keys_are_item_not_local_sku():
    a = listing(local_sku="sku-A")
    b = listing(local_sku="sku-B")
    assert (a.source_account_ref, a.store_id, a.item_id) == (
        b.source_account_ref,
        b.store_id,
        b.item_id,
    )


def test_missing_days_do_not_become_zero_financials():
    observed = read._window_stats({}, date(2026, 11, 6), 30)
    assert observed["complete"] is False
    assert observed["revenue"] is None and observed["ads"] is None
    assert observed["returns"] is None and observed["units"] is None


def test_full_observed_window_sums_item_level_currency_safe_metrics():
    cutoff = date(2026, 11, 6)
    rows = {}
    for offset in range(7):
        day = cutoff - __import__("datetime").timedelta(days=offset)
        rows[day] = [
            SimpleNamespace(
                msku="A",
                sales_qty=Decimal("2"),
                sales_amount=Decimal("20"),
                sales_currency_code="USD",
                ad_spend_amount=Decimal("4"),
                ad_spend_currency_code="USD",
                gross_profit_amount=Decimal("5"),
                gross_profit_currency_code="USD",
                return_qty=Decimal("0"),
                cost_status="complete",
            )
        ]
    result = read._window_stats(rows, cutoff, 7)
    assert result["complete"] is True
    assert result["units"] == 14 and result["revenue"] == 140
    assert result["ads"] == 28 and result["profit"] == 35
    assert result["ad_ratio"] == 20 and result["margin"] == 25
    assert result["returns"] == 0
