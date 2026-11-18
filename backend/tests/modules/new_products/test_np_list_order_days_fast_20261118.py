"""List-day count is bounded, account isolated, and never a detail query."""

import json
from datetime import date

import pytest

from app.modules.new_products.repository import NewProductRepository
from app.modules.new_products.service import NewProductService

CUT = date(2026, 11, 17)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return Result(self.rows)


def row(account="a", store="store-1", item="123", first="2026-10-19", *, frozen=False):
    return {
        "listing": {"source_account_ref": account, "store_id": store, "item_id": item},
        "facts": {"first_wfs_available_date_la": first},
        "evaluation": {"observation_state": "frozen" if frozen else "automatic_partial"},
    }


def repo(rows):
    r = NewProductRepository.__new__(NewProductRepository)
    r.session = Session(rows)
    return r


def test_one_page_aggregate_preserves_store_and_account_identity():
    r = repo(
        [
            {"account": "a", "store": "store-1", "item": "123", "source_rows": 10, "paid_days": 8},
            {"account": "a", "store": "store-2", "item": "123", "source_rows": 5, "paid_days": 3},
        ]
    )
    result = r.paid_order_days_for_list([row(), row(store="store-2")], CUT)
    assert result == {("a", "store-1", "123"): 8, ("a", "store-2", "123"): 3}
    assert len(r.session.calls) == 1
    sql, params = r.session.calls[0]
    assert "COUNT(DISTINCT d.business_date_la)" in sql
    assert "FILTER (WHERE d.order_count > 0)" in sql
    assert "d.source_account_ref=w.account" in sql and "d.store_id=w.store" in sql
    assert "d.item_id=w.item" in sql and "d.business_date_la >= w.start_day" in sql
    assert params["cutoff"] == CUT
    assert len(json.loads(params["wanted"])) == 2


def test_missing_source_is_not_a_fake_zero():
    r = repo(
        [{"account": "a", "store": "store-1", "item": "123", "source_rows": 0, "paid_days": 0}]
    )
    assert r.paid_order_days_for_list([row()], CUT) == {("a", "store-1", "123"): None}


def test_verified_zero_observed_day_not_missing():
    r = repo(
        [{"account": "a", "store": "store-1", "item": "123", "source_rows": 4, "paid_days": 0}]
    )
    assert r.paid_order_days_for_list([row()], CUT) == {("a", "store-1", "123"): 0}


def test_no_wfs_start_produces_no_mart_query():
    r = repo([])
    assert r.paid_order_days_for_list([row(first=None)], CUT) == {}
    assert r.session.calls == []


def test_page_over_200_fails_closed_without_query():
    r = repo([])
    rows = [row(item=str(i)) for i in range(201)]
    with pytest.raises(ValueError, match="PAGE_SCOPE_EXCEEDED"):
        r.paid_order_days_for_list(rows, CUT)
    assert not r.session.calls


def test_invalid_unscoped_identity_response_rejected():
    r = repo(
        [{"account": "OTHER", "store": "store-1", "item": "123", "source_rows": 10, "paid_days": 5}]
    )
    with pytest.raises(ValueError, match="QUERY_IDENTITY_MISMATCH"):
        r.paid_order_days_for_list([row()], CUT)


def test_more_paid_days_than_wfs_calendar_window_rejected():
    r = repo(
        [{"account": "a", "store": "store-1", "item": "123", "source_rows": 100, "paid_days": 100}]
    )
    with pytest.raises(ValueError, match="COUNT_INVALID"):
        r.paid_order_days_for_list([row(first="2026-11-16")], CUT)


def test_explicit_final_or_frozen_never_recomputed():
    service = NewProductService.__new__(NewProductService)

    class FakeRepo:
        def __init__(self):
            self.called = []

        def paid_order_days_for_list(self, rows, cutoff):
            self.called.append([r["listing"]["item_id"] for r in rows])
            return {("a", "store-1", "123"): 8}

    service.repo = FakeRepo()
    active = row()
    closed = row(item="already-decided")
    frozen = row(item="grade-frozen", frozen=True)
    service._attach_order_days_for_list(
        [active, closed, frozen], {("a", "store-1", "already-decided"): object()}, CUT
    )
    assert service.repo.called == [["123"]]
    assert active["facts"]["order_days_count"] == 8
    assert "order_days_count" not in closed["facts"]
    assert "order_days_count" not in frozen["facts"]


def test_empty_or_only_closed_list_never_queries_sales():
    service = NewProductService.__new__(NewProductService)

    class FailRepo:
        def paid_order_days_for_list(self, rows, cutoff):
            raise AssertionError("must not query closed rows")

    service.repo = FailRepo()
    service._attach_order_days_for_list([], {}, CUT)
    service._attach_order_days_for_list([row(frozen=True)], {}, CUT)
