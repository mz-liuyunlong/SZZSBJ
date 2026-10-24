from __future__ import annotations

import base64
import gzip
import hashlib
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from alembic import command
from app.core.api import ApiError
from app.core.auth import (
    WALMART_MONITOR_PRINCIPAL_ID,
    WALMART_MONITOR_WRITE_PERMISSION,
    Principal,
    get_optional_principal,
)
from app.core.config import Settings, SettingsError, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.walmart_monitor.models import RawWalmartMonitorEvent
from app.modules.walmart_monitor.repository import (
    RawEventWriteResult,
    WalmartMonitorEventRepository,
)
from app.modules.walmart_monitor.schemas import WalmartMonitorRawEventRequest
from app.modules.walmart_monitor.service import (
    WalmartMonitorIngestionResult,
    WalmartMonitorIngestionService,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
SYNTHETIC_TOKEN = "synthetic-monitor-token-value-000000000000"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_monitor_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.delenv("WALMART_MONITOR_INGEST_TOKEN", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _source_payload(raw: bytes = b'{"synthetic":true}') -> dict[str, object]:
    compressed = gzip.compress(raw)
    return {
        "kind": "synthetic_provider_response",
        "content_type": "application/json",
        "compression": "gzip",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "stored_byte_size": len(compressed),
        "data_base64": base64.b64encode(compressed).decode("ascii"),
    }


def _payload() -> dict[str, Any]:
    return {
        "schema_version": "walmart-monitor.raw.v1",
        "event_id": "walmart-monitor:synthetic-instance:check:1",
        "captured_at": "2026-01-15T01:02:03+00:00",
        "requested_provider": "AUTO",
        "producer": {
            "instance_id": "synthetic-instance",
            "check_id": "1",
            "run_id": "synthetic-run",
        },
        "targets": [
            {
                "source_account_ref": "synthetic-account",
                "store_id": "synthetic-store",
                "item_id": "synthetic-item",
                "store_name": "Synthetic Store",
                "sku": "SYNTHETIC-SKU",
                "msku": "SYNTHETIC-MSKU",
                "owner": "synthetic-owner",
                "product_name": "Synthetic product",
                "product_category": "Synthetic > Category",
                "wfs_inventory": 5,
                "monitoring_eligible": True,
            }
        ],
        "attempts": [
            {
                "attempt_no": 1,
                "provider": "DECODO_API",
                "outcome": "SUCCESS",
                "source_payloads": [_source_payload()],
            },
            {
                "attempt_no": 2,
                "provider": "CHROME_EXTENSION",
                "outcome": "SUCCESS",
                "source_payloads": [],
            },
        ],
        "final_observation": {
            "outcome": "SUCCESS",
            "data_source": "CHROME_EXTENSION",
            "error_code": None,
            "duration_ms": 123,
            "parsed_result": {
                "walmartCategory": {"path": [{"name": "Synthetic"}, {"name": "Category"}]}
            },
        },
    }


class MemoryRepository:
    def __init__(self) -> None:
        self.events: dict[str, RawWalmartMonitorEvent] = {}

    def insert_or_get(self, values: dict[str, object]) -> RawEventWriteResult:
        event_id = cast(str, values["event_id"])
        existing = self.events.get(event_id)
        if existing is not None:
            return RawEventWriteResult(event=existing, created=False)
        event = RawWalmartMonitorEvent(**values)
        self.events[event_id] = event
        return RawEventWriteResult(event=event, created=True)


def test_schema_requires_offset_unique_attempts_and_forbids_unknown_fields() -> None:
    naive = _payload()
    naive["captured_at"] = "2026-01-15T01:02:03"
    with pytest.raises(ValidationError, match="explicit UTC offset"):
        WalmartMonitorRawEventRequest.model_validate(naive)

    duplicate_attempt = _payload()
    duplicate_attempt["attempts"][1]["attempt_no"] = 1
    with pytest.raises(ValidationError, match="attempt_no must be unique"):
        WalmartMonitorRawEventRequest.model_validate(duplicate_attempt)

    extra = _payload()
    extra["unknown"] = "not-accepted"
    with pytest.raises(ValidationError):
        WalmartMonitorRawEventRequest.model_validate(extra)


def test_schema_preserves_monitoring_eligibility_at_capture_time() -> None:
    payload = _payload()
    payload["targets"][0]["monitoring_eligible"] = False

    request = WalmartMonitorRawEventRequest.model_validate(payload)

    assert request.targets[0].monitoring_eligible is False


def test_service_saves_one_unified_event_and_exact_replay_is_idempotent() -> None:
    payload = WalmartMonitorRawEventRequest.model_validate(_payload())
    session = MagicMock(spec=Session)
    repository = MemoryRepository()
    service = WalmartMonitorIngestionService(session, repository=repository)

    first = service.ingest(payload, idempotency_key=payload.event_id)
    replay = service.ingest(payload, idempotency_key=payload.event_id)

    assert first.duplicate is False
    assert replay.duplicate is True
    assert first.id == replay.id
    assert len(repository.events) == 1
    saved = repository.events[payload.event_id]
    assert saved.target_count == 1
    assert saved.attempt_count == 2
    assert saved.payload_json["targets"][0]["product_category"] == "Synthetic > Category"
    assert [row["provider"] for row in saved.payload_json["attempts"]] == [
        "DECODO_API",
        "CHROME_EXTENSION",
    ]
    assert session.commit.call_count == 2


def test_changed_replay_conflicts_and_rolls_back() -> None:
    session = MagicMock(spec=Session)
    repository = MemoryRepository()
    service = WalmartMonitorIngestionService(session, repository=repository)
    original = WalmartMonitorRawEventRequest.model_validate(_payload())
    service.ingest(original, idempotency_key=original.event_id)

    changed_data = _payload()
    changed_data["final_observation"]["outcome"] = "FAILED"
    changed = WalmartMonitorRawEventRequest.model_validate(changed_data)
    with pytest.raises(ApiError) as error:
        service.ingest(changed, idempotency_key=changed.event_id)

    assert error.value.code == "MONITOR_EVENT_CONFLICT"
    assert error.value.status_code == 409
    assert session.rollback.called
    assert len(repository.events) == 1


@pytest.mark.parametrize("field", ["data_base64", "sha256", "stored_byte_size", "byte_size"])
def test_artifact_integrity_failure_rejects_entire_event(field: str) -> None:
    data = _payload()
    artifact = data["attempts"][0]["source_payloads"][0]
    replacements: dict[str, object] = {
        "data_base64": base64.b64encode(b"not-gzip").decode("ascii"),
        "sha256": "0" * 64,
        "stored_byte_size": artifact["stored_byte_size"] + 1,
        "byte_size": artifact["byte_size"] + 1,
    }
    artifact[field] = replacements[field]
    payload = WalmartMonitorRawEventRequest.model_validate(data)
    session = MagicMock(spec=Session)
    repository = MemoryRepository()

    with pytest.raises(ApiError) as error:
        WalmartMonitorIngestionService(session, repository=repository).ingest(
            payload,
            idempotency_key=payload.event_id,
        )

    assert error.value.code == "MONITOR_RAW_PAYLOAD_INVALID"
    assert repository.events == {}
    session.commit.assert_not_called()


def test_decompression_limit_rejects_compressed_bomb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.walmart_monitor import service as service_module

    data = _payload()
    data["attempts"][0]["source_payloads"][0] = _source_payload(b"12345")
    payload = WalmartMonitorRawEventRequest.model_validate(data)
    monkeypatch.setattr(service_module, "MAX_UNCOMPRESSED_ARTIFACT_BYTES", 4)

    with pytest.raises(ApiError) as error:
        WalmartMonitorIngestionService(
            MagicMock(spec=Session),
            repository=MemoryRepository(),
        ).ingest(payload, idempotency_key=payload.event_id)

    assert error.value.code == "MONITOR_RAW_PAYLOAD_TOO_LARGE"
    assert error.value.status_code == 413


def test_repository_uses_atomic_postgresql_event_id_conflict_guard() -> None:
    payload = WalmartMonitorRawEventRequest.model_validate(_payload())
    event_id = uuid4()
    event = RawWalmartMonitorEvent(
        id=event_id,
        event_id=payload.event_id,
        schema_version=payload.schema_version,
        producer_instance_id=payload.producer.instance_id,
        producer_check_id=payload.producer.check_id,
        producer_run_id=payload.producer.run_id,
        captured_at=payload.captured_at,
        requested_provider=payload.requested_provider,
        final_outcome=payload.final_observation.outcome,
        target_count=1,
        attempt_count=2,
        raw_hash="0" * 64,
        payload_bytes=1,
        payload_json={},
        received_at=datetime.now(UTC),
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [event_id, event]

    result = WalmartMonitorEventRepository(session).insert_or_get(
        {
            column.name: getattr(event, column.name)
            for column in RawWalmartMonitorEvent.__table__.columns
        }
    )

    statement = session.scalar.call_args_list[0].args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "ON CONFLICT (event_id) DO NOTHING" in compiled
    assert result.created is True
    assert result.event is event


def test_raw_model_is_isolated_from_existing_business_tables() -> None:
    assert RawWalmartMonitorEvent.__table__.foreign_keys == set()
    assert RawWalmartMonitorEvent.__tablename__ == "raw_walmart_monitor_events"


def test_monitor_raw_migration_is_additive_and_isolated() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(
        config,
        "20261020_0047_walmart_order_identity_guard:20261022_0048_walmart_monitor_raw_events",
        sql=True,
    )
    sql = buffer.getvalue()

    assert "CREATE TABLE raw_walmart_monitor_events" in sql
    assert "CONSTRAINT uq_raw_walmart_monitor_events_event_id UNIQUE (event_id)" in sql
    assert "CREATE INDEX ix_raw_walmart_monitor_events_captured_at" in sql
    assert "CREATE INDEX ix_raw_walmart_monitor_events_raw_hash" in sql
    assert "FOREIGN KEY" not in sql
    assert "ALTER TABLE" not in sql
    assert "mart_listing_management_current" not in sql
    assert "product_platform_listings" not in sql
    assert "listing_gpt_analysis_links" not in sql
    assert "listing_archive_states" not in sql


def test_monitor_token_settings_are_secret_and_fail_closed() -> None:
    configured = Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "WALMART_MONITOR_INGEST_TOKEN": SYNTHETIC_TOKEN,
        }
    )
    assert configured.walmart_monitor_ingest_configured is True
    assert SYNTHETIC_TOKEN not in repr(configured)
    assert SYNTHETIC_TOKEN not in configured.model_dump_json()

    for invalid in ("short", "x" * 31 + "错"):
        with pytest.raises(SettingsError) as error:
            Settings.model_validate(
                {
                    "APP_ENV": "test",
                    "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
                    "WALMART_MONITOR_INGEST_TOKEN": invalid,
                }
            )
        assert invalid not in str(error.value)


def test_monitor_token_is_exact_route_and_least_privilege(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("WALMART_MONITOR_INGEST_TOKEN", SYNTHETIC_TOKEN)
    get_settings.cache_clear()
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/integrations/walmart-monitor/raw-events",
        "headers": [(b"authorization", f"Bearer {SYNTHETIC_TOKEN}".encode())],
    }

    principal = get_optional_principal(Request(scope))

    assert principal == Principal(
        user_id=WALMART_MONITOR_PRINCIPAL_ID,
        permissions=frozenset({WALMART_MONITOR_WRITE_PERMISSION}),
    )
    scope["path"] = "/api/integrations/sync-runs"
    from app.modules.iam import service as iam_service

    monkeypatch.setattr(iam_service, "resolve_principal_from_token", lambda _: None)
    assert get_optional_principal(Request(scope)) is None


def test_api_requires_machine_token_and_returns_no_raw_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("WALMART_MONITOR_INGEST_TOKEN", SYNTHETIC_TOKEN)
    get_settings.cache_clear()
    event_id = _payload()["event_id"]

    def fake_ingest(
        _self: WalmartMonitorIngestionService,
        _payload_model: WalmartMonitorRawEventRequest,
        *,
        idempotency_key: str,
    ) -> WalmartMonitorIngestionResult:
        assert idempotency_key == event_id
        return WalmartMonitorIngestionResult(
            id=UUID("00000000-0000-4000-8000-000000000001"),
            event_id=cast(str, event_id),
            duplicate=False,
            received_at=datetime(2026, 1, 15, tzinfo=UTC),
        )

    monkeypatch.setattr(WalmartMonitorIngestionService, "ingest", fake_ingest)
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    client = TestClient(application)
    headers = {
        "Authorization": f"Bearer {SYNTHETIC_TOKEN}",
        "Idempotency-Key": cast(str, event_id),
    }

    assert (
        client.post(
            "/api/integrations/walmart-monitor/raw-events",
            headers={**headers, "Authorization": "Bearer wrong-token-value"},
            json=_payload(),
        ).status_code
        == 401
    )
    response = client.post(
        "/api/integrations/walmart-monitor/raw-events",
        headers=headers,
        json=_payload(),
    )

    assert response.status_code == 201
    assert response.json()["data"] == {
        "id": "00000000-0000-4000-8000-000000000001",
        "event_id": event_id,
        "accepted": True,
        "duplicate": False,
        "received_at": "2026-01-15T00:00:00Z",
    }
    response_text = response.text
    assert "source_account_ref" not in response_text
    assert "data_base64" not in response_text
    assert SYNTHETIC_TOKEN not in response_text


def test_openapi_registers_only_the_approved_monitor_contracts() -> None:
    application = create_app()
    schema = application.openapi()
    paths = schema["paths"]

    assert "/api/integrations/walmart-monitor/raw-events" in paths
    operation = paths["/api/integrations/walmart-monitor/raw-events"]["post"]
    assert operation["operationId"] == "ingestWalmartMonitorRawEvent"
    assert "201" in operation["responses"]
    assert "409" in operation["responses"]
    assert "413" in operation["responses"]
    assert {path for path in paths if path.startswith("/api/integrations/walmart-monitor/")} == {
        "/api/integrations/walmart-monitor/raw-events",
        "/api/integrations/walmart-monitor/targets",
    }


def test_api_rejects_idempotency_key_mismatch_without_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("WALMART_MONITOR_INGEST_TOKEN", SYNTHETIC_TOKEN)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).post(
        "/api/integrations/walmart-monitor/raw-events",
        headers={
            "Authorization": f"Bearer {SYNTHETIC_TOKEN}",
            "Idempotency-Key": "different-synthetic-event",
        },
        json=_payload(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MONITOR_IDEMPOTENCY_KEY_INVALID"
    assert "synthetic-account" not in response.text
    assert SYNTHETIC_TOKEN not in response.text
