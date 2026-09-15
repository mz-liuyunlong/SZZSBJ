from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchPlan,
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.handlers.lingxing_product_info_executor import (
    PRODUCT_INFO_ENDPOINT,
    LingxingProductInfoExecutor,
    product_info_response_succeeded,
)
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _envelope(
    product_ids: tuple[str, ...],
    *,
    returned_ids: tuple[str, ...] | None = None,
) -> LingxingRawEnvelope:
    ids = returned_ids if returned_ids is not None else product_ids
    return LingxingRawEnvelope(
        api_path=PRODUCT_INFO_ENDPOINT,
        request_params_json=None,
        request_body_json={"productIds": list(product_ids)},
        response_json={
            "code": 0,
            "data": [
                {
                    "id": value,
                    "sku": f"SYNTHETIC-{index}",
                    "product_name": f"Synthetic Product {index}",
                }
                for index, value in enumerate(ids)
            ],
        },
        response_code=200,
        is_success=True,
        pulled_at=NOW,
        page_no=1,
        page_size=len(product_ids),
        store_id="synthetic-account",
        object_type="lingxing_batch_product_info",
        trace_id="synthetic-run",
        run_id="synthetic-run",
        batch_id="synthetic-work",
        attempt_no=1,
    )


def _publication(status: str = "changed") -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        snapshot_id=uuid4(),
        business_hash="0" * 64,
        images_written=0,
        tags_written=0,
    )


def _executor(
    product_ids: list[str],
) -> tuple[LingxingProductInfoExecutor, BatchPlan, MagicMock, MagicMock, MagicMock]:
    plan = LingxingBatchGetProductInfoSyncHandler().build_plan(
        run_id=UUID(int=1),
        source_account_ref="synthetic-account",
        lingxing_sku_ids=product_ids,
        batch_size=20,
    )
    client = MagicMock()
    executor = LingxingProductInfoExecutor(MagicMock(spec=Session), client=client)
    repository = MagicMock()
    publisher = MagicMock()
    executor.repository = repository
    executor.publisher = publisher
    repository.get_interface_by_key.return_value = SimpleNamespace(id=UUID(int=2))
    repository.get_retention_policy.return_value = SimpleNamespace(id=UUID(int=3))
    repository.find_blob_by_hash.return_value = None
    repository.add_raw_blob.side_effect = lambda value: value
    repository.add_raw_request_ref.side_effect = lambda value: value
    repository.max_attempts_for_run.return_value = 1
    publisher.publish_with_result.return_value = _publication()
    return executor, plan, client, repository, publisher


def test_real_executor_batches_ids_serially_and_publishes_persisted_details() -> None:
    product_ids = [f"synthetic-id-{index:02d}" for index in range(21)]
    executor, plan, client, repository, publisher = _executor(product_ids)
    captured_batches: list[tuple[str, ...]] = []

    def fetch(**kwargs: object) -> LingxingRawEnvelope:
        batch = kwargs["product_ids"]
        assert isinstance(batch, tuple)
        captured_batches.append(batch)
        return _envelope(batch)

    client.fetch_batch_product_info.side_effect = fetch
    result = executor.execute(source_account_ref="synthetic-account", plan=plan)

    assert [len(batch) for batch in captured_batches] == [20, 1]
    assert result.work_items_succeeded == 2
    assert result.records_seen == 21
    assert result.snapshots_written == 21
    assert publisher.publish_with_result.call_count == 21
    assert repository.add_raw_blob.call_count == 2
    assert repository.add_raw_request_ref.call_count == 2


def test_existing_run_executor_uses_persisted_plan_without_creating_second_run() -> None:
    executor, plan, client, repository, publisher = _executor(["synthetic-id"])
    run = SimpleNamespace(
        id=UUID(int=1),
        interface_id=UUID(int=2),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        status="running",
        work_items_total=1,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
        finished_at=None,
    )
    client.fetch_batch_product_info.return_value = _envelope(("synthetic-id",))

    result = executor.execute_existing_run(run=run, plan=plan)

    assert result.work_items_succeeded == 1
    assert run.status == "succeeded"
    repository.add_run.assert_not_called()
    repository.add_work_items.assert_not_called()
    repository.add_batch_items.assert_not_called()
    publisher.publish_with_result.assert_called_once()


