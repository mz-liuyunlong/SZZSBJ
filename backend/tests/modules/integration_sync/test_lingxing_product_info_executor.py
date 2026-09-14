from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

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
    assert publisher.publish.call_count == 21
    assert repository.add_raw_blob.call_count == 2
    assert repository.add_raw_request_ref.call_count == 2


def test_real_executor_fails_closed_on_contract_field_mismatch() -> None:
    executor, plan, client, repository, _publisher = _executor(["synthetic-id"])
    client.fetch_batch_product_info.return_value = _envelope(
        ("synthetic-id",),
        returned_ids=("unexpected-id",),
    )
    run = SimpleNamespace(
        work_items_failed=0,
        status="running",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    work = SimpleNamespace(status="running", error_code=None, error_message=None, finished_at=None)
    repository.get_run_for_update.return_value = run
    repository.get_work_item_for_update.return_value = work

    with pytest.raises(ProductInfoOneTimeRunError, match="CONTRACT_FIELD_MISMATCH"):
        executor.execute(source_account_ref="synthetic-account", plan=plan)

    assert run.error_code == "CONTRACT_FIELD_MISMATCH"
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
