from datetime import date

from pydantic import JsonValue

from app.integrations.lingxing.security import (
    REDACTED,
    canonical_json,
    raw_hash,
    redact_json,
    redact_text,
)


def test_recursive_redaction_and_hash_are_stable() -> None:
    marker = "credential-fixture"
    first: JsonValue = {
        "z": [{"Access-Token": marker}, "authorization=credential-fixture"],
        "a": {"private_key": marker, "value": 1, "webhook_url": marker},
    }
    second: JsonValue = {
        "a": {"webhook_url": marker, "value": 1, "private_key": marker},
        "z": [{"Access-Token": marker}, "authorization=credential-fixture"],
    }

    sanitized_first = redact_json(first)
    sanitized_second = redact_json(second)
    serialized = canonical_json(sanitized_first)

    assert marker not in serialized
    assert serialized.count(REDACTED) == 4
    assert canonical_json(sanitized_first) == canonical_json(sanitized_second)
    assert raw_hash(
        api_path="/basicOpen/multiplatform/walmart/list",
        request_method="POST",
        request_params=None,
        request_body=sanitized_first,
        response={"ok": True},
        data_date=date(2026, 1, 1),
    ) == raw_hash(
        api_path="/basicOpen/multiplatform/walmart/list",
        request_method="POST",
        request_params=None,
        request_body=sanitized_second,
        response={"ok": True},
        data_date=date(2026, 1, 1),
    )


def test_sensitive_aliases_are_redacted_without_hiding_business_fields() -> None:
    marker = "credential-fixture"
    sensitive_keys = (
        "app_secret",
        "appSecret",
        "access_token",
        "accessToken",
        "refresh_token",
        "refreshToken",
        "authorization",
        "token",
        "secret",
        "api_key",
        "apiKey",
        "x_api_key",
        "x-api-key",
        "credential",
        "credentials",
        "password",
        "cookie",
        "set-cookie",
        "webhook",
        "webhook_url",
        "signature",
        "sign",
        "private_key",
        "client_secret",
    )
    sensitive: JsonValue = {
        "nested": [{key: marker} for key in sensitive_keys],
    }
    business: JsonValue = {
        "listing_status": "active",
        "assign_status": "assigned",
        "design_name": "sample",
        "stock_days": 30,
    }

    sanitized = redact_json({"sensitive": sensitive, "business": business})

    assert marker not in canonical_json(sanitized)
    assert isinstance(sanitized, dict)
    assert sanitized["business"] == business


def test_feishu_webhook_url_value_is_redacted() -> None:
    value = "notify https://open.feishu.cn/open-apis/bot/v2/hook/credential-fixture now"

    sanitized = redact_text(value)

    assert "credential-fixture" not in sanitized
    assert REDACTED in sanitized
