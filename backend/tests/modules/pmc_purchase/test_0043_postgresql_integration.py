"""PostgreSQL 14 compatibility proof for the production-observed PMC 0043 revision.

The test is opt-in and accepts only a dedicated local/CI database. It creates synthetic
rows; it never reads production data. The downgrade check first removes the synthetic
``from_listing`` rows because a production downgrade with such rows is intentionally unsafe.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.auth import Principal, get_optional_principal
from app.core.config import Settings, SettingsError, get_test_database_url
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_purchase.gate3_models import DwsPurchaseBoard
from app.modules.pmc_purchase.schemas import BoardListQuery

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION_0042 = "20261017_0042_rbac_backfill"
REVISION_0043 = "20261017_0043_purchase_board_listing_item_source"
DATABASE_NAME = "pmc_0043_test"
DATABASE_USER = "pmc_0043_test"
ACCOUNT = "synthetic-0043-account"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
OLD_SOURCES = (
    "from_system_plan",
    "from_plan_remark",
    "from_packing_slip",
    "pending_packing_slip",
    "unresolved",
)
ALL_SOURCES = (*OLD_SOURCES[:2], "from_listing", *OLD_SOURCES[2:])


def _isolated_database_url() -> URL:
    if os.environ.get("PMC_0043_POSTGRESQL_TESTS") != "1":
        pytest.skip("PostgreSQL 14 PMC 0043 test requires explicit opt-in")
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.fail("PMC 0043 PostgreSQL test database is not configured", pytrace=False)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database != DATABASE_NAME
        or url.username != DATABASE_USER
        or url.query
    ):
        pytest.fail("PMC 0043 tests require the dedicated local test database", pytrace=False)
    return url


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    engine = create_engine(_isolated_database_url(), poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            database, username, version = connection.execute(
                text(
                    "select current_database(), current_user, current_setting('server_version_num')"
                )
            ).one()
        assert database == DATABASE_NAME
        assert username == DATABASE_USER
        version_number = int(version)
        assert version_number >= 140000
        expected_major = os.environ.get("PMC_0043_EXPECTED_POSTGRES_MAJOR")
        if expected_major is not None:
            assert version_number // 10000 == int(expected_major)
        yield engine
    finally:
        engine.dispose()


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.scalar(text("select version_num from alembic_version")))


def _source_constraint(engine: Engine) -> str:
    with engine.connect() as connection:
        value = connection.scalar(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conname = 'ck_dws_purchase_board_item_id_source'"
            )
        )
    assert value is not None
    return str(value)


def _board_row(index: int, source: str) -> DwsPurchaseBoard:
    matched = source not in {"pending_packing_slip", "unresolved"}
    match_status = (
        "matched" if matched else "pending" if source == "pending_packing_slip" else "unresolved"
    )
    return DwsPurchaseBoard(
        source_account_ref=ACCOUNT,
        calc_version="0043-compat-test",
        rule_version=1,
        calculated_at=NOW,
        source_lineage_json={"synthetic": True},
        order_sn=f"SYN-{source}-{index:04d}",
        order_item_id=f"LINE-{source}-{index:04d}",
        plan_key="",
        plan_sns_json=[],
        stage_code="S3",
        overdue_days=0,
        stage_start_estimated=False,
        store_attributed=True,
        item_id=f"synthetic-item-{index:04d}" if matched else None,
        item_id_source=source,
        item_id_match_status=match_status,
        quantity_allocated=1,
        quantity_received=0,
        remaining_quantity=1,
        sku_cycle_unstable=False,
    )


def _api(engine: Engine) -> TestClient:
    application = create_app()

    def database_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db_session] = database_session
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"page:pmc:purchase-board:view"}),
    )
    application.dependency_overrides[require_source_account_scope] = lambda: frozenset({ACCOUNT})
    return TestClient(application)


def test_0042_to_0043_reads_all_sources_and_647_synthetic_rows(
    postgres_engine: Engine,
) -> None:
    assert _revision(postgres_engine) == REVISION_0042
    assert "from_listing" not in _source_constraint(postgres_engine)

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, REVISION_0043)
    assert _revision(postgres_engine) == REVISION_0043
    assert "from_listing" in _source_constraint(postgres_engine)

    query = BoardListQuery(item_id_source=list(ALL_SOURCES))  # type: ignore[arg-type]
    assert len(query.item_id_source) == 6
    with pytest.raises(ValidationError):
        BoardListQuery.model_validate({"item_id_source": ["unknown_source"]})

    with Session(postgres_engine) as session:
        session.add_all(_board_row(index, "from_listing") for index in range(647))
        session.add_all(
            _board_row(10_000 + index, source) for index, source in enumerate(OLD_SOURCES)
        )
        session.commit()

    client = _api(postgres_engine)
    page_one = client.get(
        "/api/pmc/purchase/board",
        params={"item_id_source": "from_listing", "page": 1, "page_size": 200},
    )
    assert page_one.status_code == 200
    page_one_body = page_one.json()
    assert page_one_body["data"]["total"] == 647
    assert len(page_one_body["data"]["items"]) == 200
    assert {item["item_id"]["source"] for item in page_one_body["data"]["items"]} == {
        "from_listing"
    }

    page_four = client.get(
        "/api/pmc/purchase/board",
        params={"item_id_source": "from_listing", "page": 4, "page_size": 200},
    )
    assert page_four.status_code == 200
    assert len(page_four.json()["data"]["items"]) == 47

    detail = client.get("/api/pmc/purchase/orders/SYN-from_listing-0000")
    assert detail.status_code == 200
    assert detail.json()["data"]["lines"][0]["item_id"]["source"] == "from_listing"

    for source in OLD_SOURCES:
        response = client.get(
            "/api/pmc/purchase/board",
            params={"item_id_source": source, "page_size": 10},
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

    with Session(postgres_engine) as session:
        session.add(_board_row(20_000, "not_approved"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with postgres_engine.begin() as connection:
        connection.execute(
            text("delete from dws_purchase_board where item_id_source = 'from_listing'")
        )
        remaining = connection.scalar(
            select(func.count())
            .select_from(DwsPurchaseBoard)
            .where(DwsPurchaseBoard.source_account_ref == ACCOUNT)
        )
        assert remaining == len(OLD_SOURCES)

    # Downgrade is tested only after all new-source rows are gone. Production currently
    # has such rows, so this does not authorize or imply a safe production downgrade.
    command.downgrade(config, REVISION_0042)
    assert _revision(postgres_engine) == REVISION_0042
    assert "from_listing" not in _source_constraint(postgres_engine)
    command.upgrade(config, REVISION_0043)
    assert _revision(postgres_engine) == REVISION_0043

    with postgres_engine.begin() as connection:
        connection.execute(
            text("delete from dws_purchase_board where source_account_ref = :account"),
            {"account": ACCOUNT},
        )
