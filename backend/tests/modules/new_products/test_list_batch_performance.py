"""The list must use bounded queries; tests never connect to any database."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.new_products.bulk_read import (
    EMPTY_ADS,
    EMPTY_ORDERS,
    DecisionSnapshot,
    ReadSnapshot,
    load_decision_snapshot,
    load_read_snapshot,
)
from app.modules.new_products.service import NewProductService


class _MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return iter(self.rows)


class _FakeReadSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.statements.append((sql, parameters))
        if "listing_wfs_first_stock_la_locked" in sql:
            return _MappingResult(
                [
                    {
                        "account": "ref",
                        "store": "s",
                        "item": "i1",
                        "day": date(2026, 11, 1),
                        "date_source": "locked",
                    },
                    {
                        "account": "ref",
                        "store": "s",
                        "item": "i2",
                        "day": None,
                        "date_source": None,
                    },
                ]
            )
        if "fact_walmart_order_items" in sql:
            return _MappingResult(
                [
                    {
                        "account": "ref",
                        "store": "s",
                        "item": "i1",
                        "order_count": 2,
                        "units": 2,
                        "single_orders": 2,
                        "first_order_date": date(2026, 11, 2),
                        "unknown_lines": 0,
                    },
                ]
            )
        if "mart_daily_sales_item_day" in sql:
            return _MappingResult([])
        if "fact_walmart_ad_item_sp_daily" in sql:
            return _MappingResult([])
        raise AssertionError("Unexpected SQL")


def test_snapshot_200_items_never_executes_per_item_queries():
    session = _FakeReadSession()
    keys = [("ref", "s", f"i{i}") for i in range(1, 201)]
    snap = load_read_snapshot(session, keys, date(2026, 11, 12))
    assert len(session.statements) == 4
    assert snap.first[("ref", "s", "i1")]["day"] == date(2026, 11, 1)
    assert snap.orders[("ref", "s", "i1")]["order_count"] == 2
    assert snap.first[("ref", "s", "i2")]["day"] is None
    for sql, params in session.statements:
        assert "CAST(:" in sql
        assert len(params) == 1
    windows = json.loads(session.statements[1][1]["windows"])
    assert all(row["item"] != "i2" for row in windows)
    assert EMPTY_ORDERS["order_count"] == 0
    assert EMPTY_ADS["n"] == 0


def test_no_wfs_first_date_never_scans_sales_or_ads():
    class NoWfs(_FakeReadSession):
        def execute(self, statement, parameters):
            assert "listing_wfs_first_stock_la_locked" in str(statement)
            self.statements.append((str(statement), parameters))
            return _MappingResult(
                [{"account": "ref", "store": "s", "item": "i", "day": None, "date_source": None}]
            )

    session = NoWfs()
    snapshot = load_read_snapshot(session, [("ref", "s", "i")], date(2026, 11, 12))
    assert len(session.statements) == 1
    assert snapshot.orders == {} and snapshot.daily == {} and snapshot.ads == {}


def test_market_snapshot_absence_does_not_trigger_per_item_write_query():
    service = NewProductService.__new__(NewProductService)
    service.repo = MagicMock()
    service.write_repo = MagicMock()
    service._facts("ref", "s", "i", market_score=None, snapshot=ReadSnapshot({}, {}, {}, {}))
    service.write_repo.market.assert_not_called()


def test_market_snapshot_can_be_loaded_in_one_query_per_model():
    fake = MagicMock()
    fake.scalars.return_value.all.return_value = []
    keys = [("ref", "s", f"i{i}") for i in range(1, 201)]
    saved = load_decision_snapshot(fake, keys)
    assert isinstance(saved, DecisionSnapshot)
    assert fake.scalars.call_count == 3
    assert saved.markets == {} and saved.tracking == {} and saved.purchases == {}


def test_oversized_batch_is_rejected_before_query():
    fake = MagicMock()
    keys = [("ref", "s", f"i{i}") for i in range(201)]
    try:
        load_read_snapshot(fake, keys, date(2026, 11, 12))
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized batch was accepted")
    fake.execute.assert_not_called()


def test_stage_one_list_only_reads_scoped_tagged_listings():
    service = NewProductService.__new__(NewProductService)
    service.repo = MagicMock()
    service.write_repo = MagicMock()
    service.db = MagicMock()
    listing = MagicMock()
    listing.first_wfs_available_date_la = None
    listing.model_dump.return_value = {
        "source_account_ref": "ref",
        "store_id": "s",
        "item_id": "i1",
        "product_tags": [{"label": "小批量测品"}],
        "first_wfs_available_date_la": None,
    }
    service.repo.page.return_value = (SimpleNamespace(items=[listing]), 1, None)
    service.repo.first_order_dates.return_value = {}
    query = SimpleNamespace(
        page=1, page_size=50, store_id="", owner="", keyword="", search_field="item_id", status=""
    )

    result = service.list(frozenset({"ref"}), query)

    assert result["total"] == 1
    assert len(result["items"]) == 1
    row = result["items"][0]
    assert row["listing"]["item_id"] == "i1"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    assert row["evaluation"]["observation_state"] == "not_calculated"
    assert row["facts"]["data_status"] == "not_calculated"
    assert row["facts"]["first_order_date"] is None
    service.repo.first_order_dates.assert_called_once()
    service.write_repo.assert_not_called()
    service.db.assert_not_called()
    service.repo.page.assert_called_once()


def test_stage_one_shows_real_wfs_elapsed_days_without_scoring():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    service = NewProductService.__new__(NewProductService)
    service.repo = MagicMock()
    service.write_repo = MagicMock()
    service.db = MagicMock()
    listing = MagicMock()
    first_day = date(2026, 10, 1)
    listing.first_wfs_available_date_la = first_day
    listing.model_dump.return_value = {
        "source_account_ref": "ref",
        "store_id": "s",
        "item_id": "i1",
        "first_wfs_available_date_la": "2026-10-01",
    }
    service.repo.page.return_value = (SimpleNamespace(items=[listing]), 1, None)
    service.repo.first_order_dates.return_value = {}
    query = SimpleNamespace(
        page=1, page_size=50, store_id="", owner="", keyword="", search_field="item_id", status=""
    )

    result = service.list(frozenset({"ref"}), query)
    row = result["items"][0]
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    assert row["facts"]["elapsed_days"] == (today - first_day).days + 1
    assert row["facts"]["first_wfs_available_date_la"] == "2026-10-01"
    assert row["evaluation"]["total"] is None
    assert row["evaluation"]["grade"] is None
    service.write_repo.assert_not_called()
    service.db.assert_not_called()


def test_stage_one_renders_first_date_from_daily_sales_without_scoring():
    service = NewProductService.__new__(NewProductService)
    service.repo = MagicMock()
    service.write_repo = MagicMock()
    service.db = MagicMock()
    listing = MagicMock()
    listing.first_wfs_available_date_la = None
    listing.model_dump.return_value = {
        "source_account_ref": "primary",
        "store_id": "store1",
        "item_id": "item1",
        "first_wfs_available_date_la": None,
    }
    service.repo.page.return_value = (SimpleNamespace(items=[listing]), 1, None)
    service.repo.first_order_dates.return_value = {
        ("primary", "store1", "item1"): date(2026, 10, 15),
    }
    query = SimpleNamespace(
        page=1, page_size=200, store_id="", owner="", keyword="", search_field="item_id", status=""
    )
    result = service.list(frozenset({"primary"}), query)
    assert result["items"][0]["facts"]["first_order_date"] == "2026-10-15"
    assert result["items"][0]["evaluation"]["total"] is None
    assert result["items"][0]["evaluation"]["grade"] is None
    service.repo.first_order_dates.assert_called_once_with([listing])
    service.write_repo.assert_not_called()
    service.db.assert_not_called()


def test_local_preview_uses_single_bounded_snapshot_and_existing_scoring(monkeypatch):
    from unittest.mock import patch

    from app.modules.new_products.bulk_read import ReadSnapshot

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv(
        "PR337_LOCAL_PREVIEW_ITEM_IDS", "20874953767,20881463249,20859269992,20858150090"
    )
    service = NewProductService.__new__(NewProductService)
    service.repo = MagicMock()
    service.db = MagicMock()
    service.write_repo = MagicMock()
    service._config = MagicMock(return_value=({"weights": {}, "confirmedScoring": {}}, 0))
    listing = MagicMock()
    listing.source_account_ref = "primary"
    listing.store_id = "s1"
    listing.item_id = "20874953767"
    listing.first_wfs_available_date_la = date(2026, 11, 1)
    listing.model_dump.return_value = {
        "source_account_ref": "primary",
        "store_id": "s1",
        "item_id": "20874953767",
        "first_wfs_available_date_la": "2026-11-01",
    }
    service.repo.page.return_value = (SimpleNamespace(items=[listing]), 1, None)
    service.repo.first_order_dates.return_value = {}
    service.db.scalars.return_value.all.return_value = []
    sample = ReadSnapshot(
        {("primary", "s1", "20874953767"): {"day": date(2026, 11, 1), "date_source": "locked"}},
        {},
        {},
        {},
        {("primary", "s1", "20874953767"): 0},
    )
    fake_evaluation = {"total": None, "grade": None, "dimensions": {}}
    with (
        patch("app.modules.new_products.service.load_read_snapshot", return_value=sample) as loader,
        patch("app.modules.new_products.service.evaluate", return_value=fake_evaluation) as scorer,
    ):
        result = service.list(
            frozenset({"primary"}),
            SimpleNamespace(
                page=1,
                page_size=50,
                store_id="",
                owner="",
                keyword="",
                search_field="item_id",
                status="",
            ),
        )
    assert result["total"] == 1 and result["local_preview"] is True
    assert result["items"][0]["facts"]["valid_orders_14d"] == 0
    assert result["items"][0]["facts"]["orders_7d"] == 0
    assert result["items"][0]["evaluation"] is fake_evaluation
    assert loader.call_count == 1 and scorer.call_count == 1
    assert loader.call_args.kwargs["preview_since_first"] is True
    assert set(service.repo.page.call_args.kwargs["item_ids"]) == {
        "20874953767",
        "20881463249",
        "20859269992",
        "20858150090",
    }
    service.write_repo.market.assert_not_called()
    service.db.add.assert_not_called()
    service.db.commit.assert_not_called()


def test_ads_preview_window_extends_to_today_but_orders_stay_14_days():
    from datetime import date

    from app.modules.new_products.bulk_read import load_read_snapshot

    fake = _FakeReadSession()
    today = date(2026, 11, 12)
    load_read_snapshot(fake, [("ref", "s", "i1")], today, preview_since_first=True)
    order_window = json.loads(fake.statements[1][1]["windows"])[0]
    ad_window = json.loads(fake.statements[3][1]["windows"])[0]
    assert order_window["end_date"] == "2026-11-12"
    assert ad_window["end_date"] == "2026-11-12"
    # Earlier WFS date: the orders window would stop after 14 days, ads continue.
    fake2 = _FakeReadSession()
    original = _FakeReadSession.execute

    def with_old_date(self, statement, parameters):
        if "listing_wfs_first_stock_la_locked" in str(statement):
            self.statements.append((str(statement), parameters))
            return _MappingResult(
                [
                    {
                        "account": "ref",
                        "store": "s",
                        "item": "i1",
                        "day": date(2026, 10, 1),
                        "date_source": "locked",
                    }
                ]
            )
        return original(self, statement, parameters)

    fake2.execute = with_old_date.__get__(fake2, _FakeReadSession)
    load_read_snapshot(fake2, [("ref", "s", "i1")], today, preview_since_first=True)
    assert json.loads(fake2.statements[1][1]["windows"])[0]["end_date"] == "2026-10-14"
    assert json.loads(fake2.statements[3][1]["windows"])[0]["end_date"] == "2026-11-12"