def test_existing_run_counts_unchanged_as_seen_but_not_written() -> None:
    executor, plan, client, _repository, publisher = _executor(["synthetic-id"])
    run = SimpleNamespace(
        id=UUID(int=1),
        interface_id=UUID(int=2),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        status="running",
        work_items_total=1,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
        finished_at=None,
    )
    client.fetch_batch_product_info.return_value = _envelope(("synthetic-id",))
    publisher.publish_with_result.return_value = _publication("unchanged")

    result = executor.execute_existing_run(run=run, plan=plan)

    assert result.records_seen == 1
    assert result.snapshots_written == 0
    assert run.records_seen == 1
    assert run.records_written == 0


def test_existing_run_rejects_tampered_frozen_membership_before_outbound() -> None:
    executor, plan, client, _repository, _publisher = _executor(["synthetic-id"])
    run = SimpleNamespace(
        id=UUID(int=1),
        interface_id=UUID(int=2),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        status="running",
        work_items_total=1,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
        finished_at=None,
    )
    plan.work_items[0].id_hash = "f" * 64

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute_existing_run(run=run, plan=plan)

    client.fetch_batch_product_info.assert_not_called()


def test_real_executor_fails_closed_on_contract_field_mismatch() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    client.fetch_batch_product_info.return_value = _envelope(
        ("synthetic-id",),
        returned_ids=("unexpected-id",),
    )
    run = SimpleNamespace(
        id=plan.work_items[0].run_id,
        work_items_failed=0,
        status="running",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    work = SimpleNamespace(
        id=plan.work_items[0].id,
        status="running",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.return_value = work
    repository.list_work_items_for_run_for_update.return_value = [work]
    repository.list_batch_items_for_run_for_update.return_value = []

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute(source_account_ref="synthetic-account", plan=plan)

    assert run.error_code == "PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED"
    assert work.error_code == "CONTRACT_FIELD_MISMATCH"
    assert work.error_code == "CONTRACT_FIELD_MISMATCH"
    assert "unexpected-id" not in str(run.error_message)


def test_product_info_success_contract_requires_code_zero_and_list_data() -> None:
    response = httpx.Response(200)
    assert product_info_response_succeeded(PRODUCT_INFO_ENDPOINT, response, {"code": 0, "data": []})
    assert not product_info_response_succeeded(
        PRODUCT_INFO_ENDPOINT,
        response,
        {"code": 0, "data": {}},
    )
    assert not product_info_response_succeeded(
        PRODUCT_INFO_ENDPOINT,
        response,
        {"code": 1, "data": []},
    )


def _failed_http_envelope(product_ids: tuple[str, ...]) -> LingxingRawEnvelope:
    return LingxingRawEnvelope(
        api_path=PRODUCT_INFO_ENDPOINT,
        request_params_json=None,
        request_body_json={"productIds": list(product_ids)},
        response_json={"code": 503, "data": []},
        response_code=503,
        is_success=False,
        error_code="HTTP_ERROR",
        error_message="safe",
        pulled_at=NOW,
        page_no=1,
        page_size=len(product_ids),
        store_id="synthetic-account",
        object_type="lingxing_batch_product_info",
        trace_id="synthetic-run",
        run_id="synthetic-run",
        batch_id="synthetic-work",
        attempt_no=1,
    )


def _existing_run() -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(int=1),
        config_id=UUID(int=9),
        interface_id=UUID(int=2),
        provider="lingxing",
        interface_key="batchGetProductInfo",
        source_account_ref="synthetic-account",
        status="running",
        work_items_total=1,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
        finished_at=None,
        error_code=None,
        error_message=None,
    )


def test_existing_run_retries_only_current_work_item_and_persists_attempt_numbers() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    run = _existing_run()
    repository.max_attempts_for_run.return_value = 2
    client.fetch_batch_product_info.side_effect = [
        _failed_http_envelope(("synthetic-id",)),
        _envelope(("synthetic-id",)),
    ]

    result = executor.execute_existing_run(run=run, plan=plan)

    assert result.work_items_succeeded == 1
    assert client.fetch_batch_product_info.call_count == 2
    assert plan.work_items[0].attempt_count == 2
    refs = [call.args[0] for call in repository.add_raw_request_ref.call_args_list]
    assert [ref.attempt_no for ref in refs] == [1, 2]


def test_existing_run_stops_at_configured_max_attempts() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    run = _existing_run()
    repository.max_attempts_for_run.return_value = 2
    client.fetch_batch_product_info.side_effect = [
        RuntimeError("synthetic transport"),
        RuntimeError("synthetic transport"),
    ]
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.return_value = plan.work_items[0]

    with pytest.raises(ProductInfoOneTimeRunError, match="PRODUCT_INFO_TRANSPORT_FAILED"):
        executor.execute_existing_run(run=run, plan=plan)

    assert client.fetch_batch_product_info.call_count == 2
    assert plan.work_items[0].attempt_count == 2
    assert plan.work_items[0].status == "failed"
    assert run.status == "failed"


def test_deterministic_contract_mismatch_is_not_retried() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    run = _existing_run()
    repository.max_attempts_for_run.return_value = 3
    client.fetch_batch_product_info.return_value = _envelope(
        ("synthetic-id",),
        returned_ids=("unexpected-id",),
    )
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.return_value = plan.work_items[0]

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute_existing_run(run=run, plan=plan)

    client.fetch_batch_product_info.assert_called_once()


@pytest.mark.parametrize("variant", ["unexpected", "missing", "duplicate"])
def test_anomaly_breaker_stops_later_batches_on_response_membership_anomaly(
    variant: str,
) -> None:
    product_ids = [f"synthetic-id-{index:02d}" for index in range(21)]
    executor, plan, client, repository, _publisher = _executor(product_ids)
    run = _existing_run()
    run.work_items_total = len(plan.work_items)
    repository.max_attempts_for_run.return_value = 3
    repository.get_run_for_update.return_value = run
    repository.list_work_items_for_run_for_update.return_value = list(plan.work_items)
    repository.list_batch_items_for_run_for_update.return_value = list(plan.batch_items)

    first_batch = tuple(item.lingxing_sku_id for item in plan.batch_items if item.batch_no == 1)
    if variant == "unexpected":
        returned_ids = (*first_batch[:-1], "unexpected-id")
    elif variant == "missing":
        returned_ids = first_batch[:-1]
    else:
        returned_ids = (*first_batch[:-1], first_batch[0])

    client.fetch_batch_product_info.return_value = _envelope(
        first_batch,
        returned_ids=returned_ids,
    )

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute_existing_run(run=run, plan=plan)

    assert client.fetch_batch_product_info.call_count == 1
    assert run.status == "failed"
    assert plan.work_items[0].status == "failed"
    assert plan.work_items[0].error_code == "CONTRACT_FIELD_MISMATCH"
    assert plan.work_items[1].status == "canceled"
    assert plan.work_items[1].error_code == "PRODUCT_INFO_ANOMALY_BREAKER"
    first_items = [item for item in plan.batch_items if item.batch_no == 1]
    second_items = [item for item in plan.batch_items if item.batch_no == 2]
    assert all(item.item_status == "failed" for item in first_items)
    assert all(item.item_status == "canceled" for item in second_items)
    event = repository.add_event.call_args.args[0]
    assert event.message_code == "PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED"
    assert event.safe_details == {
        "error_code": "CONTRACT_FIELD_MISMATCH",
        "canceled_work_items": 1,
    }
    assert "unexpected-id" not in str(run.error_message)


def test_frozen_membership_anomaly_fails_bad_batch_and_never_goes_outbound() -> None:
    product_ids = [f"synthetic-id-{index:02d}" for index in range(21)]
    executor, plan, client, repository, _publisher = _executor(product_ids)
    run = _existing_run()
    run.work_items_total = len(plan.work_items)
    repository.max_attempts_for_run.return_value = 2
    repository.get_run_for_update.return_value = run
    repository.list_work_items_for_run_for_update.return_value = list(plan.work_items)
    repository.list_batch_items_for_run_for_update.return_value = list(plan.batch_items)

    plan.work_items[1].id_hash = "f" * 64

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute_existing_run(run=run, plan=plan)

    client.fetch_batch_product_info.assert_not_called()
    assert run.status == "failed"
    assert plan.work_items[1].status == "failed"
    assert plan.work_items[0].status == "canceled"
    assert all(
        item.item_status == "failed"
        for item in plan.batch_items
        if item.batch_no == plan.work_items[1].batch_no
    )
    assert all(
        item.item_status == "canceled"
        for item in plan.batch_items
        if item.batch_no == plan.work_items[0].batch_no
    )


def test_transient_batch_failure_does_not_skip_later_frozen_batches() -> None:
    product_ids = [f"synthetic-id-{index:02d}" for index in range(21)]
    executor, plan, client, repository, _publisher = _executor(product_ids)
    run = _existing_run()
    run.work_items_total = len(plan.work_items)
    repository.max_attempts_for_run.return_value = 1
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.side_effect = lambda _run_id, work_id: next(
        work for work in plan.work_items if work.id == work_id
    )
    repository.list_batch_items_for_run_for_update.return_value = list(plan.batch_items)

    second_batch = tuple(item.lingxing_sku_id for item in plan.batch_items if item.batch_no == 2)
    client.fetch_batch_product_info.side_effect = [
        RuntimeError("synthetic transport"),
        _envelope(second_batch),
    ]

    with pytest.raises(ProductInfoOneTimeRunError, match="PRODUCT_INFO_TRANSPORT_FAILED"):
        executor.execute_existing_run(run=run, plan=plan)

    assert client.fetch_batch_product_info.call_count == 2
    assert plan.work_items[0].status == "failed"
    assert plan.work_items[1].status == "succeeded"
    assert run.work_items_failed == 1
    assert run.work_items_succeeded == 1
    assert run.records_seen == 1
    assert run.records_written == 1
    assert run.status == "failed"
    assert run.error_code == "PRODUCT_INFO_TRANSPORT_FAILED"


def test_partial_publication_persists_completed_item_evidence_before_batch_failure() -> None:
    executor, plan, client, repository, publisher = _executor(["synthetic-id-a", "synthetic-id-b"])
    run = _existing_run()
    repository.max_attempts_for_run.return_value = 1
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.return_value = plan.work_items[0]
    repository.list_batch_items_for_run_for_update.return_value = list(plan.batch_items)
    client.fetch_batch_product_info.return_value = _envelope(("synthetic-id-a", "synthetic-id-b"))
    publisher.publish_with_result.side_effect = [
        _publication("changed"),
        RuntimeError("synthetic publication failure"),
    ]

    with pytest.raises(ProductInfoOneTimeRunError, match="PRODUCT_INFO_EXECUTION_FAILED"):
        executor.execute_existing_run(run=run, plan=plan)

    first_item, second_item = plan.batch_items
    assert first_item.item_status == "succeeded"
    assert first_item.raw_request_ref_id is not None
    assert second_item.item_status == "failed"
    assert run.records_seen == 2
    assert run.records_written == 1
    assert run.work_items_failed == 1
    assert run.status == "failed"


def test_existing_run_heartbeats_before_outbound_and_publication() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    heartbeat = MagicMock()
    executor.heartbeat = heartbeat
    run = _existing_run()
    repository.max_attempts_for_run.return_value = 1
    client.fetch_batch_product_info.return_value = _envelope(("synthetic-id",))

    result = executor.execute_existing_run(run=run, plan=plan)

    assert result.work_items_succeeded == 1
    assert heartbeat.call_count == 2
