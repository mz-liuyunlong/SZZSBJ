"""Clearance-only read fallback; no production DB or network is accessed."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.clearance import read_only_listings as fallback


class Selection:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class ReadSession:
    def __init__(self, ids=None, rows=None):
        self.ids = ids or []
        self.rows = rows or []
        self.statements = []

    def scalar(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        assert sql.startswith("SELECT to_regclass")
        return None

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        assert sql.strip().startswith("SELECT")
        assert params["limit"] > 0
        assert params["offset"] >= 0
        return Selection(self.ids)

    def scalars(self, statement):
        sql = str(statement)
        self.statements.append((sql, None))
        assert sql.lstrip().startswith("SELECT")
        return Selection(self.rows)


def listing():
    return SimpleNamespace(
        id=uuid4(),
        source_account_ref="HK2613",
        store_id="store-1",
        item_id="item-5",
        msku="MSKU-1",
        local_sku="SKU-1",
        title="Real Listing",
        local_name="Real Listing",
        store_name="Store",
        owner_ref="Owner",
        sale_price_currency_code="USD",
        sale_price_amount=Decimal("15.25"),
        picture_url=None,
        sales_7d=Decimal("12"),
        sales_14d=Decimal("24"),
        sales_30d=Decimal("48"),
        average_rating=Decimal("4.2"),
        review_count=27,
    )


def test_missing_optional_clearance_table_is_detected_without_writes():
    session = ReadSession()
    assert fallback.risk_read_model_ready(session) is False
    assert len(session.statements) == 1
    assert "biz_clearance_rule_versions" in str(session.statements[0][1])


def test_unrelated_database_errors_are_not_suppressed():
    class Broken:
        def scalar(self, *_args, **_kwargs):
            raise RuntimeError("real SQL error")

    with pytest.raises(RuntimeError, match="real SQL error"):
        fallback.risk_read_model_ready(Broken())


def test_scoped_keyword_pagination_uses_select_only_and_source_rows(monkeypatch):
    item = listing()
    item.wfs_available_quantity = 13
    session = ReadSession(ids=[item.id], rows=[item])
    monkeypatch.setattr(fallback, "current_available", lambda _s, _l: 13)
    monkeypatch.setattr(
        fallback,
        "read_business_snapshot",
        lambda _s, listing: {"item_id": listing.item_id, "available": 13},
    )
    result = fallback.search_unassessed_listings(session, frozenset({"HK2613"}), "SKU-1", 2, 50)
    assert result["items"] == [{"item_id": "item-5", "available": 13}]
    assert result["rule_version"] == 0 and result["risk_model_ready"] is False
    sql, params = session.statements[0]
    assert "source_account_ref = ANY(:accounts)" in sql
    assert "mart_listing_management_current" in sql
    assert "l.wfs_available_quantity" in sql
    assert params["accounts"] == ["HK2613"]
    assert params["limit"] == 51 and params["offset"] == 50
    assert params["keyword"] == "%SKU-1%"
    assert all(
        not stmt.lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
        for stmt, _ in session.statements
    )


def test_no_matching_wfs_listing_returns_empty_not_fake_data():
    result = fallback.search_unassessed_listings(ReadSession(), frozenset({"HK2613"}), "", 1, 50)
    assert result["items"] == []
    assert result["has_more"] is False


def test_facts_without_verified_daily_rows_are_null_not_invented_zero(monkeypatch):
    item = listing()
    session = ReadSession()
    monkeypatch.setattr(fallback, "current_available", lambda _s, _l: 13)
    monkeypatch.setattr(fallback, "la_today", lambda: date(2026, 11, 6))
    snap = fallback.read_business_snapshot(session, item)
    assert snap["item_id"] == "item-5"
    assert snap["sku"] == "SKU-1"
    assert snap["metrics"]["sales_7d"] == 12.0
    assert snap["metrics"]["profit_7d_usd"] is None
    assert snap["metrics"]["margin_30d_percent"] is None
    assert snap["metrics"]["sellout_days"] == 9
    assert snap["metrics"]["sellout_source"] == "listing_30d_estimate_only"
    assert snap["risk"] == "unknown"
    assert snap["rule_version"] == 0
    assert snap["metrics"]["suggested_clearance_qty"] is None


def test_exact_total_is_sql_count_of_scoped_wfs_pool(monkeypatch):
    class CountingSession(ReadSession):
        def scalar(self, statement, params=None):
            sql = str(statement)
            self.statements.append((sql, params))
            assert sql.lstrip().startswith("SELECT COUNT(*)")
            assert "source_account_ref = ANY(:accounts)" in sql
            assert "l.wfs_available_quantity" in sql
            assert "> 0" in sql and "trunc" in sql
            assert params == {"accounts": ["HK2613"], "keyword": "%SKU%"}
            return 318

    item = listing()
    item.wfs_available_quantity = 8
    session = CountingSession(ids=[item.id], rows=[item])
    monkeypatch.setattr(fallback, "current_available", lambda _s, _l: 8)
    monkeypatch.setattr(
        fallback, "read_business_snapshot", lambda _s, row: {"item_id": row.item_id, "available": 8}
    )
    result = fallback.search_unassessed_listings(
        session,
        frozenset({"HK2613"}),
        "SKU",
        1,
        50,
        exact_total=True,
        risk_only_requested=True,
    )
    assert result["total"] == 318
    assert result["total_scope"] == "all_wfs_stock_eligible"
    assert result["risk_filter_applied"] is False
    assert result["risk_calculated_in_memory"] is True
    assert result["items"][0]["item_id"] == "item-5"
    assert all(str(sql).lstrip().startswith("SELECT") for sql, _params in session.statements)


def test_empty_page_still_returns_exact_total():
    class CountingEmptySession(ReadSession):
        def scalar(self, statement, params=None):
            assert "COUNT(*)" in str(statement)
            return 0

    result = fallback.search_unassessed_listings(
        CountingEmptySession(),
        frozenset({"HK2613"}),
        "",
        2,
        50,
        exact_total=True,
    )
    assert result["total"] == 0
    assert result["items"] == []
    assert result["has_more"] is False


def test_unrequested_total_does_not_issue_count():
    session = ReadSession()
    result = fallback.search_unassessed_listings(session, frozenset({"HK2613"}), "", 1, 50)
    assert result["total"] is None
    assert len(session.statements) == 1
