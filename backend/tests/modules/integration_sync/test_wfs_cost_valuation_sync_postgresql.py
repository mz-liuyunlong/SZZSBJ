"""WFS cost valuation flow sync on a disposable PostgreSQL database (synthetic data only).

Opt-in: DOMESTIC_CHAIN_DB_TESTS=1 with the dedicated local ``domestic_chain_ci`` cluster.
No provider is called: every page comes from an in-memory fake client.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.integrations.lingxing.client import LingxingRawEnvelope
from app.integrations.lingxing.wfs_cost_valuation_contracts import WFS_COST_VALUATION_ENDPOINT
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.handlers.lingxing_wfs_cost_valuation_sync import (
    LingxingWfsCostValuationSyncHandler,
    advisory_lock_key,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
)
from app.modules.integration_sync.wfs_cost_valuation_catalog import WFS_COST_VALUATION_SYNC_SPEC
from app.modules.warehouse_wfs.inventory_flow_models import WfsCostValuationFlowOds
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic

ACCOUNT = "fixture-account"
NOW = datetime(2026, 10, 20, tzinfo=UTC)
WINDOW = (date(2026, 10, 1), date(2026, 10, 10))


# --------------------------------------------------------------------------- fixtures
@pytest.fixture()
def engine() -> Iterator[sa.Engine]:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    database = create_database(url, "wfscostflow")
    created = None
    try:
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        created = sa.create_engine(url.set(database=database), hide_parameters=True)
        yield created
    finally:
        if created is not None:
            created.dispose()
        drop_database(url, database)


@pytest.fixture()
def session(engine: sa.Engine) -> Iterator[Session]:
    with Session(engine) as value:
        yield value


class FakeClient:
    def __init__(self, pages: list[LingxingRawEnvelope]) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    def fetch_wfs_cost_valuation_page(self, **kwargs: object) -> LingxingRawEnvelope:
        self.calls.append(kwargs)
        return self.pages.pop(0)


def record(
    index: int,
    *,
    store: str = "ZZ0001-合成店铺A",
    business_type: str = "CCA",
    quantity: int = -1,
    day: str = "2026-10-02",
    serial: str | None = None,
    sid: str = "",
) -> dict[str, JsonValue]:
    return {
        "sid": sid,
        "dateLocal": f"{day} 08:00:{index % 60:02d}",
        "imageUrl": "https://example.invalid/image.png",
        "gtin": f"0000000000{index:04d}",
        "msku": f"SYN-MSKU-{index % 3}",
        "title": "synthetic title",
        "localName": "合成品名",
        "localSku": f"SYN-SKU-{index % 3}",
        "sellerName": store,
        "businessType": business_type,
        "businessName": "库存调整出库",
        "businessDesc": "Lost/Found Item",
        "quantity": quantity,
        "businessNumber": f"SYN-SHIP-{index}",
        "costSource": "shipment:SYN",
        "orderBasePurchaseAmount": "1.0000",
        "purchaseTotalAmount": "-1.0000",
        "orderBaseLogisticsAmount": "0.5000",
        "logisticsTotalAmount": "-0.5000",
        "orderBaseOtherAmount": "0",
        "otherTotalAmount": "0",
        "orderNumber": f"SYN-ORDER-{index}",
        "date1": f"{day} 00:00:00",
        "serialNumber": serial or f"SYNSERIAL{index:06d}",
    }


def page(rows: list[dict[str, JsonValue]], total: int, page_no: int) -> LingxingRawEnvelope:
    payload = cast(JsonValue, {"code": 0, "data": {"page": {"records": rows, "total": total}}})
    return LingxingRawEnvelope(
        api_path=WFS_COST_VALUATION_ENDPOINT,
        request_body_json={"offset": 0, "length": 2},
        response_json=payload,
        response_code=200,
        is_success=True,
        pulled_at=NOW,
        page_no=page_no,
        page_size=2,
        object_type="wfs_cost_valuation_flow",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="work-fixture",
        attempt_no=1,
    )


def bootstrap(
    session: Session, *, enable: bool = True
) -> tuple[IntegrationInterface, IntegrationSyncConfig]:
    IntegrationCatalogService(session).bootstrap_wfs_cost_valuation_governance(ACCOUNT)
    interface = session.scalar(
        sa.select(IntegrationInterface).where(
            IntegrationInterface.interface_key == WFS_COST_VALUATION_SYNC_SPEC.interface_key
        )
    )
    assert interface is not None
    config = session.scalar(
        sa.select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    )
    assert config is not None
    if enable:
        interface.outbound_enabled = True
        config.is_enabled = True
        config.page_size = 2
    session.commit()
    return interface, config


def new_run(
    session: Session,
    config: IntegrationSyncConfig,
    interface: IntegrationInterface,
    *,
    status: str = "running",
    window: tuple[date, date] = WINDOW,
) -> IntegrationSyncRun:
    run = IntegrationSyncRun(
        id=uuid4(),
        config_id=config.id,
        interface_id=interface.id,
        provider="lingxing",
        interface_key=WFS_COST_VALUATION_SYNC_SPEC.interface_key,
        source_account_ref=ACCOUNT,
        trigger_type="manual",
        status=status,
        idempotency_key=f"fixture-{uuid4().hex}",
        window_start=datetime.combine(window[0], datetime.min.time(), UTC),
        window_end=datetime.combine(window[1], datetime.min.time(), UTC),
        started_at=NOW if status == "running" else None,
    )
    session.add(run)
    session.commit()
    return run


def add_store(session: Session, store_id: str, name: str, sid: str | None = None) -> None:
    session.add(
        LingxingStoreDimension(
            source_account_ref=ACCOUNT,
            platform_code_raw="10008",
            platform_code="walmart",
            store_id=store_id,
            store_name=name,
            sid=sid,
            synced_at=NOW,
        )
    )
    session.commit()


def current_rows(session: Session) -> list[WfsCostValuationFlowOds]:
    session.expire_all()
    return list(
        session.scalars(
            sa.select(WfsCostValuationFlowOds)
            .where(WfsCostValuationFlowOds.is_current.is_(True))
            .order_by(WfsCostValuationFlowOds.business_number)
        )
    )


def run_sync(
    session: Session, pages: list[LingxingRawEnvelope], *, window: tuple[date, date] = WINDOW
) -> tuple[IntegrationSyncRun, FakeClient, object]:
    interface, config = bootstrap(session)
    run = new_run(session, config, interface, window=window)
    client = FakeClient(pages)
    result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(run, interface)
    session.refresh(run)
    return run, client, result


# ------------------------------------------------------------------------------ tests
def test_default_off_governance_never_reaches_the_client(session: Session) -> None:
    interface, config = bootstrap(session, enable=False)
    assert interface.outbound_enabled is False
    assert config.is_enabled is False
    assert config.schedule_enabled is False
    assert config.schedule_cron is None
    run = new_run(session, config, interface, status="queued")
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert run.status == "failed"
    assert run.error_code == "SYNC_INTERFACE_DISABLED"

    # Even with outbound enabled, a disabled config stops the handler before any request.
    interface.outbound_enabled = True
    session.commit()
    run2 = new_run(session, config, interface)
    client = FakeClient([])
    result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(run2, interface)
    assert result.status == "failed"
    assert result.error_code == "SYNC_WFS_FLOW_CONFIG_DISABLED"
    assert client.calls == []


def test_pages_all_rows_and_promotes_with_duplicate_serial_numbers(session: Session) -> None:
    rows = [record(1, serial="SYNDUP0000001"), record(2, serial="SYNDUP0000001"), record(3)]
    run, client, result = run_sync(session, [page(rows[:2], 3, 1), page(rows[2:], 3, 2)])
    assert run.status == "succeeded", run.error_code
    assert [call["offset"] for call in client.calls] == [0, 2]
    assert all("businessType" not in call for call in client.calls)
    current = current_rows(session)
    assert len(current) == 3
    assert sum(1 for row in current if row.serial_number == "SYNDUP0000001") == 2
    assert {row.source_item_ordinal for row in current} == {0, 1}
    assert all(row.currency_code is None for row in current)
    assert all(len(row.row_hash) == 64 for row in current)
    assert result.records_written == 3  # type: ignore[attr-defined]


def test_window_replacement_retires_only_rows_inside_the_window(session: Session) -> None:
    first, _, _ = run_sync(
        session,
        [page([record(1, day="2026-10-02"), record(2, day="2026-10-20")], 2, 1)],
        window=(date(2026, 10, 1), date(2026, 10, 31)),
    )
    assert first.status == "succeeded"
    second, _, result = run_sync(session, [page([record(7, day="2026-10-03")], 1, 1)])
    assert second.status == "succeeded"
    current = current_rows(session)
    assert {row.business_number for row in current} == {"SYN-SHIP-2", "SYN-SHIP-7"}
    retired = session.scalars(
        sa.select(WfsCostValuationFlowOds).where(WfsCostValuationFlowOds.is_current.is_(False))
    ).all()
    assert [row.business_number for row in retired] == ["SYN-SHIP-1"]
    assert retired[0].superseded_by_run_id == second.id
    assert result.records_superseded == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("pages", "error"),
    [
        ([page([record(1), record(2)], 3, 1), page([], 3, 2)], "SYNC_WFS_FLOW_INCOMPLETE_PAGE"),
        (
            [page([record(1), record(2)], 3, 1), page([record(3)], 4, 2)],
            "SYNC_WFS_FLOW_TOTAL_CHANGED",
        ),
        ([page([record(1), record(2)], 1, 1)], "SYNC_WFS_FLOW_TOTAL_MISMATCH"),
    ],
)
def test_failed_run_leaves_previous_current_rows_untouched(
    session: Session, pages: list[LingxingRawEnvelope], error: str
) -> None:
    good, _, _ = run_sync(session, [page([record(9)], 1, 1)])
    assert good.status == "succeeded"
    before = [(row.id, row.business_number) for row in current_rows(session)]
    bad, _, result = run_sync(session, pages)
    assert bad.status == "failed"
    assert bad.error_code == error
    assert result.status == "failed"  # type: ignore[attr-defined]
    assert [(row.id, row.business_number) for row in current_rows(session)] == before
    staged = session.scalars(
        sa.select(WfsCostValuationFlowOds).where(WfsCostValuationFlowOds.run_id == bad.id)
    ).all()
    assert all(row.is_current is False for row in staged)


def test_invalid_record_fails_the_run_without_promoting(session: Session) -> None:
    broken = record(1)
    broken["quantity"] = "1.5"
    run, _, _ = run_sync(session, [page([broken], 1, 1)])
    assert run.status == "failed"
    assert run.error_code == "SYNC_WFS_FLOW_RECORD_INVALID"
    assert current_rows(session) == []


def test_second_batch_for_same_account_is_rejected_without_requests(
    session: Session, engine: sa.Engine
) -> None:
    interface, config = bootstrap(session)
    # Holder: another worker already owns the per-account advisory lock.
    with engine.connect() as holder:
        assert holder.scalar(
            sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": advisory_lock_key(ACCOUNT)}
        )
        run = new_run(session, config, interface)
        client = FakeClient([page([record(1)], 1, 1)])
        result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(run, interface)
        assert result.status == "failed"
        assert result.error_code == "SYNC_WFS_FLOW_CONCURRENT_RUN"
        assert client.calls == []
        holder.execute(sa.text("SELECT pg_advisory_unlock_all()"))

    # A running run for the same account also blocks a second (queued) run.
    running = new_run(session, config, interface)
    queued = new_run(session, config, interface, status="queued")
    client = FakeClient([page([record(1)], 1, 1)])
    result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(queued, interface)
    assert result.error_code == "SYNC_WFS_FLOW_CONCURRENT_RUN"
    assert client.calls == []
    session.refresh(running)
    assert running.status == "running"


def test_store_mapping_by_sid_by_store_code_and_unmapped(session: Session) -> None:
    add_store(session, "9001", "ZZ0001-合成店铺A", sid="555")
    add_store(session, "9002", "ZZ0002-合成店铺B")
    add_store(session, "9003", "ZZ0003-合成店铺C")
    add_store(session, "9004", "ZZ0003-合成店铺C2")  # same code twice -> ambiguous
    rows = [
        record(1, store="ZZ0009-未知", sid="555"),  # sid wins over a non-matching name
        record(2, store="ZZ0002-合成店铺B"),
        record(3, store="ZZ0003-合成店铺C"),
        record(4, store="ZZ0404-未对照"),
    ]
    run, _, _ = run_sync(session, [page(rows[:2], 4, 1), page(rows[2:], 4, 2)])
    assert run.status == "succeeded", run.error_code
    mapped = {
        row.business_number: (row.store_code, row.store_id, row.store_mapping_status)
        for row in current_rows(session)
    }
    assert mapped == {
        "SYN-SHIP-1": ("ZZ0009", "9001", "mapped"),
        "SYN-SHIP-2": ("ZZ0002", "9002", "mapped"),
        "SYN-SHIP-3": ("ZZ0003", None, "unmapped"),
        "SYN-SHIP-4": ("ZZ0404", None, "unmapped"),
    }


def test_sensitive_seller_name_only_lives_in_payload(session: Session) -> None:
    run, _, _ = run_sync(session, [page([record(1, store="ZZ0001-合成店铺(某员工)")], 1, 1)])
    assert run.status == "succeeded"
    (row,) = current_rows(session)
    assert row.store_code == "ZZ0001"
    columns = {
        column.name
        for column in WfsCostValuationFlowOds.__table__.columns
        if column.name != "payload_json"
    }
    assert not any("seller" in name for name in columns)
