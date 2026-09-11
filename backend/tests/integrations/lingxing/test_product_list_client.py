import base64
import json

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import (
    LingxingCaptureRequest,
    LingxingClientError,
    LingxingEndpoint,
    LingxingPageRequest,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.query_sign import (
    aes_ecb_base64,
    build_canonical_signing_params,
    build_query_auth_params,
    build_signing_string,
    canonical_value,
    md5_uppercase,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
PRODUCT_LIST_ENDPOINT: LingxingEndpoint = "/erp/sc/routing/data/local_inventory/productList"
SYNTHETIC_APP_ID = "0123456789ABCDEF"
SYNTHETIC_TOKEN = "access-token-fixture"
SYNTHETIC_TIMESTAMP = "1712345678"


class _FakeTokenProvider:
    def __init__(self) -> None:
        self.get_calls = 0
        self.recover_calls: list[int | str] = []

    def get_access_token(self) -> SecretStr:
        self.get_calls += 1
        return SecretStr(SYNTHETIC_TOKEN)

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        self.recover_calls.append(provider_code)
        return SecretStr("rotated-access-token-fixture")


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": SYNTHETIC_APP_ID,
            "LINGXING_ENABLE_REAL_CALLS": True,
        }
    )


def _capture(
    *,
    body: JsonValue,
    params: dict[str, str | int | float | bool | None] | None = None,
    page_size: int = 3,
) -> LingxingCaptureRequest:
    return LingxingCaptureRequest(
        api_path=PRODUCT_LIST_ENDPOINT,
        pages=(
            LingxingPageRequest(
                page_no=1,
                page_size=page_size,
                params=params,
                body=body,
            ),
        ),
        store_ids=("account-scope-fixture",),
        object_type="synthetic_product_list",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="batch-fixture",
    )


def _is_success(
    endpoint: LingxingEndpoint,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del endpoint, response
    return isinstance(payload, dict) and payload.get("code") == 0


def test_canonical_signing_rules_are_deterministic() -> None:
    business_params: dict[str, JsonValue] = {
        "z": "",
        "none": None,
        "zero": 0,
        "false": False,
        "items": [1, "值"],
        "nested": {"b": 2, "a": 1},
        "sign": "must-not-participate",
        "alpha": "value",
    }
    params = build_canonical_signing_params(
        business_params,
        access_token=SecretStr(SYNTHETIC_TOKEN),
        app_id=SYNTHETIC_APP_ID,
        timestamp=SYNTHETIC_TIMESTAMP,
    )

    assert build_signing_string(params) == (
        f"access_token={SYNTHETIC_TOKEN}&alpha=value&app_key={SYNTHETIC_APP_ID}"
        '&false=false&items=[1,"值"]&nested={"b":2,"a":1}'
        f"&none=null&timestamp={SYNTHETIC_TIMESTAMP}&zero=0"
    )
    assert canonical_value(None) == "null"
    assert canonical_value(False) == "false"
    assert canonical_value(0) == "0"
    assert canonical_value([1, {"name": "值"}]) == '[1,{"name":"值"}]'


def test_md5_and_aes_base64_steps_are_stable() -> None:
    assert md5_uppercase("abc") == "900150983CD24FB0D6963F7D28E17F72"

    first = aes_ecb_base64("900150983CD24FB0D6963F7D28E17F72", app_id=SYNTHETIC_APP_ID)
    second = aes_ecb_base64("900150983CD24FB0D6963F7D28E17F72", app_id=SYNTHETIC_APP_ID)

    assert first == second
    assert len(base64.b64decode(first, validate=True)) == 48


def test_query_auth_uses_app_id_and_unix_second_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.lingxing.query_sign.time",
        lambda: 1_712_345_678.9,
    )

    auth = build_query_auth_params(
        {"offset": 0, "sign": "ignored"},
        access_token=SecretStr(SYNTHETIC_TOKEN),
        app_id=SYNTHETIC_APP_ID,
    )

    assert set(auth) == {"access_token", "app_key", "timestamp", "sign"}
    assert auth["access_token"] == SYNTHETIC_TOKEN
    assert auth["app_key"] == SYNTHETIC_APP_ID
    assert auth["timestamp"] == SYNTHETIC_TIMESTAMP
    assert auth["timestamp"].isdecimal()
    assert len(auth["timestamp"]) == 10
    assert auth["sign"]


def test_product_list_empty_body_uses_query_auth_without_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.lingxing.query_sign.time",
        lambda: 1_712_345_678.9,
    )
    calls = 0
    captured_sign = ""
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, captured_sign
        calls += 1
        assert request.method == "POST"
        assert request.url.path == PRODUCT_LIST_ENDPOINT
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Accept"] == "application/json"
        assert "Authorization" not in request.headers
        assert json.loads(request.content) == {}
        assert set(request.url.params) == {"access_token", "app_key", "timestamp", "sign"}
        assert request.url.params["access_token"] == SYNTHETIC_TOKEN
        assert request.url.params["app_key"] == SYNTHETIC_APP_ID
        assert request.url.params["timestamp"] == SYNTHETIC_TIMESTAMP
        captured_sign = request.url.params["sign"]
        assert captured_sign
        return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture(body={}))[0]
    finally:
        client.close()

    serialized = envelope.model_dump_json()
    assert envelope.is_success is True
    assert envelope.request_params_json is None
    assert envelope.request_body_json == {}
    assert SYNTHETIC_TOKEN not in serialized
    assert SYNTHETIC_APP_ID not in serialized
    assert SYNTHETIC_TIMESTAMP not in serialized
    assert captured_sign not in serialized
    assert calls == 1
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == []


def test_product_list_pagination_stays_in_json_body() -> None:
    calls = 0
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json.loads(request.content) == {"offset": 0, "length": 3}
        assert "offset" not in request.url.params
        assert "length" not in request.url.params
        return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture(body={"offset": 0, "length": 3}))[0]
    finally:
        client.close()

    assert envelope.is_success is True
    assert envelope.request_params_json is None
    assert envelope.request_body_json == {"offset": 0, "length": 3}
    assert calls == 1
    assert token_provider.get_calls == 1


def test_product_list_provider_error_is_a_safe_envelope() -> None:
    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"code": 1, "message": "rejected"})
        ),
    )
    try:
        envelope = client.fetch_pages(_capture(body={}))[0]
    finally:
        client.close()

    assert envelope.is_success is False
    assert envelope.error_code == "PROVIDER_ERROR"
    assert envelope.error_message == "Lingxing provider reported failure"
    assert SYNTHETIC_TOKEN not in envelope.model_dump_json()
    assert SYNTHETIC_APP_ID not in envelope.model_dump_json()
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == []


@pytest.mark.parametrize(
    ("body", "params", "message"),
    [
        ({"unexpected": 1}, None, "endpoint contract"),
        ({}, {"access_token": "caller-supplied-fixture"}, "query parameters"),
        ({"offset": -1}, None, "pagination scope"),
        ({"length": 2}, None, "page size"),
    ],
)
def test_product_list_contract_rejects_before_token_and_transport(
    body: JsonValue,
    params: dict[str, str | int | float | bool | None] | None,
    message: str,
) -> None:
    calls = 0
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match=message):
            client.fetch_pages(_capture(body=body, params=params))
    finally:
        client.close()

    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []
