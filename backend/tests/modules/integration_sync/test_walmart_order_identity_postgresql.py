from __future__ import annotations

import hashlib
import os
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.integration_sync import data_pages_real_sync
from app.modules.integration_sync.data_pages_business_rules import (
    HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION,
    VERIFIED_SAMPLE_RULE_VERSION,
)
from app.modules.integration_sync.data_pages_business_rules_v2 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_mart_invariants import DataPagesMartInvariantError

_DATABASE = "walmart_order_identity_test"
_USERNAME = "walmart_order_identity_test"
_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ACCOUNT = "synthetic-order-identity"


def _validate_url(url: URL) -> URL:
    if (
        url.host not in _HOSTS
        or url.database != _DATABASE
        or url.username != _USERNAME
        or url.query
    ):
        raise SettingsError("Walmart order identity tests require the dedicated local database")
    return url


def _database_url() -> URL:
    if os.environ.get("WALMART_ORDER_IDENTITY_DB_TESTS") != "1":
        pytest.skip("real Walmart order identity PostgreSQL test requires explicit opt-in")
    try:
        return _validate_url(get_test_database_url(Settings()))  # type: ignore[call-arg]
    except (SettingsError, ValidationError) as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture
def engine() -> Iterator[Engine]:
    database_url = _database_url()
    engine = create_engine(database_url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        identity = connection.execute(text("select current_database(),current_user")).one()
    assert identity == (_DATABASE, _USERNAME)
    with engine.begin() as connection:
        connection.execute(
            text("delete from mart_daily_sales_item_day where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_sample_order_items where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text(
                "delete from audit_walmart_order_item_conflicts where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_order_items where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_sales_item_daily where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from dim_walmart_listings where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("delete from mart_daily_sales_item_day where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text(
                    "delete from fact_walmart_sample_order_items where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text(
                    "delete from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from fact_walmart_order_items where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from fact_walmart_sales_item_daily where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from dim_walmart_listings where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
        engine.dispose()


def _legacy_hash(line_id: str, version: int) -> str:
    return hashlib.sha256(f"{line_id}:{version}".encode()).hexdigest()


def _provider_row(*, store_id: str = "store-a", changed: bool = False) -> dict[str, object]:
    purchase_at = int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp())
    return {
        "global_order_no": "order-a",
        "global_purchase_time": str(purchase_at),
        "store_id": store_id,
        "status": "cancelled" if changed else "created",
        "amount_currency": "USD",
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [
            {
                "order_item_no": f"line-{index}",
                "item_id": f"item-{index}",
                "msku": f"msku-{index}",
                "local_sku": f"sku-{index}",
                "quantity": "2" if changed and index == 0 else "1",
                "sales_revenue_amount": "0",
                "discount_amount": "0",
            }
            for index in range(5)
        ],
    }


def _single_line_provider_row(
    *,
    order_id: str = "order-a",
    line_id: str = "line-0",
    item_id: str | None = "item-0",
    amount: str = "0",
    store_id: str = "store-a",
) -> dict[str, object]:
    row = _provider_row(store_id=store_id)
    row["global_order_no"] = order_id
    item = dict(cast(list[dict[str, object]], row["item_info"])[0])
    item["order_item_no"] = line_id
    item["sales_revenue_amount"] = amount
    if item_id is None:
        item.pop("item_id", None)
    else:
        item["item_id"] = item_id
    row["item_info"] = [item]
    row["transaction_info"] = [{"order_total_amount": amount}]
    return row


def _insert_listing(
    session: Session,
    *,
    item_id: str,
    msku: str = "msku-0",
    local_sku: str = "sku-0",
) -> None:
    now = datetime(2026, 10, 20, tzinfo=UTC)
    session.execute(
        text(
            "insert into dim_walmart_listings "
            "(id,source_account_ref,platform_code,store_id,item_id,msku,local_sku,"
            "synced_at,created_at,updated_at) values "
            "(:id,:account,'walmart','store-a',:item_id,:msku,:local_sku,:now,:now,:now)"
        ),
        {
            "id": str(uuid4()),
            "account": _ACCOUNT,
            "item_id": item_id,
            "msku": msku,
            "local_sku": local_sku,
            "now": now,
        },
    )


def _insert_identity_row(
    session: Session,
    *,
    row_id: str,
    line_hash: str,
    canonical_hash: str | None,
    is_current: bool,
    account: str = _ACCOUNT,
    store_id: str | None = "store-a",
    order_id: str = "order-constraint",
    line_id: str | None = "line-constraint",
) -> None:
    now = datetime(2026, 10, 20, tzinfo=UTC)
    session.execute(
        text(
            "insert into fact_walmart_order_items "
            "(id,source_account_ref,store_id,source_order_id,source_order_line_id,"
            "source_line_hash,canonical_identity_hash,is_identity_current,source_line_ordinal,"
            "is_sample_order,synced_at,created_at,updated_at) values "
            "(:id,:account,:store_id,:order_id,:line_id,:line_hash,:canonical_hash,"
            ":is_current,0,false,:now,:now,:now)"
        ),
        {
            "id": row_id,
            "account": account,
            "store_id": store_id,
            "order_id": order_id,
            "line_id": line_id,
            "line_hash": line_hash,
            "canonical_hash": canonical_hash,
            "is_current": is_current,
            "now": now,
        },
    )


def test_order_identity_preserves_12_legacy_versions_and_5_current_rows(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version_counts = (4, 3, 2, 2, 1)
    initial_observation = datetime(2026, 10, 20, 1, tzinfo=UTC)
    replay_observation = datetime(2026, 10, 20, 2, tzinfo=UTC)
    changed_observation = datetime(2026, 10, 20, 3, tzinfo=UTC)
    now = datetime(2026, 10, 19, 1, tzinfo=UTC)
    with Session(engine) as session:
        for line_index, versions in enumerate(version_counts):
            for version in range(versions):
                session.execute(
                    text(
                        "insert into fact_walmart_order_items "
                        "(id,source_account_ref,store_id,source_order_id,source_order_line_id,"
                        "source_line_hash,source_line_ordinal,item_id,msku,local_sku,quantity,"
                        "business_date_la,order_status_raw,sales_revenue_amount,"
                        "sales_revenue_currency_code,order_total_amount,order_total_currency_code,"
                        "discount_amount,discount_currency_code,is_sample_order,is_identity_current,"
                        "synced_at,created_at,updated_at) values "
                        "(:id,:account,'store-a','order-a',:line_id,:line_hash,:ordinal,:item_id,"
                        ":msku,:local_sku,:quantity,:day,'created',:sales_amount,'USD',0,'USD',"
                        ":discount_amount,'USD',"
                        "false,false,:now,:now,:now)"
                    ),
                    {
                        "id": str(uuid4()),
                        "account": _ACCOUNT,
                        "line_id": f"line-{line_index}",
                        "line_hash": _legacy_hash(f"line-{line_index}", version),
                        "ordinal": line_index,
                        "item_id": f"item-{line_index}",
                        "msku": f"msku-{line_index}",
                        "local_sku": f"sku-{line_index}",
                        "quantity": version + 1 if line_index == 0 else 1,
                        "sales_amount": version,
                        "discount_amount": version,
                        "day": date(2026, 10, 16),
                        "now": now,
                    },
                )
        session.commit()

        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        assert (
            runner._match_refund_order_line(
                {
                    "customer_order_id": "order-a",
                    "store_id": "store-a",
                    "item_id": "item-0",
                    "msku": "msku-0",
                }
            )
            is None
        )
        legacy_single = runner._match_refund_order_line(
            {
                "customer_order_id": "order-a",
                "store_id": "store-a",
                "item_id": "item-4",
                "msku": "msku-4",
            }
        )
        assert legacy_single is not None
        assert legacy_single["source_order_line_id"] == "line-4"

        legacy_before = session.execute(
            text(
                "select id,source_line_hash,quantity,sales_revenue_amount,discount_amount "
                "from fact_walmart_order_items where source_account_ref=:account order by id"
            ),
            {"account": _ACCOUNT},
        ).all()

        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: initial_observation)
        assert runner._write_orders([_provider_row()]) == 5
        session.commit()

        adopted = runner._match_refund_order_line(
            {
                "customer_order_id": "order-a",
                "store_id": "store-a",
                "item_id": "item-0",
                "msku": "msku-0",
            }
        )
        assert adopted is not None
        assert adopted["source_order_line_id"] == "line-0"

        counts = session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true),"
                "count(distinct canonical_identity_hash) filter "
                "(where is_identity_current=true) from fact_walmart_order_items "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert counts == (17, 5, 5)

        legacy_after = session.execute(
            text(
                "select id,source_line_hash,quantity,sales_revenue_amount,discount_amount "
                "from fact_walmart_order_items where source_account_ref=:account "
                "and is_identity_current=false order by id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert legacy_after == legacy_before

        first_audit_count = session.scalar(
            text(
                "select count(*) from audit_walmart_order_item_conflicts "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        )
        assert first_audit_count and first_audit_count > 0

        current_before_replay = session.execute(
            text(
                "select id,created_at,updated_at,synced_at from fact_walmart_order_items "
                "where source_account_ref=:account and is_identity_current=true order by id"
            ),
            {"account": _ACCOUNT},
        ).all()
        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: replay_observation)
        for _ in range(3):
            assert runner._write_orders([_provider_row()]) == 5
        session.commit()

        current_after_replay = session.execute(
            text(
                "select id,created_at,updated_at,synced_at from fact_walmart_order_items "
                "where source_account_ref=:account and is_identity_current=true order by id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert [row[:3] for row in current_after_replay] == [
            row[:3] for row in current_before_replay
        ]
        assert {row.synced_at for row in current_after_replay} == {replay_observation}

        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 17
        )
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account and is_identity_current=true"
                ),
                {"account": _ACCOUNT},
            )
            == 5
        )

        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: changed_observation)
        assert runner._write_orders([_provider_row(changed=True)]) == 5
        assert runner._write_orders([_provider_row(changed=True)]) == 5
        session.commit()
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 22
        )
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account and is_identity_current=true"
                ),
                {"account": _ACCOUNT},
            )
            == 5
        )
        prior_current = session.execute(
            text(
                "select count(*) from fact_walmart_order_items "
                "where source_account_ref=:account and is_identity_current=false "
                "and created_at=:created_at and updated_at=:updated_at"
            ),
            {
                "account": _ACCOUNT,
                "created_at": initial_observation,
                "updated_at": initial_observation,
            },
        ).scalar_one()
        assert prior_current == 5
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account and differing_fields_json ? 'quantity'"
                ),
                {"account": _ACCOUNT},
            )
            >= 1
        )
        linked_transition = session.execute(
            text(
                "select count(*) from audit_walmart_order_item_conflicts a "
                "join fact_walmart_order_items prior on prior.id=a.prior_fact_id "
                "join fact_walmart_order_items current on current.id=a.canonical_fact_id "
                "where a.source_account_ref=:account and prior.is_identity_current=false "
                "and current.is_identity_current=true"
            ),
            {"account": _ACCOUNT},
        ).scalar_one()
        assert linked_transition >= 5

        same_order_line_other_store = _provider_row(store_id="store-b")
        items = cast(list[dict[str, object]], same_order_line_other_store["item_info"])
        same_order_line_other_store["item_info"] = [items[0]]
        assert runner._write_orders([same_order_line_other_store]) == 1
        session.commit()
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account "
                    "and source_order_id='order-a' and source_order_line_id='line-0' "
                    "and is_identity_current=true"
                ),
                {"account": _ACCOUNT},
            )
            == 2
        )


