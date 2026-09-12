from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.parsers.lingxing_product_info import (
    parse_product_info_fixture,
)
from app.modules.integration_sync.scheduler import IntegrationSchedulerService
from app.modules.integration_sync.schemas import SyncConfigRead, SyncConfigUpdate
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.sku_detail.publisher import SkuDetailPublicationService

ID = UUID("00000000-0000-0000-0000-000000000001")


def test_service_rolls_back_transaction_on_config_integrity_failure() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    service.repository = MagicMock()
    config = SimpleNamespace(schedule_enabled=False, schedule_cron=None)
    service.repository.get_config.return_value = config
    service.repository.update_config.side_effect = IntegrityError("safe", {}, Exception())

    with pytest.raises(ApiError) as error:
        service.update_config(
            ID,
            SyncConfigUpdate(is_enabled=True),
            frozenset({"default"}),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
        )

    assert error.value.status_code == 422
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


def test_config_update_audit_records_field_names_not_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    service.repository = MagicMock()
    config = SimpleNamespace(schedule_enabled=False, schedule_cron=None)
    service.repository.get_config.return_value = config
    expected = MagicMock(spec=SyncConfigRead)
    monkeypatch.setattr(
        SyncConfigRead,
        "model_validate",
        classmethod(lambda cls, value: expected),
    )
    audit = MagicMock()
    monkeypatch.setattr(
        "app.modules.integration_sync.service.audit_logger.info",
        audit,
    )

    result = service.update_config(
        ID,
        SyncConfigUpdate(page_size=17),
        frozenset({"default"}),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
    )

    assert result is expected
    assert "page_size" in repr(audit.call_args)
    assert "17" not in repr(audit.call_args)
    session.commit.assert_called_once_with()


def test_scheduler_deterministic_idempotency_skips_duplicate_tick() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSchedulerService(session)
    service.repository = MagicMock()
    config = SimpleNamespace(
        id=ID,
        interface_id=ID,
        source_account_ref="default",
        next_run_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    interface = SimpleNamespace(
        id=ID,
        provider="lingxing",
        interface_key="productList",
        outbound_enabled=True,
    )
    service.repository.list_due_configs.return_value = [config]
    service.repository.get_interface.return_value = interface
    service.repository.find_run_by_idempotency.return_value = SimpleNamespace(id=ID)

    assert service.create_due_runs() == []
    service.repository.add_run.assert_not_called()
    session.commit.assert_called_once_with()


def test_sku_detail_publication_commits_snapshot_current_profile_and_lineage() -> None:
    session = MagicMock(spec=Session)
    service = SkuDetailPublicationService(session)
    service.sync_repository = MagicMock()
    service.repository = MagicMock()
    service.sync_repository.get_lingxing_identity.return_value = SimpleNamespace(id=ID)
    service.sync_repository.get_raw_request_ref.return_value = SimpleNamespace(
        run_id=ID,
        raw_blob_id=ID,
    )
    service.sync_repository.add_parse_job.return_value = SimpleNamespace(id=ID)
    service.repository.get_current.return_value = None
    service.repository.get_profile.return_value = None

    snapshot_id = service.publish(
        run_id=ID,
        raw_request_ref_id=ID,
        source_account_ref="default",
        lingxing_sku_id="synthetic-id",
        source_observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="fixture-v1",
        parsed=parse_product_info_fixture({"data": {}}),
    )

    assert isinstance(snapshot_id, UUID)
    service.repository.add_snapshot.assert_called_once()
    service.repository.add_current.assert_called_once()
    service.repository.add_profile.assert_called_once()
    service.sync_repository.add_parse_job.assert_called_once()
    service.sync_repository.add_lineage.assert_called_once()
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_execution_leaves_queued_run_untouched_when_live_lock_exists() -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    service.repository = MagicMock()
    run = SimpleNamespace(
        id=ID,
        status="queued",
        interface_id=ID,
        provider="lingxing",
        interface_key="batchGetProductInfo",
    )
    service.repository.get_run_for_update.return_value = run
    service.repository.get_interface.return_value = SimpleNamespace(handler_key="disabled")
    service.repository.get_lock_for_interface.return_value = SimpleNamespace(
        run_id=ID,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    service.execute(ID)

    assert run.status == "queued"
    service.repository.add_lock.assert_not_called()
    session.rollback.assert_called_once_with()


def test_execution_recovers_expired_lease_before_claiming_run() -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    service.repository = MagicMock()
    run = SimpleNamespace(
        id=ID,
        status="queued",
        interface_id=ID,
        provider="lingxing",
        interface_key="batchGetProductInfo",
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
    )
    stale_run = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        status="running",
        finished_at=None,
        error_code=None,
        error_message=None,
    )
    expired_lock = SimpleNamespace(
        run_id=stale_run.id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    service.repository.get_run_for_update.side_effect = [run, stale_run]
    service.repository.get_interface.return_value = SimpleNamespace(handler_key="disabled")
    service.repository.get_lock_for_interface.return_value = expired_lock
    service.repository.get_lock_for_run.return_value = None
    service.repository.next_event_sequence.return_value = 1

    service.execute(ID)

    assert stale_run.status == "failed"
    assert stale_run.error_code == "SYNC_LOCK_LEASE_EXPIRED"
    service.repository.delete_lock.assert_called_once_with(expired_lock)
    service.repository.add_lock.assert_called_once()
    assert run.status == "failed"
    assert run.error_code == "SYNC_HANDLER_NOT_EXECUTABLE"
