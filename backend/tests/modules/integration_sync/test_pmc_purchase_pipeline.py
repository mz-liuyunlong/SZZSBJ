"""Isolated governance persistence + synthetic pipeline stages; no real API/DB."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Integer, MetaData, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.integration_sync import pmc_purchase_pipeline as pipeline
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import (
    LingxingPurchasePlanListSyncHandler,
    PmcPurchaseSyncError,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
)
from app.modules.integration_sync.pmc_purchase_pipeline_catalog import (
    PURCHASE_PIPELINE_KEY,
    PURCHASE_SOURCE_KEYS,
)
from app.modules.integration_sync.pmc_purchase_pipeline_repository import PurchasePipelineRepository
from app.modules.integration_sync.scheduler import IntegrationSchedulerService, next_cron_instant
from app.modules.integration_sync.schemas import SyncConfigUpdate, TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService

NOW = datetime(2026, 10, 27, 4, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def compile_jsonb(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "char_length",
            1,
            lambda value: len(value) if value is not None else None,
        ),
    )
    metadata = MetaData()
    for model in (
        IntegrationInterface,
        RawRetentionPolicy,
        IntegrationSyncConfig,
        IntegrationSyncRun,
        IntegrationSyncRunWorkItem,
        IntegrationSyncRunEvent,
    ):
        table = model.__table__.to_metadata(metadata)
        if model is IntegrationSyncRunEvent:
            table.c.id.type = Integer()
        for index in table.indexes:
            where = index.dialect_options["postgresql"].get("where")
            if where is not None:
                index.dialect_options["sqlite"]["where"] = where
    metadata.create_all(engine)
    monkeypatch.setattr(pipeline, "utc_now", lambda: NOW)
    with Session(engine) as session:
        IntegrationCatalogService(session).bootstrap_pmc_purchase_governance("fixture")
        config = PurchasePipelineRepository(session).register("fixture")
        config.is_enabled = True
        config.schedule_enabled = True
        for interface in session.scalars(select(IntegrationInterface)):
            interface.outbound_enabled = True
        session.commit()
        yield session
    engine.dispose()


def new_run(session, *, trigger="manual", start=None, end=None):
    config = PurchasePipelineRepository(session).config_for(PURCHASE_PIPELINE_KEY, "fixture")
    run = IntegrationSyncRun(
        id=uuid4(),
        config_id=config.id,
        interface_id=config.interface_id,
        provider="lingxing",
        interface_key=PURCHASE_PIPELINE_KEY,
        source_account_ref="fixture",
        trigger_type=trigger,
        status="queued",
        idempotency_key=str(uuid4()),
        window_start=start,
        window_end=end,
    )
    session.add(run)
    session.commit()
    return run


def mock_stages(monkeypatch, session, fail=None):
    calls = []

    def collect(self, child, interface):
        calls.append(interface.interface_key)
        child.status = "failed" if fail == interface.interface_key else "succeeded"
        child.records_seen = 2
        child.records_written = 2
        child.finished_at = NOW
        session.commit()

    def publish(**kwargs):
        calls.append("dwd")
        if fail == "dwd":
            raise RuntimeError("synthetic")

    def refresh(**kwargs):
        calls.append("dws")
        if fail == "dws":
            raise RuntimeError("synthetic")

    for handler in pipeline.PMC_PURCHASE_HANDLERS.values():
        monkeypatch.setattr(handler, "execute", collect)
    monkeypatch.setattr(pipeline, "PmcPurchaseDwdPublisher", lambda s: MagicMock(publish=publish))
    monkeypatch.setattr(pipeline, "PmcPurchaseDwsRefresher", lambda s: MagicMock(refresh=refresh))
    return calls


@pytest.mark.parametrize("trigger", ["manual", "schedule", "retry"])
def test_complete_pipeline_and_stage_logs(session, monkeypatch, trigger):
    calls = mock_stages(monkeypatch, session)
    run = new_run(session, trigger=trigger)
    pipeline.PurchasePipeline(session).execute(run.id)
    assert calls == [*PURCHASE_SOURCE_KEYS, "dwd", "dws"]
    assert run.status == "succeeded"
    assert run.work_items_succeeded == 5
    assert run.records_written == 6
    assert PurchasePipelineRepository(session).watermark("fixture").date() == NOW.date()
    works = session.scalars(
        select(IntegrationSyncRunWorkItem)
        .where(
            IntegrationSyncRunWorkItem.run_id == run.id,
        )
        .order_by(IntegrationSyncRunWorkItem.ordinal)
    ).all()
    assert [w.request_safe_params["stage"] for w in works] == [
        *PURCHASE_SOURCE_KEYS,
        "publish_dwd",
        "refresh_dws",
    ]
    assert all("child_run_id" in w.request_safe_params for w in works[:3])
    pipeline.PurchasePipeline(session).execute(run.id)
    assert len(calls) == 5  # Duplicate delivery cannot replay a finished run.


@pytest.mark.parametrize("failure", [*PURCHASE_SOURCE_KEYS, "dwd", "dws"])
def test_failure_does_not_advance_watermark(session, monkeypatch, failure):
    calls = mock_stages(monkeypatch, session, failure)
    run = new_run(session)
    pipeline.PurchasePipeline(session).execute(run.id)
    assert run.status == "failed"
    assert run.work_items_failed == 1
    assert PurchasePipelineRepository(session).watermark("fixture") is None
    assert calls[-1] == failure
    if failure in PURCHASE_SOURCE_KEYS:
        assert "dwd" not in calls and "dws" not in calls


def test_incremental_overlap_and_retry_window(session, monkeypatch):
    mock_stages(monkeypatch, session)
    first = new_run(session)
    pipeline.PurchasePipeline(session).execute(first.id)
    second = new_run(session)
    pipeline.PurchasePipeline(session).execute(second.id)
    assert second.window_start.date() == NOW.date() - timedelta(days=1)
    failed = new_run(session, start=first.window_start, end=first.window_end)
    failed.status = "failed"
    session.commit()
    result = IntegrationSyncService(session).create_retry_run(
        failed.id,
        TriggerRequest(reason="synthetic retry", idempotency_key=str(uuid4())),
        account_refs=frozenset({"fixture"}),
        actor_ref="test",
        request_id="test",
    )
    retry = session.get(IntegrationSyncRun, result.run_id)
    assert retry.window_start == failed.window_start and retry.window_end == failed.window_end


def test_parent_configuration_and_source_guards(session):
    repo = PurchasePipelineRepository(session)
    source = repo.config_for("purchasePlanList", "fixture")
    service = IntegrationSyncService(session)
    with pytest.raises(ApiError) as error:
        service.update_config(
            source.id,
            SyncConfigUpdate(schedule_enabled=True, schedule_cron="* * * * *"),
            frozenset({"fixture"}),
            actor_ref="test",
            request_id="test",
        )
    assert error.value.code == "SYNC_PURCHASE_USE_UNIFIED_TASK"
    parent = new_run(session)
    child = IntegrationSyncRun(
        id=uuid4(),
        config_id=source.id,
        interface_id=source.interface_id,
        provider="lingxing",
        interface_key="purchasePlanList",
        source_account_ref="fixture",
        trigger_type="manual",
        status="queued",
        idempotency_key=str(uuid4()),
        window_start=NOW,
        window_end=NOW,
    )
    interface = session.get(IntegrationInterface, source.interface_id)
    handler = LingxingPurchasePlanListSyncHandler(session, client=MagicMock())
    with pytest.raises(PmcPurchaseSyncError, match="USE_UNIFIED_TASK"):
        handler._preflight(child, interface)
    child.parent_run_id = parent.id
    parent.status = "running"
    session.commit()
    handler = LingxingPurchasePlanListSyncHandler(
        session,
        client=MagicMock(),
        pipeline_parent_id=parent.id,
    )
    config, _, _ = handler._preflight(child, interface)
    assert config.id == parent.config_id
    parent.source_account_ref = "another"
    with pytest.raises(PmcPurchaseSyncError, match="USE_UNIFIED_TASK"):
        handler._preflight(child, interface)


def test_registration_idempotent_and_scoped(session):
    repo = PurchasePipelineRepository(session)
    before = repo.config_for(PURCHASE_PIPELINE_KEY, "fixture")
    same = repo.register("fixture")
    assert same.id == before.id and same.schedule_enabled
    IntegrationCatalogService(session).bootstrap_pmc_purchase_governance("another")
    second = repo.register("another")
    session.commit()
    assert not second.is_enabled and not second.schedule_enabled
    assert second.schedule_cron == "0 */3 * * *"
    assert repo.watermark("another") is None


def test_scheduler_dispatches_parent_and_ignores_child(session):
    repo = PurchasePipelineRepository(session)
    parent = repo.config_for(PURCHASE_PIPELINE_KEY, "fixture")
    child = repo.config_for("purchasePlanList", "fixture")
    for config in (parent, child):
        config.is_enabled = True
        config.schedule_enabled = True
        config.schedule_cron = "0 */3 * * *"
        config.next_run_at = NOW - timedelta(hours=1)
    session.commit()
    runs = IntegrationSchedulerService(session).create_due_runs(now=NOW)
    assert len(runs) == 1
    assert session.get(IntegrationSyncRun, runs[0]).interface_key == PURCHASE_PIPELINE_KEY
    assert not child.schedule_enabled and child.next_run_at is None
    assert parent.next_run_at.replace(tzinfo=UTC) == next_cron_instant("0 */3 * * *", NOW)


def test_window_bounds():
    spans = pipeline.purchase_windows(date(2026, 8, 1), date(2027, 3, 1))
    assert spans[0][0] == date(2026, 8, 1) and spans[-1][1] == date(2027, 3, 1)
    assert all((end - start).days < 90 for start, end in spans)
    assert all(
        left[1] + timedelta(days=1) == right[0]
        for left, right in zip(spans, spans[1:], strict=False)
    )
    with pytest.raises(ValueError):
        pipeline.purchase_windows(date(2026, 7, 1), NOW.date())


def test_preflight_rejects_disabled_source_before_any_collection(session, monkeypatch):
    calls = mock_stages(monkeypatch, session)
    source = PurchasePipelineRepository(session).config_for("purchaseReceiptOrderList", "fixture")
    session.get(IntegrationInterface, source.interface_id).outbound_enabled = False
    session.commit()
    run = new_run(session)
    pipeline.PurchasePipeline(session).execute(run.id)
    assert calls == []
    assert run.status == "failed" and run.error_code == "SYNC_PURCHASE_SOURCE_DISABLED"


def test_interrupted_parent_and_children_recovered_without_touching_other_runs(session):
    parent = new_run(session)
    parent.status = "running"
    source = PurchasePipelineRepository(session).config_for("purchasePlanList", "fixture")
    child = IntegrationSyncRun(
        id=uuid4(),
        config_id=source.id,
        interface_id=source.interface_id,
        provider="lingxing",
        interface_key="purchasePlanList",
        source_account_ref="fixture",
        trigger_type="manual",
        status="running",
        idempotency_key=str(uuid4()),
        parent_run_id=parent.id,
        reason="purchase_board_pipeline",
    )
    session.add(child)
    session.commit()
    other = new_run(session)
    repo = PurchasePipelineRepository(session)
    repo.recover_interrupted()
    session.commit()
    assert parent.status == child.status == "failed"
    assert parent.error_code == child.error_code == "SYNC_PURCHASE_INTERRUPTED"
    assert other.status == "queued"
    assert repo.watermark("fixture") is None


def test_parent_scope_is_enforced_for_manual_and_retry(session):
    parent = new_run(session)
    service = IntegrationSyncService(session)
    with pytest.raises(ApiError) as error:
        service.create_manual_run(
            parent.config_id,
            TriggerRequest(reason="scope test", idempotency_key=str(uuid4())),
            actor_ref="test",
            request_id="test",
            account_refs=frozenset({"other"}),
        )
    assert error.value.status_code == 404
    parent.status = "failed"
    session.commit()
    with pytest.raises(ApiError) as error:
        service.create_retry_run(
            parent.id,
            TriggerRequest(reason="scope test", idempotency_key=str(uuid4())),
            actor_ref="test",
            request_id="test",
            account_refs=frozenset({"other"}),
        )
    assert error.value.status_code == 404


def test_recovery_does_not_dispatch_internal_children(session):
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    parent = new_run(session)
    source = PurchasePipelineRepository(session).config_for("purchasePlanList", "fixture")
    child = IntegrationSyncRun(
        id=uuid4(),
        config_id=source.id,
        interface_id=source.interface_id,
        provider="lingxing",
        interface_key="purchasePlanList",
        source_account_ref="fixture",
        trigger_type="manual",
        status="queued",
        idempotency_key=str(uuid4()),
        parent_run_id=parent.id,
        reason="purchase_board_pipeline",
    )
    session.add(child)
    session.commit()
    ids = IntegrationSyncRepository(session).list_recoverable_queued_run_ids(
        datetime(2030, 1, 1, tzinfo=UTC),
        limit=100,
    )
    assert parent.id in ids and child.id not in ids


@pytest.mark.parametrize("acquired", [True, False])
def test_purchase_lock_release_and_contention(acquired):
    from app.modules.integration_sync.pmc_purchase_pipeline_repository import purchase_connection

    engine = MagicMock()
    engine.dialect.name = "postgresql"
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = acquired
    if acquired:
        with pytest.raises(RuntimeError, match="synthetic stage error"):
            with purchase_connection(engine) as locked:
                assert locked is connection
                raise RuntimeError("synthetic stage error")
        assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])
    else:
        with purchase_connection(engine) as locked:
            assert locked is None
        connection.execute.assert_not_called()


def test_contended_parent_requeues_without_running_sources(session, monkeypatch):
    from contextlib import nullcontext

    calls = mock_stages(monkeypatch, session)
    parent = new_run(session)
    parent.queued_at = NOW - timedelta(days=1)
    session.commit()
    monkeypatch.setattr(pipeline, "purchase_connection", lambda engine: nullcontext(None))
    pipeline.execute_purchase_pipeline(session.get_bind(), parent.id)
    session.refresh(parent)
    assert parent.status == "queued" and parent.queued_at.replace(tzinfo=UTC) == NOW
    assert not calls


def test_scheduler_recovers_crashed_manual_parent_without_new_run(session, monkeypatch):
    from contextlib import nullcontext

    run = new_run(session)
    run.status = "running"
    config = session.get(IntegrationSyncConfig, run.config_id)
    config.schedule_enabled = False
    session.commit()
    with session.get_bind().connect() as connection:
        monkeypatch.setattr(pipeline, "purchase_connection", lambda engine: nullcontext(connection))
        recovered = pipeline.recover_purchase_pipeline(session.get_bind())
    session.refresh(run)
    assert recovered == [run.id]
    assert run.status == "failed"
    assert run.error_code == "SYNC_PURCHASE_INTERRUPTED"


def test_purchase_recovery_failure_does_not_block_other_scheduler_recovery(monkeypatch):
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    scheduler = IntegrationSchedulerService(session)
    scheduler.repository = MagicMock()
    scheduler.repository.list_expired_locks_for_update.return_value = []
    scheduler.repository.list_stale_unleased_productlist_runs_for_update.return_value = []
    monkeypatch.setattr(
        pipeline, "recover_purchase_pipeline", MagicMock(side_effect=RuntimeError())
    )
    assert scheduler.recover_expired_runs(now=NOW) == []
    scheduler.repository.list_expired_locks_for_update.assert_called_once()
    scheduler.repository.list_stale_unleased_productlist_runs_for_update.assert_called_once()
