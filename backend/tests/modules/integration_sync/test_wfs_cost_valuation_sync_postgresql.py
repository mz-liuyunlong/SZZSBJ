"""WFS cost valuation flow sync on a disposable PostgreSQL database (synthetic data only).

Opt-in: DOMESTIC_CHAIN_DB_TESTS=1 with the dedicated local ``domestic_chain_ci`` cluster.
No provider is called: every page comes from an in-memory fake client.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
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
    IntegrationSyncLock,
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

    # A running run for the same account with a live lease also blocks a second (queued) run.
    running = new_run(session, config, interface)
    add_lease(session, running, expires_in=timedelta(minutes=5))
    queued = new_run(session, config, interface, status="queued")
    client = FakeClient([page([record(1)], 1, 1)])
    result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(queued, interface)
    assert result.error_code == "SYNC_WFS_FLOW_CONCURRENT_RUN"
    assert client.calls == []
    session.refresh(running)
    assert running.status == "running"


def add_lease(session: Session, run: IntegrationSyncRun, *, expires_in: timedelta) -> None:
    """expires_in 为负 = 过期租约：拿锁和最后心跳都在到期之前（锁表约束要求到期不早于心跳）。"""
    now = datetime.now(UTC)
    expires_at = now + expires_in
    taken_at = min(now, expires_at - timedelta(minutes=5))
    session.add(
        IntegrationSyncLock(
            provider=run.provider,
            interface_key=run.interface_key,
            run_id=run.id,
            lock_token_hash="0" * 64,
            acquired_at=taken_at,
            heartbeat_at=taken_at,
            expires_at=expires_at,
        )
    )
    session.commit()


def test_expired_lease_does_not_block_and_lock_is_released_after_each_run(
    session: Session, engine: sa.Engine
) -> None:
    """刘云龙 2026-11-26：任务结束必须放锁；崩掉留下的「running」不能挡住下一次。

    直接调 handler 的层面：只有活租约才算在跑；成功、失败后咨询锁都已释放。
    """
    interface, config = bootstrap(session)
    # a crashed run: status still "running" but its lease expired long ago -> not active.
    # (the runs table allows one "running" per interface, so the new run here stays "queued"
    # in the handler path; the execution-layer path is covered by the next test)
    crashed = new_run(session, config, interface)
    add_lease(session, crashed, expires_in=timedelta(minutes=-30))
    queued = new_run(session, config, interface, status="queued")
    handler = LingxingWfsCostValuationSyncHandler(session, client=FakeClient([]))
    assert handler._other_run_active(queued) is False
    # the advisory lock is released after a successful and after a failed run
    crashed.status = "failed"
    session.commit()
    ok_run = new_run(session, config, interface, status="queued")
    client = FakeClient([page([record(1)], 1, 1)])
    result = LingxingWfsCostValuationSyncHandler(session, client=client).execute(ok_run, interface)
    assert result.status == "succeeded", result.error_code
    with engine.connect() as probe:
        assert probe.scalar(
            sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": advisory_lock_key(ACCOUNT)}
        )
        probe.execute(sa.text("SELECT pg_advisory_unlock_all()"))
    failing = new_run(session, config, interface, status="queued")
    bad = FakeClient([page([{**record(1), "quantity": "1.5"}], 1, 1)])
    failed = LingxingWfsCostValuationSyncHandler(session, client=bad).execute(failing, interface)
    assert failed.status == "failed"
    with engine.connect() as probe:
        assert probe.scalar(
            sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": advisory_lock_key(ACCOUNT)}
        )
        probe.execute(sa.text("SELECT pg_advisory_unlock_all()"))


def test_execution_layer_path_releases_lease_and_lock_and_clears_expired_lease(
    session: Session, engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产真实链路：SyncRunExecutionService.execute → 租约 → handler → finally 删租约。"""
    from contextlib import contextmanager

    from app.modules.integration_sync.handlers import lingxing_wfs_cost_valuation_sync as module

    interface, config = bootstrap(session)
    pages: list[list[LingxingRawEnvelope]] = []

    @contextmanager
    def fake_client():  # type: ignore[no-untyped-def]
        yield FakeClient(pages.pop(0))

    monkeypatch.setattr(module, "_require_runtime", lambda settings: None)
    monkeypatch.setattr(module, "wfs_cost_valuation_client", fake_client)
    from app.modules.integration_sync import execution as execution_module

    recalcs: list[tuple[set[tuple[str | None, str]], str]] = []

    def fake_periods(_session: Session, *, source_account_ref: str, keys: object) -> object:
        recalcs.append((set(keys.mskus), "periods"))  # type: ignore[attr-defined]
        return [("store-x", "2026-10-07")]

    def fake_enqueue(_session: Session, pairs: object, *, reason: str) -> tuple[int, bool]:
        recalcs[-1] = (recalcs[-1][0], reason)
        return 1, True

    def no_full_recalc(*args: object, **kwargs: object) -> bool:
        raise AssertionError("cost flow sync must never dispatch a store-wide recalc")

    monkeypatch.setattr(execution_module, "affected_periods", fake_periods)
    monkeypatch.setattr(execution_module, "enqueue_affected", fake_enqueue)
    monkeypatch.setattr(execution_module, "dispatch_order_review_recalc", no_full_recalc)

    def lock_free() -> bool:
        with engine.connect() as probe:
            free = bool(
                probe.scalar(
                    sa.text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": advisory_lock_key(ACCOUNT)},
                )
            )
            probe.execute(sa.text("SELECT pg_advisory_unlock_all()"))
        return free

    def lease_rows() -> int:
        return session.scalar(sa.select(sa.func.count()).select_from(IntegrationSyncLock)) or 0

    # ① a normal run: lease gone and advisory lock free afterwards
    first = new_run(session, config, interface, status="queued")
    pages.append([page([record(1)], 1, 1)])
    SyncRunExecutionService(session).execute(first.id)
    session.expire_all()
    first_row = session.get(IntegrationSyncRun, first.id)
    assert first_row is not None
    assert first_row.status == "succeeded", first_row.error_code
    assert lease_rows() == 0 and lock_free()
    # 成功 → 只按变了的行投递（店铺没认出 = 任何店铺；MSKU 归一成小写）
    assert recalcs == [({(None, "syn-msku-1")}, "wfs_cost_flow_sync")]

    # ② a crashed run holding an expired lease: the execution layer fails it and runs the new one
    crashed = new_run(session, config, interface)
    add_lease(session, crashed, expires_in=timedelta(minutes=-30))
    second = new_run(session, config, interface, status="queued")
    pages.append([page([record(2)], 1, 1)])
    SyncRunExecutionService(session).execute(second.id)
    session.expire_all()
    crashed_row = session.get(IntegrationSyncRun, crashed.id)
    assert crashed_row is not None
    assert (crashed_row.status, crashed_row.error_code) == ("failed", "SYNC_LOCK_LEASE_EXPIRED")
    second_row = session.get(IntegrationSyncRun, second.id)
    assert second_row is not None
    assert second_row.status == "succeeded", second_row.error_code
    assert lease_rows() == 0 and lock_free()

    # ③ a failing run also leaves no lease and no lock behind
    third = new_run(session, config, interface, status="queued")
    pages.append([page([{**record(3), "quantity": "1.5"}], 1, 1)])
    SyncRunExecutionService(session).execute(third.id)
    session.expire_all()
    third_row = session.get(IntegrationSyncRun, third.id)
    assert third_row is not None and third_row.status == "failed"
    assert lease_rows() == 0 and lock_free()
    # ② 用 record(2) 整段替换 record(1)：新旧两边的 MSKU 都算受影响
    assert recalcs[1] == ({(None, "syn-msku-1"), (None, "syn-msku-2")}, "wfs_cost_flow_sync")
    # 失败批次不整段替换，不投递重算（①②各一次）
    assert len(recalcs) == 2


