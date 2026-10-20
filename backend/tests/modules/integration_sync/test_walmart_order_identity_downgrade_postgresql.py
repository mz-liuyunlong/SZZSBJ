from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import Settings, SettingsError, get_test_database_url

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261020_0047_walmart_order_identity_guard"
PREVIOUS = "20261019_0046_operation_logs"
_DATABASE = "walmart_order_identity_test"
_USERNAME = "walmart_order_identity_test"
_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ACCOUNT = "synthetic-downgrade-guard"


def _database_url() -> URL:
    if os.environ.get("WALMART_ORDER_IDENTITY_DB_TESTS") != "1":
        pytest.skip("real Walmart order identity PostgreSQL test requires explicit opt-in")
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError) as exc:
        pytest.fail(str(exc), pytrace=False)
    if (
        url.host not in _HOSTS
        or url.database != _DATABASE
        or url.username != _USERNAME
        or url.query
    ):
        pytest.fail("downgrade test requires the dedicated local database", pytrace=False)
    return url


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.scalar(text("select version_num from alembic_version")))


def _insert_fact(
    engine: Engine,
    *,
    row_id: str,
    line_id: str,
    canonical_hash: str,
    current: bool,
) -> None:
    now = datetime(2026, 10, 20, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into fact_walmart_order_items "
                "(id,source_account_ref,store_id,source_order_id,source_order_line_id,"
                "source_line_hash,canonical_identity_hash,is_identity_current,"
                "source_line_ordinal,is_sample_order,synced_at,created_at,updated_at) values "
                "(:id,:account,'store-a','order-a',:line_id,:line_hash,:canonical_hash,"
                ":current,0,false,:now,:now,:now)"
            ),
            {
                "id": row_id,
                "account": _ACCOUNT,
                "line_id": line_id,
                "line_hash": hashlib.sha256(line_id.encode()).hexdigest(),
                "canonical_hash": canonical_hash,
                "current": current,
                "now": now,
            },
        )


def _assert_guard_preserved_schema(engine: Engine) -> None:
    assert _revision(engine) == REVISION
    inspector = inspect(engine)
    assert inspector.has_table("audit_walmart_order_item_conflicts")
    columns = {column["name"] for column in inspector.get_columns("fact_walmart_order_items")}
    assert {"canonical_identity_hash", "is_identity_current"} <= columns


def test_0047_downgrade_is_empty_only_and_preserves_data_on_rejection() -> None:
    engine = create_engine(_database_url(), poolclass=NullPool, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(text("delete from audit_walmart_order_item_conflicts"))
        connection.execute(text("delete from fact_walmart_order_items"))

    current_id = str(uuid4())
    _insert_fact(
        engine,
        row_id=current_id,
        line_id="line-current",
        canonical_hash="a" * 64,
        current=True,
    )
    with pytest.raises(DBAPIError, match="0047 downgrade blocked"):
        command.downgrade(_config(), PREVIOUS)
    _assert_guard_preserved_schema(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("select count(*) from fact_walmart_order_items where id=cast(:id as uuid)"),
                {"id": current_id},
            )
            == 1
        )

    with engine.begin() as connection:
        connection.execute(text("delete from fact_walmart_order_items"))

    prior_id = str(uuid4())
    canonical_id = str(uuid4())
    _insert_fact(
        engine,
        row_id=prior_id,
        line_id="line-prior",
        canonical_hash="b" * 64,
        current=False,
    )
    _insert_fact(
        engine,
        row_id=canonical_id,
        line_id="line-canonical",
        canonical_hash="b" * 64,
        current=False,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into audit_walmart_order_item_conflicts "
                "(id,canonical_identity_hash,source_account_ref,store_id,source_order_id,"
                "source_order_line_id,prior_fact_id,canonical_fact_id,prior_snapshot_hash,"
                "observed_snapshot_hash,differing_fields_json,resolution_status,observed_at,"
                "created_at) values (:id,:canonical_hash,:account,'store-a','order-a',"
                "'line-a',cast(:prior_id as uuid),cast(:canonical_id as uuid),:prior_hash,"
                ":observed_hash,cast('[\"quantity\"]' as jsonb),'observed',:now,:now)"
            ),
            {
                "id": str(uuid4()),
                "canonical_hash": "b" * 64,
                "account": _ACCOUNT,
                "prior_id": prior_id,
                "canonical_id": canonical_id,
                "prior_hash": "c" * 64,
                "observed_hash": "d" * 64,
                "now": datetime(2026, 10, 20, tzinfo=UTC),
            },
        )
    with pytest.raises(DBAPIError, match="0047 downgrade blocked"):
        command.downgrade(_config(), PREVIOUS)
    _assert_guard_preserved_schema(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 1
        )

    with engine.begin() as connection:
        connection.execute(text("delete from audit_walmart_order_item_conflicts"))
        connection.execute(text("delete from fact_walmart_order_items"))

    command.downgrade(_config(), PREVIOUS)
    assert _revision(engine) == PREVIOUS
    inspector = inspect(engine)
    assert not inspector.has_table("audit_walmart_order_item_conflicts")
    columns = {column["name"] for column in inspector.get_columns("fact_walmart_order_items")}
    assert "canonical_identity_hash" not in columns
    assert "provider_item_id" not in columns

    command.upgrade(_config(), REVISION)
    assert _revision(engine) == REVISION
    upgraded = {
        column["name"] for column in inspect(engine).get_columns("fact_walmart_order_items")
    }
    assert {"canonical_identity_hash", "provider_item_id", "item_id_resolution_source"} <= upgraded
    engine.dispose()
