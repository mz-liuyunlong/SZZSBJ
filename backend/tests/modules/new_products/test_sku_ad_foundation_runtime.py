"""Runtime contracts with real SQLAlchemy PostgreSQL DML compilation, no server."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete, Insert, Update

from app.modules.new_products import sku_ad_foundation_runtime as r

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)
DAY = NOW.astimezone(r.LA).date()
ROW = dict(
    advertiserId="A",
    campaignId="C",
    adGroupId="G",
    adItemId="AD",
    itemId="I",
    mpSellerName=" Store A ",
    campaignStatus="enabled",
    adGroupStatus="enabled",
    adStatus="enabled",
    reviewStatus="approved",
    adSpend="0",
    ntbRevenue="2.3",
)


class Result(list):
    def mappings(self):
        return self

    def all(self):
        return self


class SimulatedSession:
    """Only a fixture/SQL compiler. Does not claim PostgreSQL execution."""

    def __init__(self, store="S", fact=True, account="X"):
        self.store = store
        self.fact = fact
        self.account = account
        self.calls = []
        self.dml = []

    def execute(self, stmt, params=None):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.calls.append((sql, params))
        if isinstance(stmt, (Insert, Update, Delete)):
            table = stmt.table.name
            assert table in r.m.Base.metadata.tables, table
            assert not table.startswith("dim_") and table != "fact_walmart_ad_item_sp_daily"
            self.dml.append((table, stmt, stmt.compile(dialect=postgresql.dialect()).params))
            return Result()
        if "from fact_walmart_ad_item_sp_daily" in sql:
            assert (
                params == {"account": self.account, "day": DAY} or params["account"] == self.account
            )
            return Result(
                [
                    dict(
                        advertiser_id="A",
                        source_line_hash="a" * 64,
                        store_id=self.store,
                        item_id="I",
                        campaign_id="C",
                        ad_group_id="G",
                        ad_item_id="AD",
                        ad_spend_currency_code="USD",
                        synced_at=NOW,
                    )
                ]
                if self.fact
                else []
            )
        if "from dim_walmart_advertisers" in sql:
            assert params["account"] == self.account
            return Result(
                [
                    dict(
                        advertiser_id="A",
                        advertiser_name="Adv",
                        raw_status="1",
                        store_id=None,
                        synced_at=NOW,
                    )
                ]
            )
        if "from dim_lingxing_stores" in sql:
            assert params["account"] == self.account
            return Result([("S", "Store A"), ("T", "Store B")])
        if "from dim_walmart_listings" in sql:
            assert params["account"] == self.account
            return Result([("S", "I"), ("T", "I")])
        raise AssertionError(sql)


def pages(row=ROW):
    return [
        (
            "walmart_advertiser_list",
            uuid4(),
            NOW - timedelta(minutes=2),
            [{"advertiserId": "A", "advertiserName": "Adv", "status": 1}],
        ),
        ("walmart_ad_item_sp_list", uuid4(), NOW - timedelta(minutes=1), [row]),
    ]


def run(db, row=ROW, *, source_pages=None, day=DAY, complete=True):
    return r._write_ad_day(
        db,
        account=db.account,
        day=day,
        pages=source_pages or pages(row),
        selected={("A", "a" * 64): row},
        complete=complete,
        now=NOW,
    )


def test_ad_enabled_positive_without_spend_and_exact_store_scope():
    db = SimulatedSession()
    out = run(db)
    assert out == {"daily": 1, "enabled": 1, "mappings": 1}
    inserts = [x for x in db.dml if isinstance(x[1], Insert)]
    assert {x[0] for x in inserts} == {
        "fact_walmart_ad_item_sp_daily_ext",
        "dwd_walmart_ad_item_config_ext",
        "biz_walmart_ad_account_store_mapping",
        "mart_listing_ad_status_current",
    }
    status = next(x[2] for x in inserts if x[0] == "mart_listing_ad_status_current")
    assert (
        status["ad_enabled"] is True
        and status["store_id"] == "S"
        and status["source_account_ref"] == "X"
    )
    assert status["evidence_json"]["coverage_verified"] is False
    assert not any(t == "fact_walmart_ad_item_sp_daily" for t, *_ in db.dml)


def test_ambiguous_seller_and_conflicting_fact_store_never_enabled():
    db = SimulatedSession(store="T")
    out = run(db)
    assert out["enabled"] == 0
    mapped = next(x[2] for x in db.dml if x[0] == "biz_walmart_ad_account_store_mapping")
    assert mapped["mapping_status"] == "ambiguous" and mapped["store_id"] is None
    assert not any(
        t == "mart_listing_ad_status_current" and isinstance(stmt, Insert) for t, stmt, _ in db.dml
    )


def test_unknown_is_not_false_for_paused_and_incomplete_report():
    db = SimulatedSession()
    out = run(db, {**ROW, "adStatus": "disabled"})
    assert out["enabled"] == 0
    changes = [params for t, stmt, params in db.dml if t == "mart_listing_ad_status_current"]
    assert len(changes) == 1 and changes[0]["ad_enabled"] is None
    db = SimulatedSession()
    with pytest.raises(ValueError, match="CAPTURE_INCOMPLETE"):
        run(db, complete=False)
    assert db.dml == []


def test_historical_report_does_not_change_listing_or_mapping():
    db = SimulatedSession()
    out = run(db, day=DAY - timedelta(days=7))
    assert out["status"] == "historical_day_not_published"
    assert all(
        t not in ("mart_listing_ad_status_current", "biz_walmart_ad_account_store_mapping")
        for t, *_ in db.dml
    )


def test_unverified_fact_or_raw_lineage_does_not_replace_daily_extension():
    db = SimulatedSession(fact=False)
    with pytest.raises(ValueError, match="FACT_SET_CHANGED"):
        run(db)
    assert db.dml == []
    db = SimulatedSession()
    with pytest.raises(ValueError, match="SELECTED_ROW_UNVERIFIED"):
        run(db, source_pages=pages({**ROW, "ntbRevenue": "99"}))
    assert db.dml == []


def test_all_ad_source_rows_retained_including_missing_identity_and_redaction():
    db = SimulatedSession()
    blob = uuid4()
    data = [ROW, {"futureMetric": 0, "token": "private"}]
    for _ in range(2):
        r.save_ad_source_page(
            db, account="X", day=DAY, kind="walmart_ad_item_sp_list", blob=blob, seen=NOW, rows=data
        )
    keys = [x[2]["observation_key"] for x in db.dml]
    assert keys[0] != keys[1] and keys[:2] == keys[2:]
    assert db.dml[1][2]["payload_json"] == {"futureMetric": 0, "token": "[REDACTED]"}
    assert all(t == "dwd_walmart_ad_source_observations" for t, *_ in db.dml)
    assert all(
        "ON CONFLICT" in str(stmt.compile(dialect=postgresql.dialect())) for _, stmt, _ in db.dml
    )


def test_capture_provenance_and_unknown_shapes_do_not_raise():
    runner = SimpleNamespace()
    response = SimpleNamespace(response_json={"data": {"list": [ROW]}}, pulled_at=NOW)
    blob = uuid4()
    r.collect_ad_page(runner, "walmart_ad_item_sp_list", str(blob), response)
    assert runner._foundation_ad_pages[0][1] == blob
    assert runner._foundation_ad_pages[0][3] == [ROW]
    r.collect_ad_page(
        runner,
        "walmart_ad_item_sp_list",
        str(blob),
        SimpleNamespace(response_json={"bad": 1}, pulled_at=NOW),
    )
    assert runner._foundation_ad_capture_failed is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("campaignStatus", "paused"),
        ("adGroupStatus", "disabled"),
        ("adStatus", "deleted"),
        ("reviewStatus", None),
    ],
)
def test_positive_requires_all_status_evidence(field, value):
    assert not r.observed_enabled({**ROW, field: value}, "1", NOW, NOW)


def test_stale_and_future_observations_never_positive():
    assert not r.observed_enabled(ROW, "1", NOW - timedelta(hours=49), NOW)
    assert not r.observed_enabled(ROW, "1", NOW + timedelta(seconds=1), NOW)
    assert not r.observed_enabled(ROW, "0", NOW, NOW)
    assert r.observed_enabled(ROW, "1", NOW, NOW)


def test_duplicate_state_conflict_never_publishes_positive():
    ps = pages()
    ps[1][3].append({**ROW, "adStatus": "disabled"})
    db = SimulatedSession()
    assert run(db, source_pages=ps)["enabled"] == 0


def test_account_mapping_no_item_only_guess_and_ambiguous_names():
    assert r.confirmed_store(
        store_names={"store a": {"S", "T"}}, item_stores={"I": {"S"}}, facts=[("Store A", "I", "S")]
    ) == (None, "ambiguous")
    assert r.confirmed_store(
        store_names={}, item_stores={"I": {"S"}}, facts=[(None, "I", "S")]
    ) == (None, "unmapped")