def test_affected_keys_only_cover_rows_that_really_changed(session: Session) -> None:
    window = (date(2026, 10, 1), date(2026, 10, 31))
    # 测试配置一页最多 2 行：两行正好一页
    rows = [record(1), record(2)]
    first, _, result = run_sync(session, [page(rows, 2, 1)], window=window)
    assert first.status == "succeeded", first.error_code
    affected = result.affected  # type: ignore[attr-defined]
    assert affected.mskus == {(None, "syn-msku-1"), (None, "syn-msku-2")}
    assert affected.orders == {(None, "SYN-ORDER-1"), (None, "SYN-ORDER-2")}
    # 同样的数据再拉一次：整段替换了，但内容一行没变 → 没有受影响的键
    again, _, same = run_sync(session, [page(rows, 2, 1)], window=window)
    assert again.status == "succeeded", again.error_code
    assert same.affected.is_empty()  # type: ignore[attr-defined]
    # 只改 record(2) 的数量：只记它的 MSKU 和订单号
    changed = [record(1), record(2, quantity=-2)]
    third, _, diff = run_sync(session, [page(changed, 2, 1)], window=window)
    assert third.status == "succeeded", third.error_code
    assert diff.affected.mskus == {(None, "syn-msku-2")}  # type: ignore[attr-defined]
    assert diff.affected.orders == {(None, "SYN-ORDER-2")}  # type: ignore[attr-defined]


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
