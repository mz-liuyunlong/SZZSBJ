# ruff: noqa: E501
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.modules.clearance.batch_read import DAILY_FIELDS, _available, application_identity


def test_batch_exact_historical_identity():
    row = {"source_account_ref": "a", "store_id": "s", "item_id": "a::s::123"}
    assert application_identity(row) == ("a", "s", "123")
    assert application_identity({**row, "item_id": "b::s::123"}) == ("a", "s", "b::s::123")


def test_inventory_freshness_and_unknown():
    now = datetime.now(UTC)
    listing = SimpleNamespace(calculated_at=now, wfs_available_quantity=Decimal("12"))
    old = SimpleNamespace(captured_at=now - timedelta(days=1), wfs_available_quantity=Decimal("2"))
    new = SimpleNamespace(captured_at=now, wfs_available_quantity=Decimal("0"))
    assert _available(listing, old) == 12
    assert _available(listing, new) == 0
    assert _available(listing, None) == 12
    new.wfs_available_quantity = None
    assert _available(listing, new) is None
    new.wfs_available_quantity = Decimal("1.5")
    assert _available(listing, new) is None


def test_projection_has_cost_currency_and_identity():
    assert {
        "source_account_ref",
        "store_id",
        "item_id",
        "msku",
        "cost_status",
        "gross_profit_currency_code",
        "first_leg_cost_total_usd",
        "sem_ad_spend_amount",
    } <= set(DAILY_FIELDS)
    assert "source_lineage_json" not in DAILY_FIELDS


def test_plan_sales_la_boundaries_and_completed_cutoff():
    from datetime import date

    from app.modules.clearance.batch_read import _plan_sales_dates

    row = {"submitted_at": "2026-11-21T02:00:00+00:00", "status": "running"}
    today = date(2026, 11, 24)
    assert _plan_sales_dates(row, today) == (date(2026, 11, 21), today)
    assert _plan_sales_dates(
        {**row, "status": "done", "finished_at": "2026-11-23T03:00:00Z"}, today
    ) == (date(2026, 11, 21), date(2026, 11, 22))
    assert _plan_sales_dates({**row, "status": "pending"}, today) == (date(2026, 11, 21), None)
    assert _plan_sales_dates({**row, "status": "done", "finished_at": None}, today) == (
        date(2026, 11, 21),
        None,
    )
    assert _plan_sales_dates(row, date(2026, 11, 20))[1] is None


def test_plan_sales_batch_exact_identity_and_missing_not_zero():
    from datetime import date

    from app.modules.clearance.batch_read import read_plan_sales

    class Fake:
        def execute(self, statement, params):
            assert params["application_ids"] == ["one", "two"]
            assert params["accounts"] == ["a", "a"]
            assert params["stores"] == ["s", "s"]
            assert params["items"] == ["123", "123"]
            assert params["starts"] == [date(2026, 11, 21), date(2026, 11, 22)]
            assert "m.source_account_ref = k.account_ref" in str(statement)
            assert "records = distinct_mskus" in str(statement)
            assert "IS NOT DISTINCT FROM 'USD'" in str(statement)
            return self

        def mappings(self):
            return self

        def all(self):
            return [{"application_id": "one", "sold": Decimal("8"), "amount": Decimal("120.55")}]

    row = {
        "id": "one",
        "source_account_ref": "a",
        "store_id": "s",
        "item_id": "a::s::123",
        "status": "running",
        "submitted_at": "2026-11-21T02:00:00Z",
    }
    result = read_plan_sales(
        Fake(),
        [
            row,
            {**row, "id": "two", "submitted_at": "2026-11-22T02:00:00Z"},
            {**row, "id": "three", "source_account_ref": "other"},
        ],
        {"a"},
        date(2026, 11, 24),
    )
    assert result["one"]["plan_sold_qty"] == 8
    assert result["one"]["plan_sales_amount_usd"] == 120.55
    assert result["two"]["plan_sold_qty"] is None
    assert result["three"]["plan_sales_amount_usd"] is None


def test_plan_daily_large_read_keeps_exact_identity_projection():
    from datetime import date

    from app.modules.clearance.batch_read import read_daily_rows

    class Fake:
        def execute(self, statement, params):
            sql = str(statement)
            assert "CROSS JOIN LATERAL" in sql
            assert "m.item_id = k.item_id" in sql
            assert "m.store_id = k.store_id" in sql
            assert "m.source_account_ref = k.account_ref" in sql
            assert "m.business_date_la BETWEEN :start_day AND :end_day" in sql
            assert len(params["items"]) == 150
            assert params["start_day"] == date(2026, 10, 26)
            return self

        def all(self):
            return []

    assert not read_daily_rows(Fake(), [("a", "s", str(i)) for i in range(150)], date(2026, 11, 24))