def test_order_identity_current_constraints_and_metadata_match(engine: Engine) -> None:
    valid_hash = "a" * 64
    with Session(engine) as session:
        _insert_identity_row(
            session,
            row_id=str(uuid4()),
            line_hash="1" * 64,
            canonical_hash=None,
            is_current=False,
        )
        session.commit()

    invalid_rows: tuple[dict[str, object], ...] = (
        {"canonical_hash": None},
        {"canonical_hash": valid_hash, "account": ""},
        {"canonical_hash": valid_hash, "store_id": None},
        {"canonical_hash": valid_hash, "store_id": ""},
        {"canonical_hash": valid_hash, "order_id": ""},
        {"canonical_hash": valid_hash, "line_id": None},
        {"canonical_hash": valid_hash, "line_id": ""},
        {"canonical_hash": "G" * 64},
    )
    for index, overrides in enumerate(invalid_rows):
        with Session(engine) as session, pytest.raises(IntegrityError):
            _insert_identity_row(
                session,
                row_id=str(uuid4()),
                line_hash=hashlib.sha256(f"invalid-{index}".encode()).hexdigest(),
                canonical_hash=cast(str | None, overrides.get("canonical_hash", valid_hash)),
                is_current=True,
                account=cast(str, overrides.get("account", _ACCOUNT)),
                store_id=cast(str | None, overrides.get("store_id", "store-a")),
                order_id=cast(str, overrides.get("order_id", f"order-invalid-{index}")),
                line_id=cast(str | None, overrides.get("line_id", "line-constraint")),
            )
            session.commit()

    with Session(engine) as session:
        _insert_identity_row(
            session,
            row_id=str(uuid4()),
            line_hash="2" * 64,
            canonical_hash=valid_hash,
            is_current=True,
        )
        session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError):
        _insert_identity_row(
            session,
            row_id=str(uuid4()),
            line_hash="3" * 64,
            canonical_hash=valid_hash,
            is_current=True,
            order_id="order-other",
            line_id="line-other",
        )
        session.commit()
    with Session(engine) as session:
        _insert_identity_row(
            session,
            row_id=str(uuid4()),
            line_hash="4" * 64,
            canonical_hash="b" * 64,
            is_current=True,
            order_id="order-other",
            line_id="line-other",
        )
        session.commit()

    inspector = inspect(engine)
    check_names = {
        row["name"] for row in inspector.get_check_constraints("fact_walmart_order_items")
    }
    assert "ck_fact_walmart_order_items_canonical_identity_hash_sha256" in check_names
    assert "ck_fact_walmart_order_items_canonical_identity_current_complete" in check_names
    assert "ck_fact_walmart_order_items_current_item_lineage" in check_names
    current_index = next(
        row
        for row in inspector.get_indexes("fact_walmart_order_items")
        if row["name"] == "uq_fact_walmart_order_items_current_identity"
    )
    assert current_index["unique"] is True
    assert current_index["column_names"] == ["canonical_identity_hash"]


