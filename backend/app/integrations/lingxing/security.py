import hashlib
import json
import re
from datetime import date

from pydantic import JsonValue

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "appsecret",
        "authorization",
        "clientsecret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "privatekey",
        "refreshtoken",
        "secret",
        "setcookie",
        "sign",
        "signature",
        "token",
        "webhook",
        "webhookurl",
        "xapikey",
    }
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_FEISHU_WEBHOOK_PATTERN = re.compile(
    r"(?i)https://open\.(?:feishu\.cn|larksuite\.com)/open-apis/bot/v2/hook/[^\s\"'<>]+"
)
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|app[_-]?secret|"
    r"client[_-]?secret|api[_-]?key|x[_-]?api[_-]?key|credentials?|token|secret|"
    r"password|private[_-]?key|signature|sign|webhook(?:[_-]?url)?|"
    r"set[_-]?cookie|cookie)\s*([=:])\s*([^\s&;,]+)"
)


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.casefold() if character.isalnum())


def _is_sensitive_key(key: str) -> bool:
    return _normalized_key(key) in _SENSITIVE_KEYS


def redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub(REDACTED, value)
    value = _FEISHU_WEBHOOK_PATTERN.sub(REDACTED, value)
    return _ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value
    )


def redact_json(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def raw_hash(
    *,
    api_path: str,
    request_method: str,
    request_params: JsonValue,
    request_body: JsonValue,
    response: JsonValue,
    data_date: date | None,
) -> str:
    canonical = canonical_json(
        {
            "api_path": api_path,
            "data_date": data_date.isoformat() if data_date is not None else None,
            "request_body": request_body,
            "request_method": request_method,
            "request_params": request_params,
            "response": response,
        }
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
