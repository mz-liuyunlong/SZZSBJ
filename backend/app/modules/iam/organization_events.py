"""Authenticated Feishu v2 organization-event decoding; no database or provider I/O.

Public endpoint must validate the original encrypted body before trusting any
event fields.  Event identifiers, not message payloads, are retained for replay
protection; the current Feishu directory remains the organization authority.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from app.core.api import ApiError, ErrorCode

_MAX_BODY_BYTES = 64 * 1024
_MAX_EVENT_AGE_SECONDS = 7 * 60 * 60  # Feishu may retry up to six hours.
_MAX_FUTURE_SECONDS = 300
_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")

CONTACT_EVENTS = frozenset(
    {
        "contact.user.created_v3",
        "contact.user.updated_v3",
        "contact.user.deleted_v3",
        "contact.department.created_v3",
        "contact.department.updated_v3",
        "contact.department.deleted_v3",
        "contact.scope.updated_v3",
    }
)


@dataclass(frozen=True, slots=True)
class FeishuEvent:
    event_id: str
    event_type: str
    open_id: str | None
    revoke_session: bool


@dataclass(frozen=True, slots=True)
class FeishuPayload:
    challenge: str | None
    event: FeishuEvent | None


def _reject() -> None:
    raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)


def _event_json(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422) from exc
    if not isinstance(parsed, dict):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    return parsed


def _decrypt(encrypt_key: str, ciphertext: str) -> bytes:
    try:
        decoded = base64.b64decode(ciphertext, validate=True)
        if len(decoded) < 32 or len(decoded) % 16 != 0:
            raise ValueError("Invalid Feishu ciphertext length")
        iv, data = decoded[:16], decoded[16:]
        cipher = Cipher(
            algorithms.AES(hashlib.sha256(encrypt_key.encode("utf-8")).digest()),
            modes.CBC(iv),
        )
        decryptor = cipher.decryptor()
        padded = decryptor.update(data) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except (ValueError, TypeError) as exc:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403) from exc


def decode_feishu_event(
    *,
    raw_body: bytes,
    timestamp: str,
    nonce: str,
    signature: str,
    encrypt_key: str,
    verification_token: str,
    app_id: str,
    now_seconds: int | None = None,
) -> FeishuPayload:
    """Verify signed encrypted delivery and normalize only approved contact events."""
    if not 0 < len(raw_body) <= _MAX_BODY_BYTES:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=413)
    if not encrypt_key or not verification_token or not app_id:
        _reject()
    if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 16:
        _reject()
    if not nonce or len(nonce) > 128 or not signature or len(signature) != 64:
        _reject()
    sent = int(timestamp)
    now = int(time.time()) if now_seconds is None else now_seconds
    if sent < now - _MAX_EVENT_AGE_SECONDS or sent > now + _MAX_FUTURE_SECONDS:
        _reject()

    expected = hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode("utf-8") + raw_body
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        _reject()

    wrapper = _event_json(raw_body)
    encrypted = wrapper.get("encrypt")
    if not isinstance(encrypted, str) or not encrypted:
        _reject()  # Never accept unsigned/plaintext Feishu events.
    payload = _event_json(_decrypt(encrypt_key, encrypted))

    header = payload.get("header")
    if not isinstance(header, dict):
        header = {}
    token = header.get("token") or payload.get("token")
    if not isinstance(token, str) or not hmac.compare_digest(
        token, verification_token
    ):
        _reject()

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str) or not 0 < len(challenge) <= 1024:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        return FeishuPayload(challenge=challenge, event=None)

    if payload.get("schema") != "2.0" or header.get("app_id") != app_id:
        _reject()
    event_type = header.get("event_type")
    event_id = header.get("event_id")
    if not isinstance(event_type, str) or event_type not in CONTACT_EVENTS:
        return FeishuPayload(challenge=None, event=None)
    if not isinstance(event_id, str) or not _ID_PATTERN.fullmatch(event_id):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    event = payload.get("event")
    if not isinstance(event, dict):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    obj = event.get("object")
    if not isinstance(obj, dict):
        obj = {}
    old = event.get("old_object")
    if not isinstance(old, dict):
        old = {}
    open_id = obj.get("open_id") or old.get("open_id")
    if not isinstance(open_id, str) or not _ID_PATTERN.fullmatch(open_id):
        open_id = None
    status = obj.get("status")
    if not isinstance(status, dict):
        status = {}
    revoke = bool(
        event_type == "contact.user.deleted_v3"
        or (
            event_type == "contact.user.updated_v3"
            and (
                status.get("is_frozen") is True
                or status.get("is_resigned") is True
                or status.get("is_exited") is True
                or status.get("is_activated") is False
                or status.get("is_active") is False
            )
        )
    )
    return FeishuPayload(
        challenge=None,
        event=FeishuEvent(
            event_id=event_id,
            event_type=event_type,
            open_id=open_id if event_type.startswith("contact.user.") else None,
            revoke_session=revoke,
        ),
    )
