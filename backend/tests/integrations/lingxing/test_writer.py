from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.lingxing.client import LingxingEndpoint, LingxingRawEnvelope
from app.models.raw_lingxing_api import RawLingxingApi
from app.repositories.lingxing_raw import LingxingRawRepository
from app.services.lingxing_raw import LingxingRawService, LingxingWriteError

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
ENDPOINT: LingxingEndpoint = "/basicOpen/multiplatform/walmart/list"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _envelope() -> LingxingRawEnvelope:
    return LingxingRawEnvelope(
        api_path=ENDPOINT,
        request_params_json={"access_token": "credential-fixture"},
        request_body_json={"page": 1},
        response_json={"nested": {"private-key": "credential-fixture"}},
        response_code=200,
        is_success=True,
        pulled_at=NOW,
        page_no=1,
        page_size=3,
        store_id="scope-fixture",
        object_type="synthetic_object",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="batch-fixture",
        attempt_no=1,
        extra_json={"authorization": "credential-fixture"},
    )


def test_dry_run_computes_hash_without_repository_or_transaction_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = LingxingRawService(session, _settings())
    add = MagicMock()
    monkeypatch.setattr(service.repository, "add", add)

    first = service.save([_envelope()])[0]
    second = service.save([_envelope()])[0]

    assert first.written is False
    assert first.raw_hash == second.raw_hash
    assert len(first.raw_hash) == 64
    add.assert_not_called()
    session.commit.assert_not_called()


def test_write_guard_denies_raw_and_structured_writes() -> None:
    session = MagicMock(spec=Session)
    service = LingxingRawService(
        session,
        _settings(LINGXING_DRY_RUN=False, LINGXING_ALLOW_RAW_WRITE=False),
    )

    with pytest.raises(LingxingWriteError, match="RAW writes are disabled"):
        service.save([_envelope()])

    with pytest.raises(ValidationError, match="structured writes are not approved"):
        _settings(LINGXING_ALLOW_STRUCTURED_WRITE=True)
    session.commit.assert_not_called()


def test_writer_sanitizes_appends_and_service_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = LingxingRawService(
        session,
        _settings(LINGXING_DRY_RUN=False, LINGXING_ALLOW_RAW_WRITE=True),
    )

    def add(record: RawLingxingApi) -> RawLingxingApi:
        record.id = 1
        return record

    persisted = MagicMock(side_effect=add)
    monkeypatch.setattr(service.repository, "add", persisted)

    result = service.save([_envelope()])[0]
    record = persisted.call_args.args[0]

    assert result.written is True
    assert result.record_id == 1
    assert "credential-fixture" not in str(record.request_params_json)
    assert "credential-fixture" not in str(record.response_json)
    assert "credential-fixture" not in str(record.extra_json)
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_writer_keeps_only_safe_summary_for_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = LingxingRawService(
        session,
        _settings(LINGXING_DRY_RUN=False, LINGXING_ALLOW_RAW_WRITE=True),
    )
    envelope = _envelope().model_copy(
        update={
            "response_json": None,
            "is_success": False,
            "error_code": "RESPONSE_TOO_LARGE",
            "error_message": "Lingxing response exceeded configured byte limit",
        }
    )

    def add(record: RawLingxingApi) -> RawLingxingApi:
        record.id = 1
        return record

    persisted = MagicMock(side_effect=add)
    monkeypatch.setattr(service.repository, "add", persisted)

    service.save([envelope])
    record = persisted.call_args.args[0]

    assert record.response_json is None
    assert record.error_code == "RESPONSE_TOO_LARGE"
    assert record.error_message == "Lingxing response exceeded configured byte limit"


def test_repository_flushes_without_owning_transaction() -> None:
    session = MagicMock(spec=Session)
    repository = LingxingRawRepository(session)
    record = RawLingxingApi(
        api_path=ENDPOINT,
        request_method="POST",
        is_success=False,
        pulled_at=NOW,
        raw_hash="0" * 64,
        object_type="synthetic_object",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="batch-fixture",
        attempt_no=1,
    )

    repository.add(record)

    session.add.assert_called_once_with(record)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
