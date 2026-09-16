from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.integrations.lingxing.security import REDACTED, canonical_json, redact_json
from app.modules.integration_sync.data_pages_catalog import (
    DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY,
)
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
)
from app.modules.integration_sync.parsers.lingxing_data_pages import DataPagesParserKey
from app.modules.integration_sync.repository import IntegrationSyncRepository

_UNSAFE_REQUEST_PARAM_KEY_PARTS = frozenset(
    {
        "access_token",
        "authorization",
        "cookie",
        "password",
        "payload",
        "raw",
        "secret",
        "sign",
        "signature",
        "token",
    }
)


class DataPagesRawCaptureError(RuntimeError):
    """Safe DATA-PAGES RAW capture error without source payload details."""


@dataclass(frozen=True, slots=True)
class DataPagesRawCaptureEnvelope:
    """Synthetic or future controlled RAW capture input.

    The envelope contains an already-received response. This module does not call
    Lingxing, read credentials, plan schedules, or authorize production execution.
    """

    parser_key: DataPagesParserKey
    request_safe_params: dict[str, object]
    response_json: JsonValue
    attempt_no: int
    requested_at: datetime
    received_at: datetime
    response_code: int | None = None
    provider_code: str | None = None
    is_success: bool = True
    response_count: int | None = None


@dataclass(frozen=True, slots=True)
class DataPagesRawCaptureResult:
    raw_blob_id: UUID
    raw_request_ref_id: UUID
    response_hash: str
    payload_bytes: int
    response_count: int | None


class DataPagesRawCaptureHandler:
    """Persist redacted RAW blobs and request references for DATA-PAGES work items."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def capture(
        self,
        run: IntegrationSyncRun,
        work_item: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        envelope: DataPagesRawCaptureEnvelope,
    ) -> DataPagesRawCaptureResult:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY.get(envelope.parser_key)
        if spec is None:
            raise DataPagesRawCaptureError("DATA_PAGES_RAW_CAPTURE_UNKNOWN_PARSER")
        _validate_capture_context(run, work_item, policy, envelope, spec.interface_key)
        _assert_safe_request_params(envelope.request_safe_params)

        payload = redact_json(envelope.response_json)
        response_hash = _response_hash(payload)
        encoded = canonical_json(payload).encode("utf-8")
        blob = self.repository.find_blob_by_hash(response_hash)
        if blob is None:
            blob = self.repository.add_raw_blob(
                ApiRawBlob(
                    id=uuid4(),
                    response_hash=response_hash,
                    payload_json=payload,
                    payload_bytes=len(encoded),
                    content_type="application/json",
                    storage_mode="database",
                    archive_uri=None,
                    retention_policy_id=policy.id,
                    received_at=envelope.received_at,
                    archived_at=None,
                    payload_deleted_at=None,
                )
            )
        response_count = envelope.response_count
        if response_count is None:
            response_count = _response_count(payload)
        raw_ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work_item.id,
                raw_blob_id=blob.id,
                request_kind=work_item.request_kind,
                attempt_no=envelope.attempt_no,
                request_safe_params=dict(envelope.request_safe_params),
                http_status=envelope.response_code,
                provider_code=envelope.provider_code or _provider_code(payload),
                is_success=envelope.is_success,
                response_count=response_count,
                requested_at=envelope.requested_at,
                received_at=envelope.received_at,
            )
        )
        work_item.attempt_count = envelope.attempt_no
        work_item.response_count = response_count
        run.records_seen += response_count or 0
        self.session.commit()
        return DataPagesRawCaptureResult(
            raw_blob_id=blob.id,
            raw_request_ref_id=raw_ref.id,
            response_hash=response_hash,
            payload_bytes=len(encoded),
            response_count=response_count,
        )


def _validate_capture_context(
    run: IntegrationSyncRun,
    work_item: IntegrationSyncRunWorkItem,
    policy: RawRetentionPolicy,
    envelope: DataPagesRawCaptureEnvelope,
    interface_key: str,
) -> None:
    spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[envelope.parser_key]
    if (
        run.provider != "lingxing"
        or run.interface_key != interface_key
        or work_item.run_id != run.id
        or work_item.request_kind != spec.request_kind
        or policy.policy_key != spec.retention_policy_key
        or not policy.is_active
        or envelope.attempt_no < 1
    ):
        raise DataPagesRawCaptureError("DATA_PAGES_RAW_CAPTURE_CONTEXT_INVALID")


def _assert_safe_request_params(value: object) -> None:
    if not isinstance(value, dict):
        raise DataPagesRawCaptureError("DATA_PAGES_RAW_CAPTURE_UNSAFE_REQUEST_PARAMS")
    for key, item in value.items():
        if not isinstance(key, str) or _is_unsafe_key(key):
            raise DataPagesRawCaptureError("DATA_PAGES_RAW_CAPTURE_UNSAFE_REQUEST_PARAMS")
        _assert_safe_request_param_value(item)


def _assert_safe_request_param_value(value: object) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, dict):
        _assert_safe_request_params(value)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe_request_param_value(item)
        return
    raise DataPagesRawCaptureError("DATA_PAGES_RAW_CAPTURE_UNSAFE_REQUEST_PARAMS")


def _is_unsafe_key(value: str) -> bool:
    normalized = value.casefold().replace("-", "_")
    return any(part in normalized for part in _UNSAFE_REQUEST_PARAM_KEY_PARTS)


def _response_hash(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _response_count(payload: JsonValue) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return len(data)
        rows = payload.get("rows")
        if isinstance(rows, list):
            return len(rows)
    return None


def _provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip()[:64]


def payload_contains_redacted_marker(payload: JsonValue) -> bool:
    """Test helper proving redaction happened without exposing the original value."""

    return REDACTED in canonical_json(payload)
