from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

import app.modules.integration_sync.execution as execution_module
import app.modules.integration_sync.tasks as task_module
from app.core.api import ApiError
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.schemas import BackfillRequest, TriggerRequest, TriggerType
from app.modules.integration_sync.service import (
    SYNC_PRODUCTINFO_BACKFILL_NOT_SUPPORTED,
    IntegrationSyncService,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _productinfo_interface(*, outbound_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=101),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        display_name="Synthetic ProductInfo",
        method="POST",
        endpoint_path="/erp/sc/routing/data/local_inventory/batchGetProductInfo",
        request_kind="id_batch_page",
        handler_key="lingxing.batch_get_product_info.v1",
        contract_version="synthetic-v1",
        outbound_enabled=outbound_enabled,
    )


def _config(*, is_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=100),
        interface_id=UUID(int=101),
        source_account_ref="synthetic-account",
        is_enabled=is_enabled,
        schedule_enabled=True,
        schedule_cron="0 * * * *",
        schedule_timezone="UTC",
        batch_size=20,
        page_size=None,
        max_pages=None,
        max_attempts=2,
        retention_policy_id=None,
        next_run_at=NOW,
        last_scheduled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_manual_productinfo_run_is_formally_reachable() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository

    config = _config()
    interface = _productinfo_interface()
    repository.get_config.return_value = config
    repository.get_interface.return_value = interface
    repository.find_run_by_idempotency.return_value = None

    def add_run(run: object) -> object:
        run.id = UUID(int=200)  # type: ignore[attr-defined]
        return run

    repository.add_run.side_effect = add_run
    repository.add_event.side_effect = lambda event: event

    created = service.create_manual_run(
        config.id,
        TriggerRequest(
            reason="synthetic manual ProductInfo",
            idempotency_key="synthetic-productinfo-manual",
        ),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
        account_refs=frozenset({"synthetic-account"}),
    )

    assert created.run_id == UUID(int=200)
    assert created.trigger_type is TriggerType.MANUAL
    run = repository.add_run.call_args.args[0]
    assert run.provider == "lingxing"
    assert run.interface_key == "batchGetProductInfo"
    assert run.status == "queued"
    assert run.work_items_total == 0
    session.commit.assert_called_once()


