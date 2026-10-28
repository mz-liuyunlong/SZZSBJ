from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.walmart_monitor.models import RawWalmartMonitorEvent
from app.modules.walmart_monitor.projection import WalmartMonitorProjectionService
from app.modules.walmart_monitor.repository import (
    RawEventWriteResult,
    WalmartMonitorEventRepository,
)
from app.modules.walmart_monitor.schemas import (
    MAX_COMPRESSED_ARTIFACT_BYTES,
    MAX_UNCOMPRESSED_ARTIFACT_BYTES,
    MonitorSourcePayload,
    WalmartMonitorRawEventRequest,
)


class RawEventRepository(Protocol):
    def insert_or_get(self, values: dict[str, object]) -> RawEventWriteResult: ...


class RawEventProjector(Protocol):
    def project(self, raw_event: RawWalmartMonitorEvent) -> int: ...


@dataclass(frozen=True, slots=True)
class WalmartMonitorIngestionResult:
    id: UUID
    event_id: str
    duplicate: bool
    received_at: datetime


class WalmartMonitorIngestionService:
    def __init__(
        self,
        session: Session,
        *,
        repository: RawEventRepository | None = None,
        projector: RawEventProjector | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or WalmartMonitorEventRepository(session)
        self.projector = (
            projector
            if projector is not None
            else WalmartMonitorProjectionService(session)
            if repository is None
            else None
        )

    def ingest(
        self,
        payload: WalmartMonitorRawEventRequest,
        *,
        idempotency_key: str,
    ) -> WalmartMonitorIngestionResult:
        if idempotency_key != payload.event_id:
            raise ApiError(
                code="MONITOR_IDEMPOTENCY_KEY_INVALID",
                status_code=422,
            )

        for attempt in payload.attempts:
            for source_payload in attempt.source_payloads:
                _validate_source_payload(source_payload)

        normalized_payload = payload.model_dump(mode="json")
        canonical_bytes = json.dumps(
            normalized_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        raw_hash = hashlib.sha256(canonical_bytes).hexdigest()
        received_at = datetime.now(UTC)
        values: dict[str, object] = {
            "id": uuid4(),
            "event_id": payload.event_id,
            "schema_version": payload.schema_version,
            "producer_instance_id": payload.producer.instance_id,
            "producer_check_id": payload.producer.check_id,
            "producer_run_id": payload.producer.run_id,
            "captured_at": payload.captured_at,
            "requested_provider": payload.requested_provider,
            "final_outcome": payload.final_observation.outcome,
            "target_count": len(payload.targets),
            "attempt_count": len(payload.attempts),
            "raw_hash": raw_hash,
            "payload_bytes": len(canonical_bytes),
            "payload_json": normalized_payload,
            "received_at": received_at,
        }

        try:
            write_result = self.repository.insert_or_get(values)
            if not write_result.created and not hmac.compare_digest(
                write_result.event.raw_hash,
                raw_hash,
            ):
                self.session.rollback()
                raise ApiError(code="MONITOR_EVENT_CONFLICT", status_code=409)
            if write_result.created and self.projector is not None:
                self.projector.project(write_result.event)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        event: RawWalmartMonitorEvent = write_result.event
        return WalmartMonitorIngestionResult(
            id=event.id,
            event_id=event.event_id,
            duplicate=not write_result.created,
            received_at=event.received_at,
        )


def _validate_source_payload(source_payload: MonitorSourcePayload) -> None:
    try:
        stored_bytes = base64.b64decode(source_payload.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(code="MONITOR_RAW_PAYLOAD_INVALID", status_code=422) from None

    if (
        len(stored_bytes) != source_payload.stored_byte_size
        or len(stored_bytes) > MAX_COMPRESSED_ARTIFACT_BYTES
    ):
        code = (
            "MONITOR_RAW_PAYLOAD_TOO_LARGE"
            if len(stored_bytes) > MAX_COMPRESSED_ARTIFACT_BYTES
            else "MONITOR_RAW_PAYLOAD_INVALID"
        )
        raise ApiError(code=code, status_code=413 if code.endswith("TOO_LARGE") else 422)

    try:
        with gzip.GzipFile(fileobj=BytesIO(stored_bytes), mode="rb") as archive:
            raw_bytes = archive.read(MAX_UNCOMPRESSED_ARTIFACT_BYTES + 1)
    except (EOFError, gzip.BadGzipFile, OSError):
        raise ApiError(code="MONITOR_RAW_PAYLOAD_INVALID", status_code=422) from None

    if len(raw_bytes) > MAX_UNCOMPRESSED_ARTIFACT_BYTES:
        raise ApiError(code="MONITOR_RAW_PAYLOAD_TOO_LARGE", status_code=413)
    if len(raw_bytes) != source_payload.byte_size:
        raise ApiError(code="MONITOR_RAW_PAYLOAD_INVALID", status_code=422)
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    if not hmac.compare_digest(actual_hash, source_payload.sha256):
        raise ApiError(code="MONITOR_RAW_PAYLOAD_INVALID", status_code=422)
