"""Encrypted Feishu event delivery contracts, without provider or DB traffic."""

import base64
import hashlib
import json
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from app.core.api import ApiError
from app.modules.iam.organization_events import decode_feishu_event

_KEY = "synthetic-encrypt-key"
_TOKEN = "synthetic-verification-token"
_APP_ID = "cli_synthetic"
_TIMESTAMP = "1780000000"
_NONCE = "synthetic-nonce"
_IV = b"1234567890abcdef"


def _signed_payload(payload: dict) -> dict[str, str | bytes]:
    plaintext = json.dumps(payload).encode()
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(hashlib.sha256(_KEY.encode()).digest()), modes.CBC(_IV)
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    raw = json.dumps({"encrypt": base64.b64encode(_IV + encrypted).decode()}).encode()
    signature = hashlib.sha256(
        (_TIMESTAMP + _NONCE + _KEY).encode() + raw
    ).hexdigest()
    return {"raw_body": raw, "timestamp": _TIMESTAMP, "nonce": _NONCE,
            "signature": signature, "encrypt_key": _KEY,
            "verification_token": _TOKEN, "app_id": _APP_ID,
            "now_seconds": int(_TIMESTAMP)}


def _user_payload(event_type: str, status: dict | None = None) -> dict:
    return {
        "schema": "2.0",
        "header": {
            "app_id": _APP_ID,
            "event_id": "event-1",
            "event_type": event_type,
            "token": _TOKEN,
        },
        "event": {"object": {"open_id": "ou-synthetic", "status": status or {}}},
    }


def test_verified_leave_event_requests_immediate_session_revocation() -> None:
    delivery = _signed_payload(_user_payload("contact.user.deleted_v3"))
    event = decode_feishu_event(**delivery).event
    assert event is not None
    assert event.event_id == "event-1"
    assert event.open_id == "ou-synthetic"
    assert event.revoke_session is True


def test_verified_active_update_only_requests_reconciliation() -> None:
    delivery = _signed_payload(
        _user_payload("contact.user.updated_v3", {"is_active": True})
    )
    event = decode_feishu_event(**delivery).event
    assert event is not None
    assert event.revoke_session is False


def test_verified_freeze_event_revokes_session() -> None:
    delivery = _signed_payload(
        _user_payload("contact.user.updated_v3", {"is_frozen": True})
    )
    event = decode_feishu_event(**delivery).event
    assert event is not None
    assert event.revoke_session is True


def test_signed_challenge_needs_verification_token() -> None:
    delivery = _signed_payload({
        "type": "url_verification", "token": _TOKEN, "challenge": "synthetic-challenge"
    })
    result = decode_feishu_event(**delivery)
    assert result.challenge == "synthetic-challenge"
    assert result.event is None


@pytest.mark.parametrize("corrupted", ["signature", "timestamp", "verification_token"])
def test_invalid_signature_staleness_or_verification_token_rejected(corrupted: str) -> None:
    delivery = _signed_payload(_user_payload("contact.user.deleted_v3"))
    if corrupted == "signature":
        delivery["signature"] = "f" * 64
    elif corrupted == "timestamp":
        delivery["now_seconds"] = int(_TIMESTAMP) + 8 * 60 * 60
    else:
        delivery["verification_token"] = "bad-token"
    with pytest.raises(ApiError) as denied:
        decode_feishu_event(**delivery)
    assert denied.value.status_code == 403


def test_unsupported_contact_event_is_acknowledged_without_any_action() -> None:
    delivery = _signed_payload(_user_payload("contact.untrusted.unknown_v3"))
    result = decode_feishu_event(**delivery)
    assert result.event is None


def test_event_inbox_is_idempotent_and_revocation_is_scoped_to_linked_account() -> None:
    from app.modules.iam.organization_event_inbox import (
        enqueue_contact_event,
        revoke_linked_sessions,
    )
    from app.modules.iam.organization_events import FeishuEvent

    session = MagicMock()
    session.execute.return_value.scalar.side_effect = ["event-1", None]
    event = FeishuEvent("event-1", "contact.user.deleted_v3", "ou-synthetic", True)
    assert enqueue_contact_event(session, event) is True
    assert enqueue_contact_event(session, event) is False

    revoke_linked_sessions(session, "ou-synthetic")
    query = str(session.execute.call_args.args[0])
    assert "u.feishu_open_id = :open_id" in query
    assert "s.revoked_at IS NULL" in query
    assert "UPDATE app_sessions" in query
    assert "ou-synthetic" not in query
    session.commit.assert_not_called()


def test_retry_inbox_has_bounded_attempts_and_manual_review() -> None:
    from app.modules.iam.organization_event_inbox import reschedule_events

    session = MagicMock()
    reschedule_events(
        session,
        [{"event_id": "evt-1", "attempt_count": 6}], error_code="RECONCILE_FAILURE"
    )
    assert session.execute.call_args.args[1]["status"] == "needs_review"
    assert session.execute.call_args.args[1]["error_code"] == "RECONCILE_FAILURE"


def test_worker_disabled_does_not_access_directory_or_database(monkeypatch) -> None:
    from app.modules.iam.organization_tasks import organization_event_tick

    monkeypatch.delenv("SZZSBJ_FEISHU_ORG_EVENTS_ENABLED", raising=False)
    monkeypatch.setenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED", "1")
    outside = MagicMock()
    monkeypatch.setattr("app.modules.iam.organization_tasks._read_feishu", outside)
    monkeypatch.setattr("app.modules.iam.organization_tasks.get_session_factory", outside)
    organization_event_tick()
    outside.assert_not_called()
