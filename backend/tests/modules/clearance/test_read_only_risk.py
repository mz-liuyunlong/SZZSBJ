"""Verify pure risk restoration against source-backed facts without any DB writes."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.clearance import read_only_listings as module
from app.modules.clearance.rules import ClearanceRules


def listing():
    return SimpleNamespace(
        source_account_ref="HK2613", store_id="S1", item_id="i1",
        sale_price_amount=Decimal("15"), sale_price_currency_code="USD",
        inbound_quantity=Decimal("0"), average_rating=Decimal("4.6"),
        review_count=10,
    )


def window(units: int | None, days: int = 30) -> dict:
    return {
        "units": Decimal(units) if units is not None else None,
        "revenue": Decimal("120") if units is not None else None,
        "ads": Decimal("8") if units is not None else None,
        "profit": Decimal("12") if units is not None else None,
        "returns": Decimal("0") if units is not None else None,
        "complete": units is not None,
        "effective_days": days,
        "observed_days": days if units is not None else 0,
        "active_sales_days": 5 if units is not None else None,
    }


def test_uses_existing_rule_evaluator_for_high_coverage():
    w = {7:window(7, 7), 14:window(14, 14), 30:window(30)}
    level, reasons, signals, gaps, metrics = module._assess_read_only(listing(), 240, w, 120, None)
    assert level == "high"
    assert metrics["sellout_days"] == 240
    assert any("180" in reason for reason in reasons)
    assert signals == []


def test_medium_rule_and_new_product_protection():
    w = {7:window(7, 7), 14:window(14, 14), 30:window(30)}
    assert module._assess_read_only(listing(), 120, w, 120, None)[0] == "medium"
    assert module._assess_read_only(listing(), 120, w, 40, None)[0] == "low"
    # Unknown first-WFS date cannot waive 60-day new-product protection.
    level, reasons, _, gaps, _ = module._assess_read_only(listing(), 120, w, None, None)
    assert level == "unknown"
    assert "first_wfs_available_date_la" in gaps
    assert any("新品" in x for x in reasons)


def test_zero_sales_requires_first_stock_date_and_complete_window():
    w = {7:window(0, 7), 14:window(0, 14), 30:window(0)}
    assert module._assess_read_only(listing(), 120, w, 32, None)[0] == "high"
    assert module._assess_read_only(listing(), 120, w, None, None)[0] == "unknown"
    w[30] = window(None)
    assert module._assess_read_only(listing(), 120, w, 32, None)[0] == "unknown"


def test_incomplete_sales_cannot_be_inferred_from_listing_mart():
    w = {7:window(None, 7), 14:window(None, 14), 30:window(None)}
    level, _, _, gaps, metrics = module._assess_read_only(listing(), 100, w, None, None)
    assert level == "unknown"
    assert "sales_30d_completeness" in gaps
    assert metrics["sellout_days"] is None


def test_effective_days_respect_verified_first_stock():
    cutoff = date(2026, 11, 5)
    first = cutoff - timedelta(days=4)
    rows = {first + timedelta(days=i): [SimpleNamespace(
        msku="SKU-A", sales_qty=Decimal(2), sales_amount=Decimal(20),
        sales_currency_code="USD", ad_spend_amount=Decimal(3),
        ad_spend_currency_code="USD", cost_status="complete",
        gross_profit_amount=Decimal(5), gross_profit_currency_code="USD",
        return_qty=Decimal(0),
    )] for i in range(5)}
    w = module._window_stats(rows, cutoff, 30, first)
    assert w["complete"] is True
    assert w["units"] == Decimal(10)
    assert w["effective_days"] == 5
    assert w["observed_days"] == 5
    assert module._window_stats(rows, cutoff, 30, None)["complete"] is False


def test_no_silent_error_handling_or_state_table_writes():
    class Exploding:
        def scalar(self, *_args, **_kwargs):
            raise RuntimeError("unexpected business SQL failure")
    with pytest.raises(RuntimeError, match="unexpected business SQL failure"):
        module._first_wfs_date(Exploding(), listing())
    assert ClearanceRules().highCoverage == 180
    assert ClearanceRules().mediumCoverage == 90
    assert ClearanceRules().assistCoverage == 60


def test_full_snapshot_uses_real_daily_fact_rows_and_never_persists(monkeypatch):
    from uuid import uuid4

    cutoff = date(2026, 11, 5)
    first = cutoff - timedelta(days=120)
    source_rows = []
    for i in range(30):
        source_rows.append(SimpleNamespace(
            business_date_la=cutoff - timedelta(days=i),
            msku="M1", sales_qty=Decimal(1), sales_amount=Decimal("20"),
            sales_currency_code="USD", ad_spend_amount=Decimal("2"),
            ad_spend_currency_code="USD", gross_profit_amount=Decimal("5"),
            gross_profit_currency_code="USD", return_qty=Decimal(0),
            cost_status="complete", cost_quantity=Decimal(1),
            purchase_cost_total_usd=Decimal(4), first_leg_cost_total_usd=Decimal(2),
        ))

    class FakeSession:
        def __init__(self):
            self.statements = []
        def scalars(self, statement):
            sql = str(statement)
            self.statements.append(sql)
            assert sql.lstrip().startswith("SELECT")
            return SimpleNamespace(all=lambda: source_rows)

    item = listing()
    item.id = uuid4()
    item.msku = "M1"
    item.local_sku = "SKU1"
    item.title = "Genuine product"
    item.local_name = None
    item.store_name = "Genuine store"
    item.owner_ref = "Genuine owner"
    item.picture_url = None
    item.sales_7d = Decimal(7)
    item.sales_14d = Decimal(14)
    item.sales_30d = Decimal(30)
    monkeypatch.setattr(module, "current_available", lambda _s, _l: 240)
    monkeypatch.setattr(module, "la_today", lambda: cutoff + timedelta(days=1))
    monkeypatch.setattr(module, "_first_wfs_date", lambda _s, _l: first)
    session = FakeSession()
    snapshot = module.read_business_snapshot(session, item)
    assert snapshot["risk"] == "high"
    assert snapshot["metrics"]["sellout_days"] == 240
    assert snapshot["metrics"]["capital_purchase_first_leg_usd"] == 1440.0
    assert snapshot["metrics"]["capital_at_cost_usd"] is None
    assert snapshot["source_account_ref"] == "HK2613"
    assert snapshot["item_id"] == "i1"
    assert snapshot["rule_version"] == 0
    assert all(text.startswith("SELECT") for text in session.statements)


def test_optional_first_wfs_source_never_uses_unverified_listing_age():
    from datetime import date
    class LookupSession:
        def __init__(self, found):
            self.found=found
            self.queries=[]
        def scalar(self, sql, params=None):
            self.queries.append(str(sql))
            if "to_regclass" in str(sql):
                return "listing_wfs_first_stock_la_locked" if self.found else None
            return date(2026, 9, 1)
    missing=LookupSession(False)
    assert module._first_wfs_date(missing, listing()) is None
    assert len(missing.queries)==1
    present=LookupSession(True)
    assert module._first_wfs_date(present, listing()) == date(2026, 9, 1)
    assert len(present.queries)==2
    assert all(q.lstrip().startswith("SELECT") for q in present.queries)
