from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.integration_sync.handlers.lingxing_batch_product_info import ordered_id_hash
from app.modules.integration_sync.models import (
    IntegrationSyncRunWorkItem,
    LingxingProductInfoBatchItem,
)
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import (
    SYNC_PRODUCTINFO_RETRY_PLAN_INVALID,
    IntegrationSyncService,
)


def _source_run() -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=100),
        config_id=UUID(int=101),
        interface_id=UUID(int=102),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        status="failed",
        window_start=None,
        window_end=None,
    )


def _work(
    *,
    work_id: int,
    ordinal: int,
    status: str,
    product_ids: list[str],
) -> IntegrationSyncRunWorkItem:
    return IntegrationSyncRunWorkItem(
        id=UUID(int=work_id),
        run_id=UUID(int=100),
        ordinal=ordinal,
        request_kind="id_batch_page",
        status=status,
        attempt_count=2 if status == "failed" else 1,
        batch_no=ordinal,
        id_count=len(product_ids),
        id_hash=ordered_id_hash(product_ids),
        request_safe_params={"batch_no": ordinal, "id_count": len(product_ids)},
    )


def _members(
    work: IntegrationSyncRunWorkItem,
    product_ids: list[str],
) -> list[LingxingProductInfoBatchItem]:
    assert work.batch_no is not None
    return [
        LingxingProductInfoBatchItem(
            id=UUID(int=1000 + index + work.ordinal * 10),
            run_id=UUID(int=100),
            work_item_id=work.id,
            source_account_ref="synthetic-account",
            batch_no=work.batch_no,
            item_ordinal=index,
            lingxing_sku_id=product_id,
            raw_request_ref_id=None,
            item_status=work.status,
        )
        for index, product_id in enumerate(product_ids)
    ]


def _service() -> tuple[IntegrationSyncService, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    repository = MagicMock()
    service.repository = repository
    repository.find_run_by_idempotency.return_value = None

    def add_run(run: object) -> object:
        if getattr(run, "id", None) is None:
            run.id = UUID(int=500)  # type: ignore[attr-defined]
        return run

    repository.add_run.side_effect = add_run
    repository.add_work_items.side_effect = lambda values: list(values)
    repository.add_batch_items.side_effect = lambda values: list(values)
    repository.add_event.side_effect = lambda value: value
    return service, session, repository


def test_productinfo_retry_copies_only_failed_frozen_membership() -> None:
    service, session, repository = _service()
    source = _source_run()
    failed_ids = ["synthetic-a", "synthetic-b"]
    succeeded_ids = ["synthetic-c"]
    failed = _work(work_id=201, ordinal=2, status="failed", product_ids=failed_ids)
    succeeded = _work(work_id=202, ordinal=3, status="succeeded", product_ids=succeeded_ids)

    repository.get_run.return_value = source
    repository.list_work_items_for_run.return_value = [failed, succeeded]
    repository.list_batch_items_for_run.return_value = [
        *_members(failed, failed_ids),
        *_members(succeeded, succeeded_ids),
    ]

    created = service.create_retry_run(
        source.id,
        TriggerRequest(reason="synthetic retry"),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
        account_refs=frozenset({"synthetic-account"}),
    )

    assert created.retry_of_run_id == source.id
    copied_work_items = list(repository.add_work_items.call_args.args[0])
    copied_batch_items = list(repository.add_batch_items.call_args.args[0])
    assert len(copied_work_items) == 1
    assert copied_work_items[0].ordinal == failed.ordinal
    assert copied_work_items[0].id_hash == failed.id_hash
    assert copied_work_items[0].attempt_count == 0
    assert copied_work_items[0].status == "queued"
    assert [item.lingxing_sku_id for item in copied_batch_items] == failed_ids
    assert [item.item_ordinal for item in copied_batch_items] == [0, 1]
    assert all(item.item_status == "queued" for item in copied_batch_items)
    repository.list_active_lingxing_sku_ids.assert_not_called()
    session.commit.assert_called_once()


def test_productinfo_retry_rejects_source_without_failed_work_item() -> None:
    service, _, repository = _service()
    source = _source_run()
    succeeded = _work(
        work_id=202,
        ordinal=1,
        status="succeeded",
        product_ids=["synthetic-c"],
    )
    repository.get_run.return_value = source
    repository.list_work_items_for_run.return_value = [succeeded]
    repository.list_batch_items_for_run.return_value = _members(
        succeeded,
        ["synthetic-c"],
    )

    with pytest.raises(ApiError):
        service.create_retry_run(
            source.id,
            TriggerRequest(reason="synthetic retry"),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"synthetic-account"}),
        )

    repository.add_run.assert_not_called()


def test_productinfo_retry_fails_closed_when_frozen_hash_is_tampered() -> None:
    service, session, repository = _service()
    source = _source_run()
    failed = _work(
        work_id=201,
        ordinal=1,
        status="failed",
        product_ids=["synthetic-a"],
    )
    failed.id_hash = "f" * 64
    repository.get_run.return_value = source
    repository.list_work_items_for_run.return_value = [failed]
    repository.list_batch_items_for_run.return_value = _members(
        failed,
        ["synthetic-a"],
    )

    with pytest.raises(ApiError) as error:
        service.create_retry_run(
            source.id,
            TriggerRequest(reason="synthetic retry"),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"synthetic-account"}),
        )

    assert error.value.code == SYNC_PRODUCTINFO_RETRY_PLAN_INVALID
    session.rollback.assert_called_once()


def test_productinfo_retry_rejects_anomaly_breaker_source() -> None:
    service, session, repository = _service()
    source = _source_run()
    source.error_code = "PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED"
    repository.get_run.return_value = source

    with pytest.raises(ApiError) as error:
        service.create_retry_run(
            source.id,
            TriggerRequest(reason="synthetic retry"),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"synthetic-account"}),
        )

    assert error.value.code == "SYNC_RUN_NOT_RETRYABLE"
    repository.list_work_items_for_run.assert_not_called()
    repository.add_run.assert_not_called()
    session.commit.assert_not_called()
