from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

import app.modules.integration_sync.service as service_module
from app.core.api import ApiError
from app.modules.integration_sync.scheduler import (
    IntegrationSchedulerService,
    ScheduleExpressionError,
    next_cron_instant,
)
from app.modules.integration_sync.schemas import SyncConfigUpdate
from app.modules.integration_sync.service import IntegrationSyncService

NOW = datetime(2026, 1, 1, 12, 7, tzinfo=UTC)


def _config(
    *,
    schedule_enabled: bool = True,
    schedule_cron: str | None = "0 * * * *",
    next_run_at: datetime | None = datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=100),
        interface_id=UUID(int=101),
        source_account_ref="synthetic-account",
        is_enabled=True,
        schedule_enabled=schedule_enabled,
        schedule_cron=schedule_cron,
        schedule_timezone="UTC",
        page_size=None,
        batch_size=20,
        max_pages=None,
        max_attempts=2,
        retention_policy_id=None,
        next_run_at=next_run_at,
        last_scheduled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _interface(interface_key: str = "batchGetProductInfo") -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=101),
        provider="lingxing",
        interface_key=interface_key,
        outbound_enabled=True,
    )


def test_next_cron_instant_uses_celery_cron_fields_in_utc() -> None:
    assert next_cron_instant("*/15 * * * *", NOW) == datetime(
        2026,
        1,
        1,
        12,
        15,
        tzinfo=UTC,
    )
    assert next_cron_instant("0 0 * * 0", NOW) == datetime(
        2026,
        1,
        4,
        0,
        0,
        tzinfo=UTC,
    )


def test_next_cron_instant_rejects_invalid_or_impossible_schedule() -> None:
    with pytest.raises(ScheduleExpressionError):
        next_cron_instant("not a cron", NOW)
    with pytest.raises(ScheduleExpressionError):
        next_cron_instant("0 0 31 2 *", NOW)


def test_update_config_enabling_schedule_sets_initial_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository
    config = _config(schedule_enabled=False, schedule_cron=None, next_run_at=None)
    repository.get_config.return_value = config
    repository.get_interface.return_value = _interface()

    def apply_values(record: object, values: dict[str, object]) -> object:
        for name, value in values.items():
            setattr(record, name, value)
        return record

    repository.update_config.side_effect = apply_values
    monkeypatch.setattr(service_module, "utc_now", lambda: NOW)

    result = service.update_config(
        config.id,
        SyncConfigUpdate(
            schedule_enabled=True,
            schedule_cron="*/15 * * * *",
        ),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
    )

    persisted_values = repository.update_config.call_args.args[1]
    assert persisted_values["next_run_at"] == datetime(
        2026,
        1,
        1,
        12,
        15,
        tzinfo=UTC,
    )
    assert result.next_run_at == datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    session.commit.assert_called_once()


def test_update_config_disabling_schedule_clears_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository
    config = _config()
    repository.get_config.return_value = config

    def apply_values(record: object, values: dict[str, object]) -> object:
        for name, value in values.items():
            setattr(record, name, value)
        return record

    repository.update_config.side_effect = apply_values
    monkeypatch.setattr(service_module, "utc_now", lambda: NOW)

    service.update_config(
        config.id,
        SyncConfigUpdate(schedule_enabled=False),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
    )

    assert repository.update_config.call_args.args[1]["next_run_at"] is None


def test_update_config_rejects_invalid_cron_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository
    config = _config(schedule_enabled=False, schedule_cron=None, next_run_at=None)
    repository.get_config.return_value = config
    repository.get_interface.return_value = _interface()
    monkeypatch.setattr(service_module, "utc_now", lambda: NOW)

    with pytest.raises(ApiError):
        service.update_config(
            config.id,
            SyncConfigUpdate(
                schedule_enabled=True,
                schedule_cron="bad cron",
            ),
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
        )

    repository.update_config.assert_not_called()
    session.commit.assert_not_called()


def test_scheduler_creates_productinfo_run_and_advances_next_run() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    repository = MagicMock()
    scheduler.repository = repository

    config = _config()
    interface = _interface()
    repository.list_due_configs.return_value = [config]
    repository.get_interface.return_value = interface
    repository.find_run_by_idempotency.return_value = None

    def add_run(run: object) -> object:
        run.id = UUID(int=200)  # type: ignore[attr-defined]
        return run

    repository.add_run.side_effect = add_run
    repository.add_event.side_effect = lambda event: event

    run_ids = scheduler.create_due_runs(now=datetime(2026, 1, 1, 12, 34, tzinfo=UTC))

    assert run_ids == [UUID(int=200)]
    run = repository.add_run.call_args.args[0]
    assert run.trigger_type == "schedule"
    assert run.interface_key == "batchGetProductInfo"
    assert run.idempotency_key == (
        "schedule:00000000-0000-0000-0000-000000000064:2026-01-01T12:00:00+00:00"
    )
    assert config.last_scheduled_at == datetime(2026, 1, 1, 12, 34, tzinfo=UTC)
    assert config.next_run_at == datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
    session.commit.assert_called_once()


def test_scheduler_duplicate_slot_is_idempotent_and_still_advances() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    repository = MagicMock()
    scheduler.repository = repository

    config = _config()
    repository.list_due_configs.return_value = [config]
    repository.get_interface.return_value = _interface()
    repository.find_run_by_idempotency.return_value = SimpleNamespace(id=UUID(int=300))

    run_ids = scheduler.create_due_runs(now=datetime(2026, 1, 1, 12, 34, tzinfo=UTC))

    assert run_ids == []
    repository.add_run.assert_not_called()
    repository.add_event.assert_not_called()
    assert config.next_run_at == datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
    session.commit.assert_called_once()


def test_scheduler_never_schedules_productlist() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    repository = MagicMock()
    scheduler.repository = repository

    config = _config()
    repository.list_due_configs.return_value = [config]
    repository.get_interface.return_value = _interface("productList")

    run_ids = scheduler.create_due_runs(now=datetime(2026, 1, 1, 12, 34, tzinfo=UTC))

    assert run_ids == []
    repository.add_run.assert_not_called()
    assert config.next_run_at is None


def test_scheduler_recovery_applies_grace_window_to_queued_runs() -> None:
    session = MagicMock(spec=Session)
    scheduler = IntegrationSchedulerService(session)
    repository = MagicMock()
    scheduler.repository = repository
    recovered = [UUID(int=901), UUID(int=902)]
    repository.list_recoverable_queued_run_ids.return_value = recovered

    result = scheduler.recoverable_queued_run_ids(limit=25, now=NOW)

    assert result == recovered
    repository.list_recoverable_queued_run_ids.assert_called_once_with(
        NOW - timedelta(minutes=1),
        limit=25,
    )
