from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.integrations.lingxing.security import canonical_json
from app.modules.integration_sync.data_pages_raw_capture import (
    DataPagesRawCaptureEnvelope,
    DataPagesRawCaptureError,
    DataPagesRawCaptureHandler,
    payload_contains_redacted_marker,
)
from app.modules.integration_sync.models import (
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-0000-0000-000000000101")
WORK_ID = UUID("00000000-0000-0000-0000-000000000102")
INTERFACE_ID = UUID("00000000-0000-0000-0000-000000000103")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000104")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000105")


def _run(interface_key: str = "orderV2List") -> IntegrationSyncRun:
    return IntegrationSyncRun(
        id=RUN_ID,
        config_id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        provider="lingxing",
        interface_key=interface_key,
        source_account_ref="default",
        trigger_type="manual",
        status="running",
        idempotency_key="synthetic-data-pages-run",
        work_items_total=1,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )


def _work() -> IntegrationSyncRunWorkItem:
    return IntegrationSyncRunWorkItem(
        id=WORK_ID,
        run_id=RUN_ID,
        ordinal=1,
        request_kind="offset_page",
        status="running",
        attempt_count=0,
        offset_value=0,
        length_value=100,
        request_safe_params={"offset": 0, "length": 100},
    )


def _policy() -> RawRetentionPolicy:
    return RawRetentionPolicy(
        id=POLICY_ID,
        policy_key="lingxing-data-pages-order-v2-list-v1",
        provider="lingxing",
        interface_key="orderV2List",
        hot_retention_days=365,
        archive_after_days=None,
        delete_after_days=None,
        archive_required=False,
        legal_hold=False,
        is_active=True,
    )


def _handler() -> tuple[DataPagesRawCaptureHandler, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    handler = DataPagesRawCaptureHandler(session)
    repository = MagicMock()
    handler.repository = repository
    repository.find_blob_by_hash.return_value = None
    repository.add_raw_blob.side_effect = lambda blob: blob
    repository.add_raw_request_ref.side_effect = lambda ref: ref
    return handler, repository, session


def test_data_pages_raw_capture_persists_redacted_payload_metadata() -> None:
    handler, repository, session = _handler()
    run = _run()
    work = _work()
    policy = _policy()

    result = handler.capture(
        run,
        work,
        policy,
        DataPagesRawCaptureEnvelope(
            parser_key="order_v2_list",
            request_safe_params={"offset": 0, "length": 100},
            response_json={
                "code": "0",
                "access_token": "secret-value",
                "data": [{"order_id": "synthetic-order"}],
            },
            response_code=200,
            attempt_no=1,
            requested_at=NOW,
            received_at=NOW,
            is_success=True,
        ),
    )

    blob = repository.add_raw_blob.call_args.args[0]
    request_ref = repository.add_raw_request_ref.call_args.args[0]

    assert payload_contains_redacted_marker(blob.payload_json)
    assert "secret-value" not in canonical_json(blob.payload_json)
    assert request_ref.request_safe_params == {"offset": 0, "length": 100}
    assert request_ref.provider_code == "0"
    assert request_ref.is_success is True
    assert request_ref.response_count == 1
    assert work.attempt_count == 1
    assert work.response_count == 1
    assert run.records_seen == 1
    assert result.raw_blob_id == blob.id
    assert result.raw_request_ref_id == request_ref.id
    assert result.response_count == 1
    session.commit.assert_called_once_with()


def test_data_pages_raw_capture_reuses_existing_blob_by_response_hash() -> None:
    handler, repository, _session = _handler()
    existing_blob = MagicMock()
    existing_blob.id = UUID("00000000-0000-0000-0000-000000000201")
    repository.find_blob_by_hash.return_value = existing_blob

    result = handler.capture(
        _run(),
        _work(),
        _policy(),
        DataPagesRawCaptureEnvelope(
            parser_key="order_v2_list",
            request_safe_params={"offset": 0, "length": 100},
            response_json={"code": "0", "data": []},
            response_code=200,
            attempt_no=1,
            requested_at=NOW,
            received_at=NOW,
            is_success=True,
        ),
    )

    repository.add_raw_blob.assert_not_called()
    assert result.raw_blob_id == existing_blob.id


def test_data_pages_raw_capture_rejects_unsafe_request_params() -> None:
    handler, repository, _session = _handler()

    with pytest.raises(DataPagesRawCaptureError) as exc_info:
        handler.capture(
            _run(),
            _work(),
            _policy(),
            DataPagesRawCaptureEnvelope(
                parser_key="order_v2_list",
                request_safe_params={"access_token": "secret-value"},
                response_json={"code": "0", "data": []},
                response_code=200,
                attempt_no=1,
                requested_at=NOW,
                received_at=NOW,
                is_success=True,
            ),
        )

    assert str(exc_info.value) == "DATA_PAGES_RAW_CAPTURE_UNSAFE_REQUEST_PARAMS"
    repository.add_raw_blob.assert_not_called()
    repository.add_raw_request_ref.assert_not_called()


def test_data_pages_raw_capture_rejects_mismatched_interface_context() -> None:
    handler, repository, _session = _handler()

    with pytest.raises(DataPagesRawCaptureError) as exc_info:
        handler.capture(
            _run(interface_key="walmartListingList"),
            _work(),
            _policy(),
            DataPagesRawCaptureEnvelope(
                parser_key="order_v2_list",
                request_safe_params={"offset": 0, "length": 100},
                response_json={"code": "0", "data": []},
                response_code=200,
                attempt_no=1,
                requested_at=NOW,
                received_at=NOW,
                is_success=True,
            ),
        )

    assert str(exc_info.value) == "DATA_PAGES_RAW_CAPTURE_CONTEXT_INVALID"
    repository.add_raw_blob.assert_not_called()
    repository.add_raw_request_ref.assert_not_called()
