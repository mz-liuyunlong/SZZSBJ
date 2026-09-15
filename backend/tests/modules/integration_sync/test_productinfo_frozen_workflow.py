from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.integration_sync.execution import SyncRunExecutionService


def _run() -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=11),
        config_id=UUID(int=12),
        source_account_ref="synthetic-account",
        status="running",
        work_items_total=0,
        error_code=None,
        error_message=None,
        finished_at=None,
    )


def test_productinfo_plan_freezes_active_identity_set_once() -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository
    run = _run()

    repository.list_work_items_for_run.return_value = []
    repository.list_batch_items_for_run.return_value = []
    repository.list_active_lingxing_sku_ids.return_value = [
        "synthetic-id-b",
        "synthetic-id-a",
    ]
    repository.batch_size_for_run.return_value = 20

    plan = service.load_or_freeze_product_info_plan(run)

    assert plan is not None
    assert [item.lingxing_sku_id for item in plan.batch_items] == [
        "synthetic-id-a",
        "synthetic-id-b",
    ]
    assert run.work_items_total == 1
    repository.list_active_lingxing_sku_ids.assert_called_once_with("synthetic-account")
    repository.add_work_items.assert_called_once()
    repository.add_batch_items.assert_called_once()
    session.commit.assert_called_once()

    repository.list_work_items_for_run.return_value = list(plan.work_items)
    repository.list_batch_items_for_run.return_value = list(plan.batch_items)
    repository.list_active_lingxing_sku_ids.reset_mock()
    repository.add_work_items.reset_mock()
    repository.add_batch_items.reset_mock()
    session.commit.reset_mock()

    persisted = service.load_or_freeze_product_info_plan(run)

    assert persisted is not None
    assert persisted.work_items == plan.work_items
    assert persisted.batch_items == plan.batch_items
    repository.list_active_lingxing_sku_ids.assert_not_called()
    repository.add_work_items.assert_not_called()
    repository.add_batch_items.assert_not_called()
    session.commit.assert_not_called()


def test_productinfo_plan_rejects_half_persisted_frozen_state() -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository
    run = _run()

    repository.list_work_items_for_run.return_value = [SimpleNamespace()]
    repository.list_batch_items_for_run.return_value = []
    service._fail = MagicMock()  # type: ignore[method-assign]

    plan = service.load_or_freeze_product_info_plan(run)

    assert plan is None
    service._fail.assert_called_once_with(run, "SYNC_FROZEN_PLAN_INVALID")
    repository.list_active_lingxing_sku_ids.assert_not_called()


def test_productinfo_plan_rejects_batch_size_above_provider_limit() -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository
    run = _run()

    repository.list_work_items_for_run.return_value = []
    repository.list_batch_items_for_run.return_value = []
    repository.list_active_lingxing_sku_ids.return_value = ["synthetic-id"]
    repository.batch_size_for_run.return_value = 21
    service._fail = MagicMock()  # type: ignore[method-assign]

    plan = service.load_or_freeze_product_info_plan(run)

    assert plan is None
    service._fail.assert_called_once_with(run, "SYNC_BATCH_SIZE_INVALID")
    repository.add_work_items.assert_not_called()
    repository.add_batch_items.assert_not_called()