def test_productinfo_backfill_is_rejected_until_window_semantics_exist() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository

    config = _config()
    repository.get_config.return_value = config
    repository.get_interface.return_value = _productinfo_interface()

    with pytest.raises(ApiError) as error:
        service.create_backfill_run(
            config.id,
            BackfillRequest(
                reason="synthetic backfill",
                window_start=datetime(2025, 12, 1, tzinfo=UTC),
                window_end=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"synthetic-account"}),
        )

    assert error.value.code == SYNC_PRODUCTINFO_BACKFILL_NOT_SUPPORTED
    repository.add_run.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    ("outbound_enabled", "config_enabled", "expected_code"),
    [
        (False, True, "SYNC_INTERFACE_DISABLED"),
        (True, False, "SYNC_CONFIG_DISABLED"),
    ],
)
def test_formal_execution_rechecks_governance_before_productinfo_outbound(
    monkeypatch: pytest.MonkeyPatch,
    outbound_enabled: bool,
    config_enabled: bool,
    expected_code: str,
) -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository

    run = SimpleNamespace(
        id=UUID(int=300),
        config_id=UUID(int=100),
        interface_id=UUID(int=101),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        trigger_type="schedule",
        status="queued",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    repository.get_run_for_update.return_value = run
    repository.get_interface.return_value = _productinfo_interface(
        outbound_enabled=outbound_enabled
    )
    repository.get_config.return_value = _config(is_enabled=config_enabled)
    repository.next_event_sequence.return_value = 1
    repository.add_event.side_effect = lambda event: event

    client_factory = MagicMock()
    monkeypatch.setattr(execution_module, "product_info_client", client_factory)

    service.execute(run.id)

    assert run.status == "failed"
    assert run.error_code == expected_code
    client_factory.assert_not_called()
    repository.add_lock.assert_not_called()
    session.commit.assert_called_once()


def test_scheduler_tick_dispatches_every_due_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    session_context = MagicMock(spec=AbstractContextManager)
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    session_factory = MagicMock(return_value=session_context)
    monkeypatch.setattr(task_module, "get_session_factory", lambda: session_factory)

    run_ids = [UUID(int=401), UUID(int=402)]
    create_due_runs = MagicMock(return_value=run_ids)
    recoverable_queued_run_ids = MagicMock(return_value=[])
    monkeypatch.setattr(
        task_module.IntegrationSchedulerService,
        "create_due_runs",
        create_due_runs,
    )
    monkeypatch.setattr(
        task_module.IntegrationSchedulerService,
        "recoverable_queued_run_ids",
        recoverable_queued_run_ids,
    )

    dispatched: list[UUID] = []
    monkeypatch.setattr(task_module, "dispatch_sync_run", dispatched.append)

    task_module.scheduler_tick.run()

    assert dispatched == run_ids
    create_due_runs.assert_called_once_with()
    recoverable_queued_run_ids.assert_called_once_with()


def test_execute_task_delegates_only_run_id_to_execution_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    session_context = MagicMock(spec=AbstractContextManager)
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    session_factory = MagicMock(return_value=session_context)
    monkeypatch.setattr(task_module, "get_session_factory", lambda: session_factory)

    execute = MagicMock()
    monkeypatch.setattr(
        task_module.SyncRunExecutionService,
        "execute",
        execute,
    )

    run_id = UUID(int=500)
    task_module.execute_sync_run.run(str(run_id))

    execute.assert_called_once_with(run_id)


def test_execution_leaves_lock_blocked_run_queued_for_scheduler_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository

    run = SimpleNamespace(
        id=UUID(int=600),
        config_id=UUID(int=100),
        interface_id=UUID(int=101),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        trigger_type="schedule",
        status="queued",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    repository.get_run_for_update.return_value = run
    repository.get_interface.return_value = _productinfo_interface()
    repository.get_config.return_value = _config()
    repository.get_lock_for_interface.return_value = SimpleNamespace(
        expires_at=NOW + timedelta(minutes=2)
    )
    monkeypatch.setattr(execution_module, "utc_now", lambda: NOW)

    service.execute(run.id)

    assert run.status == "queued"
    repository.add_lock.assert_not_called()
    session.rollback.assert_called_once()


def test_execution_heartbeat_renews_owned_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository
    lock = SimpleNamespace(
        heartbeat_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=1),
    )
    repository.get_lock_for_run_for_update.return_value = lock
    monkeypatch.setattr(execution_module, "utc_now", lambda: NOW)

    service._heartbeat_lock(UUID(int=700))

    assert lock.heartbeat_at == NOW
    assert lock.expires_at == NOW + execution_module.LOCK_LEASE_DURATION
    session.commit.assert_called_once()


def test_scheduler_tick_recovers_queued_runs_and_continues_after_dispatch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    session_context = MagicMock(spec=AbstractContextManager)
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False
    session_factory = MagicMock(return_value=session_context)
    monkeypatch.setattr(task_module, "get_session_factory", lambda: session_factory)

    new_run = UUID(int=801)
    recovered_run = UUID(int=802)
    monkeypatch.setattr(
        task_module.IntegrationSchedulerService,
        "create_due_runs",
        MagicMock(return_value=[new_run]),
    )
    monkeypatch.setattr(
        task_module.IntegrationSchedulerService,
        "recoverable_queued_run_ids",
        MagicMock(return_value=[new_run, recovered_run]),
    )

    attempted: list[UUID] = []

    def dispatch(run_id: UUID) -> None:
        attempted.append(run_id)
        if run_id == new_run:
            raise task_module.TaskDispatchError("synthetic unavailable")

    monkeypatch.setattr(task_module, "dispatch_sync_run", dispatch)

    task_module.scheduler_tick.run()

    assert attempted == [new_run, recovered_run]