def test_listing_item_resolution_is_idempotent_across_three_provider_null_replays(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = [datetime(2026, 10, 20, hour, tzinfo=UTC) for hour in range(1, 5)]
    row = _single_line_provider_row(item_id=None)
    with Session(engine) as session:
        _insert_listing(session, item_id="listing-item-0")
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: observations[0])
        assert runner._write_orders([row]) == 1
        assert runner._resolve_order_items() == 0
        session.commit()

        first = session.execute(
            text(
                "select id,provider_item_id,item_id,item_id_resolution_source,"
                "created_at,updated_at from fact_walmart_order_items "
                "where source_account_ref=:account and is_identity_current=true"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert first[1:4] == (None, "listing-item-0", "listing_local_sku_unique")

        for observed_at in observations[1:]:
            monkeypatch.setattr(data_pages_real_sync, "_now", lambda value=observed_at: value)
            assert runner._write_orders([row]) == 1
            assert runner._resolve_order_items() == 0
            session.commit()

        rows = session.execute(
            text(
                "select id,provider_item_id,item_id,item_id_resolution_source,"
                "created_at,updated_at,synced_at from fact_walmart_order_items "
                "where source_account_ref=:account order by created_at,id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert len(rows) == 1
        assert rows[0][:6] == (*first[:4], first.created_at, first.updated_at)
        assert rows[0].synced_at == observations[-1]
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 0
        )

        provider_confirmed = _single_line_provider_row(item_id="listing-item-0")
        assert runner._write_orders([provider_confirmed]) == 1
        session.commit()
        counts = session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true) "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert counts == (2, 1)
        confirmed = session.execute(
            text(
                "select provider_item_id,item_id,item_id_resolution_source "
                "from fact_walmart_order_items where source_account_ref=:account "
                "and is_identity_current=true"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert confirmed == ("listing-item-0", "listing-item-0", "provider")
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 1
        )


def test_provider_item_conflict_with_listing_resolution_fails_closed(engine: Engine) -> None:
    missing = _single_line_provider_row(item_id=None)
    with Session(engine) as session:
        _insert_listing(session, item_id="listing-item-0")
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        assert runner._write_orders([missing]) == 1
        assert runner._resolve_order_items() == 0
        session.commit()

        with pytest.raises(
            data_pages_real_sync.DataPagesRealSyncError,
            match="DATA_PAGES_ORDER_ITEM_ID_RESOLUTION_CONFLICT",
        ):
            runner._write_orders([_single_line_provider_row(item_id="provider-item-other")])
        session.rollback()

        row = session.execute(
            text(
                "select count(*) over (),provider_item_id,item_id,item_id_resolution_source "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert row == (1, None, "listing-item-0", "listing_local_sku_unique")
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 0
        )


def test_ambiguous_listing_item_resolution_remains_unresolved(engine: Engine) -> None:
    with Session(engine) as session:
        _insert_listing(session, item_id="listing-item-a")
        _insert_listing(session, item_id="listing-item-b")
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        assert runner._write_orders([_single_line_provider_row(item_id=None)]) == 1
        assert runner._resolve_order_items() == 1
        session.commit()
        assert session.execute(
            text(
                "select provider_item_id,item_id,item_id_resolution_source "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one() == (None, None, None)


def test_repeated_snapshot_transitions_keep_distinct_audit_events(engine: Engine) -> None:
    with Session(engine) as session:
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        for amount in ("10", "12", "10", "12"):
            assert runner._write_orders([_single_line_provider_row(amount=amount)]) == 1
            session.commit()

        counts = session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true),"
                "count(distinct canonical_identity_hash) "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert counts == (4, 1, 1)
        transitions = session.execute(
            text(
                "select prior_fact_id,canonical_fact_id,prior_snapshot_hash,"
                "observed_snapshot_hash from audit_walmart_order_item_conflicts "
                "where source_account_ref=:account order by observed_at,id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert len(transitions) == 3
        assert len({(row.prior_fact_id, row.canonical_fact_id) for row in transitions}) == 3
        hash_pair_counts = Counter(
            (row.prior_snapshot_hash, row.observed_snapshot_hash) for row in transitions
        )
        assert sorted(hash_pair_counts.values()) == [1, 2]

        assert runner._write_orders([_single_line_provider_row(amount="12")]) == 1
        session.commit()
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 3
        )

        assert runner._write_orders([_single_line_provider_row(amount="14")]) == 1
        session.rollback()
        assert session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true) "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one() == (4, 1)
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 3
        )


def test_late_order_numbers_are_versioned_and_enable_refund_matching(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_observation = datetime(2026, 10, 20, 1, tzinfo=UTC)
    completed_observation = datetime(2026, 10, 20, 2, tzinfo=UTC)
    replay_observation = datetime(2026, 10, 20, 3, tzinfo=UTC)
    initial = _single_line_provider_row(
        order_id="order-number-fill",
        line_id="line-number-fill",
    )
    completed = dict(initial)
    completed["reference_no"] = "reference-filled"
    completed_items = [dict(item) for item in cast(list[dict[str, object]], initial["item_info"])]
    completed_items[0]["platform_order_no"] = "platform-filled"
    completed["item_info"] = completed_items

    with Session(engine) as session:
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: first_observation)
        assert runner._write_orders([initial]) == 1
        session.commit()

        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: completed_observation)
        assert runner._write_orders([completed]) == 1
        session.commit()

        versions = session.execute(
            text(
                "select id,platform_order_no,reference_no,is_identity_current,"
                "created_at,updated_at,synced_at from fact_walmart_order_items "
                "where source_account_ref=:account order by created_at,id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert len(versions) == 2
        assert versions[0][1:4] == (None, None, False)
        assert versions[0][4:] == (
            first_observation,
            first_observation,
            first_observation,
        )
        assert versions[1][1:4] == ("platform-filled", "reference-filled", True)

        transition = session.execute(
            text(
                "select prior_fact_id,canonical_fact_id,differing_fields_json "
                "from audit_walmart_order_item_conflicts "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert transition.prior_fact_id == versions[0].id
        assert transition.canonical_fact_id == versions[1].id
        assert transition.differing_fields_json == ["platform_order_no", "reference_no"]

        for refund in (
            {
                "purchase_order_id": "platform-filled",
                "store_id": "store-a",
                "item_id": "item-0",
                "msku": "msku-0",
            },
            {
                "customer_order_id": "reference-filled",
                "store_id": "store-a",
                "item_id": "item-0",
                "msku": "msku-0",
            },
        ):
            matched = runner._match_refund_order_line(refund)
            assert matched is not None
            assert matched["id"] == versions[1].id
            assert matched["source_order_line_id"] == "line-number-fill"

        monkeypatch.setattr(data_pages_real_sync, "_now", lambda: replay_observation)
        assert runner._write_orders([completed]) == 1
        session.commit()

        replayed = session.execute(
            text(
                "select id,platform_order_no,reference_no,is_identity_current,"
                "created_at,updated_at,synced_at from fact_walmart_order_items "
                "where source_account_ref=:account order by created_at,id"
            ),
            {"account": _ACCOUNT},
        ).all()
        assert len(replayed) == 2
        assert replayed[0] == versions[0]
        assert replayed[1][:6] == versions[1][:6]
        assert replayed[1].synced_at == replay_observation
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 1
        )


def test_same_snapshot_change_across_identities_does_not_cross_deduplicate(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        for amount in ("10", "12"):
            rows = [
                _single_line_provider_row(order_id="order-a", line_id="line-a", amount=amount),
                _single_line_provider_row(order_id="order-b", line_id="line-b", amount=amount),
            ]
            assert runner._write_orders(rows) == 2
            session.commit()
        assert session.execute(
            text(
                "select count(*),count(distinct canonical_identity_hash) "
                "from audit_walmart_order_item_conflicts "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one() == (2, 2)


def test_concurrent_order_replay_creates_one_current_identity(engine: Engine) -> None:
    barrier = Barrier(2)
    row = _single_line_provider_row(item_id=None)

    with Session(engine) as session:
        _insert_listing(session, item_id="listing-item-0")
        session.commit()

    def write_once() -> None:
        with Session(engine) as session:
            runner = DataPagesRealSyncRunner(
                session=session,
                client=None,
                source_account_ref=_ACCOUNT,
                business_date=date(2026, 10, 16),
                page_size=20,
                campaign_type="SP",
                max_advertisers=1,
            )
            barrier.wait()
            assert runner._write_orders([row]) == 1
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write_once) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)

    with Session(engine) as session:
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        assert runner._resolve_order_items() == 0
        session.commit()
        counts = session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true) "
                "from fact_walmart_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        lineage = session.execute(
            text(
                "select provider_item_id,item_id,item_id_resolution_source "
                "from fact_walmart_order_items where source_account_ref=:account "
                "and is_identity_current=true"
            ),
            {"account": _ACCOUNT},
        ).one()
    assert counts == (1, 1)
    assert lineage == (None, "listing-item-0", "listing_local_sku_unique")


def test_verified_v3_v5_samples_reject_evidence_changes_without_mart_loss(
    engine: Engine,
) -> None:
    now = datetime.now(UTC)
    purchase_at = str(int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp()))
    provider_row: dict[str, object] = {
        "global_order_no": "sample-order-a",
        "global_purchase_time": purchase_at,
        "store_id": "store-a",
        "status": "created",
        "amount_currency": "USD",
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [
            {
                "order_item_no": "sample-line-a",
                "platform_order_no": "sample-platform-order-a",
                "item_id": "item-a",
                "msku": "msku-a",
                "local_sku": "sku-a",
                "quantity": "1",
                "unit_price_amount": "0",
            }
        ],
    }
    with Session(engine) as session:
        session.execute(
            text(
                "insert into dim_walmart_listings "
                "(id,source_account_ref,platform_code,store_id,item_id,msku,local_sku,"
                "synced_at,created_at,updated_at) values "
                "(:id,:account,'walmart','store-a','item-a','msku-a','sku-a',"
                ":now,:now,:now)"
            ),
            {"id": str(uuid4()), "account": _ACCOUNT, "now": now},
        )
        session.execute(
            text(
                "insert into fact_walmart_sales_item_daily "
                "(id,business_date_la,source_account_ref,platform_code,store_id,item_id,"
                "msku,local_sku,sales_qty,order_count,sales_amount,sales_currency_code,"
                "allocation_status,synced_at,created_at,updated_at) values "
                "(:id,:day,:account,'walmart','store-a','item-a','msku-a','sku-a',"
                "9,9,90,'USD','direct',:now,:now,:now)"
            ),
            {
                "id": str(uuid4()),
                "day": date(2026, 10, 16),
                "account": _ACCOUNT,
                "now": now,
            },
        )
        session.execute(
            text(
                "insert into fact_walmart_sample_order_items "
                "(id,business_date_utc_minus_7,business_timezone,source_account_ref,"
                "source_order_id,platform_order_no,store_id,platform_code,source_order_line_id,"
                "item_id,msku,local_sku,quantity,unit_price_amount,unit_price_currency_code,"
                "order_total_amount,"
                "order_total_currency_code,is_cancelled,is_valid_sample,sample_rule_version,"
                "synced_at,created_at,updated_at) values "
                "(:id,:day,'America/Los_Angeles',:account,'sample-order-a',"
                "'sample-platform-order-a','store-a','10008','sample-line-a','item-a',"
                "'msku-a','sku-a',1,0,'USD',0,'USD',false,true,:rule,:now,:now,:now)"
            ),
            {
                "id": str(uuid4()),
                "day": date(2026, 10, 16),
                "account": _ACCOUNT,
                "rule": HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION,
                "now": now,
            },
        )
        session.commit()
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )

        assert runner._write_sample_orders([provider_row]) == 1
        session.commit()
        preserved = session.execute(
            text(
                "select is_valid_sample,sample_rule_version "
                "from fact_walmart_sample_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert preserved == (True, HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION)

        assert runner._refresh_daily_sales_mart() == 1
        session.commit()
        mart_before = session.execute(
            text(
                "select gross_sales_qty,sample_order_count,sample_qty,sales_qty "
                "from mart_daily_sales_item_day where source_account_ref=:account "
                "and business_date_la=:day and store_id='store-a' and item_id='item-a'"
            ),
            {"account": _ACCOUNT, "day": date(2026, 10, 16)},
        ).one()
        assert mart_before == (9, 1, 1, 8)

        base_item = cast(list[dict[str, object]], provider_row["item_info"])[0]
        conflicts: list[dict[str, object]] = []
        for changed_item in (
            {**base_item, "unit_price_currency_code": "CNY"},
            {**base_item, "local_sku": "sku-b"},
            {**base_item, "local_sku": None},
            {**base_item, "item_id": "item-b"},
            {**base_item, "msku": "msku-b"},
            {**base_item, "quantity": "2"},
            {**base_item, "unit_price_amount": "1"},
        ):
            conflicts.append({**provider_row, "item_info": [changed_item]})
        conflicts.append(
            {
                **provider_row,
                "transaction_info": [{"order_total_amount": "2"}],
                "item_info": [{**base_item, "item_price_amount": "10", "discount_amount": "10"}],
            }
        )
        conflicts.append({**provider_row, "amount_currency": "CNY"})
        conflicts.append({**provider_row, "status": "cancelled"})

        for changed in conflicts:
            with pytest.raises(
                DataPagesMartInvariantError,
                match="DATA_PAGES_VERIFIED_SAMPLE_CHANGED",
            ):
                runner._write_sample_orders([changed])
            session.rollback()
            preserved_after_conflict = session.execute(
                text(
                    "select is_valid_sample,sample_rule_version,item_id,msku,local_sku,"
                    "quantity,unit_price_amount,unit_price_currency_code,order_total_amount,"
                    "order_total_currency_code,is_cancelled "
                    "from fact_walmart_sample_order_items where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            ).one()
            assert preserved_after_conflict == (
                True,
                HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION,
                "item-a",
                "msku-a",
                "sku-a",
                1,
                0,
                "USD",
                0,
                "USD",
                False,
            )
            mart_after_conflict = session.execute(
                text(
                    "select sample_order_count,sample_qty,sales_qty "
                    "from mart_daily_sales_item_day where source_account_ref=:account "
                    "and business_date_la=:day and store_id='store-a' and item_id='item-a'"
                ),
                {"account": _ACCOUNT, "day": date(2026, 10, 16)},
            ).one()
            assert mart_after_conflict == (1, 1, 8)

        session.execute(
            text(
                "update fact_walmart_sample_order_items set sample_rule_version=:rule "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT, "rule": VERIFIED_SAMPLE_RULE_VERSION},
        )
        session.commit()
        assert runner._write_sample_orders([provider_row]) == 1
        session.commit()
        assert session.execute(
            text(
                "select is_valid_sample,sample_rule_version "
                "from fact_walmart_sample_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one() == (True, VERIFIED_SAMPLE_RULE_VERSION)

        v5_changed = {**provider_row, "item_info": [{**base_item, "item_id": "item-b"}]}
        with pytest.raises(
            DataPagesMartInvariantError,
            match="DATA_PAGES_VERIFIED_SAMPLE_CHANGED",
        ):
            runner._write_sample_orders([v5_changed])
        session.rollback()
        assert session.execute(
            text(
                "select is_valid_sample,sample_rule_version,item_id "
                "from fact_walmart_sample_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one() == (True, VERIFIED_SAMPLE_RULE_VERSION, "item-a")


def test_isolated_database_guard_rejects_application_database() -> None:
    unsafe = make_url("postgresql+psycopg://application@127.0.0.1/szzsbj_app")
    with pytest.raises(SettingsError, match="dedicated local database"):
        _validate_url(unsafe)
