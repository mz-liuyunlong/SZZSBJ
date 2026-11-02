"""ODS (cargo + goods + shipping lists) → published WFS shipment board."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.integrations.lingxing.pmc_wfs_contracts import (
    WFS_CARGO_PAGE_ENDPOINT,
    WFS_SHIPPING_LIST_PAGE_ENDPOINT,
)
from app.modules.integration_sync.models import ApiRawBlob, ApiRawRequestRef, IntegrationSyncRun
from app.modules.integration_sync.parsers.lingxing_wfs_board import parse_wfs_page
from app.modules.pmc_wfs.board_publisher import (
    WfsBoardPublisher,
    WfsBoardPublishError,
    build_board_rows,
    provider_datetime,
)
from app.modules.pmc_wfs.lingxing_models import (
    LingxingWfsCargoGoodsOds,
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
    WfsBoardPublication,
    WfsShipmentBoardRow,
)
from tests.modules.pmc_wfs.wfs_board_fixtures import CARGOS, SHIPPING_LISTS, page

ACCOUNT = "primary"
T1 = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
TABLES = (
    "gov_integration_sync_runs",
    "ods_api_raw_blobs",
    "ods_api_raw_request_refs",
    "ods_lingxing_wfs_cargos",
    "ods_lingxing_wfs_cargo_goods",
    "ods_lingxing_wfs_shipping_lists",
    "gov_wfs_board_publications",
    "mart_wfs_shipment_board",
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_functions(dbapi_connection: object, _record: object) -> None:
        # PostgreSQL CHECK constraints use char_length(); SQLite has only length().
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    with engine.begin() as conn:
        # PostgreSQL partial index (WHERE status = 'running'); SQLite ignores the predicate and
        # would reject a second run of the same interface, which this suite needs.
        conn.execute(text("DROP INDEX IF EXISTS uq_gov_integration_sync_runs_running"))
    with Session(engine) as s:
        yield s
    engine.dispose()


def _run(session: Session, interface_key: str, *, status: str = "succeeded") -> UUID:
    run_id = uuid4()
    session.add(
        IntegrationSyncRun(
            id=run_id,
            interface_id=uuid4(),
            provider="lingxing",
            interface_key=interface_key,
            source_account_ref=ACCOUNT,
            trigger_type="manual",
            status=status,
            idempotency_key=f"wfs:{run_id}",
            window_start=datetime(2026, 6, 1, tzinfo=UTC),
            window_end=datetime(2026, 10, 30, tzinfo=UTC),
            queued_at=T1,
            started_at=T1,
            finished_at=T1,
        )
    )
    session.flush()
    return run_id


def _ref(session: Session, run_id: UUID) -> UUID:
    # sqlite does not enforce the FK targets; placeholder ids stand in for policy/work item.
    blob_id = uuid4()
    session.add(
        ApiRawBlob(
            id=blob_id,
            response_hash=sha256(uuid4().bytes).hexdigest(),
            payload_json={},
            payload_bytes=2,
            content_type="application/json",
            storage_mode="database",
            retention_policy_id=uuid4(),
            received_at=T1,
        )
    )
    ref_id = uuid4()
    session.add(
        ApiRawRequestRef(
            id=ref_id,
            run_id=run_id,
            work_item_id=uuid4(),
            raw_blob_id=blob_id,
            request_kind="offset_page",
            attempt_no=1,
            request_safe_params={"offset": 0, "length": 200},
            http_status=200,
            provider_code="0",
            is_success=True,
            response_count=3,
            requested_at=T1,
            received_at=T1,
        )
    )
    session.flush()
    return ref_id


def _load_ods(session: Session) -> tuple[UUID, UUID]:
    cargo_run = _run(session, "wfsCargoPage")
    cargo_ref = _ref(session, cargo_run)
    parsed = parse_wfs_page(WFS_CARGO_PAGE_ENDPOINT, page(CARGOS, 3))
    for ordinal, header in enumerate(parsed.headers):
        session.add(
            LingxingWfsCargoOds(
                run_id=cargo_run,
                raw_request_ref_id=cargo_ref,
                source_account_ref=ACCOUNT,
                source_item_ordinal=ordinal,
                observed_at=T1,
                **header.columns,
            )
        )
        for child in header.children:
            session.add(
                LingxingWfsCargoGoodsOds(
                    run_id=cargo_run,
                    raw_request_ref_id=cargo_ref,
                    source_account_ref=ACCOUNT,
                    source_item_ordinal=ordinal,
                    observed_at=T1,
                    **child.columns,
                )
            )
    shipping_run = _run(session, "wfsShippingListPage")
    shipping_ref = _ref(session, shipping_run)
    parsed_shipping = parse_wfs_page(WFS_SHIPPING_LIST_PAGE_ENDPOINT, page(SHIPPING_LISTS, 2))
    for ordinal, header in enumerate(parsed_shipping.headers):
        session.add(
            LingxingWfsShippingListOds(
                run_id=shipping_run,
                raw_request_ref_id=shipping_ref,
                source_account_ref=ACCOUNT,
                source_item_ordinal=ordinal,
                observed_at=T1,
                **header.columns,
            )
        )
    session.commit()
    return cargo_run, shipping_run


def test_provider_datetime_converts_shanghai_wall_clock_to_utc() -> None:
    assert provider_datetime("2026-10-16 15:23:28") == datetime(2026, 10, 16, 7, 23, 28, tzinfo=UTC)
    assert provider_datetime("2026-10-16") == datetime(2026, 10, 15, 16, 0, tzinfo=UTC)
    assert provider_datetime("1970-01-01") is None
    assert provider_datetime("") is None and provider_datetime(None) is None


def test_build_board_rows_joins_goods_and_shipping_by_both_links(session: Session) -> None:
    _load_ods(session)
    cargos = list(session.scalars(select(LingxingWfsCargoOds)))
    goods = list(session.scalars(select(LingxingWfsCargoGoodsOds)))
    shipping = list(session.scalars(select(LingxingWfsShippingListOds)))

    rows = {r["cargo_code"]: r for r in build_board_rows(cargos, goods, shipping)}

    first = rows["3292441WFB"]
    assert first["shipping_codes"] == ["SP202610160010009"]  # via shipping_list_codes
    assert first["declared_units"] == 72 and first["received_units"] == 0
    assert first["actual_delivery_date"] == date(2026, 10, 18)
    assert first["expected_arrival_date"] == date(2026, 11, 5)
    assert first["logistics_numbers"] == ["ZY010009"]
    assert first["cargo_created_at"] == datetime(2026, 10, 16, 7, 23, 28, tzinfo=UTC)
    second = rows["3292442WFB"]
    assert second["shipping_codes"] == ["SP202610170010010"]  # via shipping_goods[].cargo_code
    assert second["declared_units"] == 50 and second["received_units"] == 48
    assert second["damaged_units"] == 2 and second["sku_count"] == 2
    assert second["arrival_date"] == date(2026, 10, 28)
    assert second["status_name"] == "RECEIVING_IN_PROGRESS"
    assert len(second["payload_json"]["goods"]) == 2
    third = rows["3292443WFB"]
    assert third["shipping_codes"] == [] and third["declared_units"] is None
    assert third["warehouse_id"] is None and third["sku_count"] == 0


def test_publish_writes_version_and_flips_current(session: Session) -> None:
    cargo_run, shipping_run = _load_ods(session)
    publisher = WfsBoardPublisher(session)

    first = publisher.publish(account=ACCOUNT, cargo_run_id=cargo_run, shipping_run_id=shipping_run)
    assert first.rows == 3 and first.cargos_without_shipping == 1
    assert first.coverage_start == date(2026, 6, 1) and first.coverage_end == date(2026, 10, 30)
    pub = session.get(WfsBoardPublication, first.publication_id)
    assert pub is not None and pub.is_current is True
    assert pub.quality_report["rows"] == 3 and pub.quality_report["shipping_lists"] == 2
    board = list(
        session.scalars(
            select(WfsShipmentBoardRow).where(
                WfsShipmentBoardRow.publication_id == first.publication_id
            )
        )
    )
    assert {r.cargo_code for r in board} == {"3292441WFB", "3292442WFB", "3292443WFB"}

    second = publisher.publish(account=ACCOUNT, cargo_run_id=cargo_run, shipping_run_id=None)
    assert second.cargos_without_shipping == 3
    current = list(
        session.scalars(
            select(WfsBoardPublication).where(
                WfsBoardPublication.source_account_ref == ACCOUNT,
                WfsBoardPublication.is_current.is_(True),
            )
        )
    )
    assert [p.id for p in current] == [second.publication_id]
    assert session.get(WfsBoardPublication, first.publication_id).is_current is False


def test_publish_requires_succeeded_matching_runs(session: Session) -> None:
    cargo_run, shipping_run = _load_ods(session)
    failed = _run(session, "wfsCargoPage", status="failed")
    session.commit()
    publisher = WfsBoardPublisher(session)
    with pytest.raises(WfsBoardPublishError) as not_succeeded:
        publisher.publish(account=ACCOUNT, cargo_run_id=failed, shipping_run_id=None)
    assert not_succeeded.value.code == "WFS_BOARD_SUCCESSFUL_RUNS_REQUIRED"
    with pytest.raises(WfsBoardPublishError) as swapped:
        publisher.publish(account=ACCOUNT, cargo_run_id=shipping_run, shipping_run_id=cargo_run)
    assert swapped.value.code == "WFS_BOARD_RUN_INTERFACE_MISMATCH"
    with pytest.raises(WfsBoardPublishError) as wrong_account:
        publisher.publish(account="other", cargo_run_id=cargo_run, shipping_run_id=None)
    assert wrong_account.value.code == "WFS_BOARD_SUCCESSFUL_RUNS_REQUIRED"
