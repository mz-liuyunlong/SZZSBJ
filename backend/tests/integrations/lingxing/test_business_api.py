import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.business_api import LingxingBusinessApiExecutor
from app.integrations.lingxing.openapi import LingxingOpenApiError, LingxingOpenApiRequest

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
SYNTHETIC_APP_ID = "0123456789ABCDEF"
SYNTHETIC_TOKEN = "credential-fixture"


class _FakeTokenProvider:
    def __init__(self) -> None:
        self.get_calls = 0
        self.recover_calls: list[int | str] = []

    def get_access_token(self) -> SecretStr:
        self.get_calls += 1
        return SecretStr(SYNTHETIC_TOKEN)

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        self.recover_calls.append(provider_code)
        return SecretStr("rotated-credential-fixture")


def _settings(*, enabled: bool = True) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": SYNTHETIC_APP_ID,
            "LINGXING_ENABLE_REAL_CALLS": enabled,
        }
    )


def test_post_business_request_query_signs_auth_and_keeps_business_json_in_body() -> None:
    calls = 0
    token_provider = _FakeTokenProvider()
    parameters = {
        "platform_code": [10008],
        "paging": True,
        "offset": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == "/pb/mp/shop/v2/getSellerList"
        assert set(request.url.params) == {
            "access_token",
            "app_key",
            "timestamp",
            "sign",
        }
        assert "Authorization" not in request.headers
        assert json.loads(request.content) == parameters
        return httpx.Response(200, json={"code": 0, "data": {"list": []}})

    executor = LingxingBusinessApiExecutor(
        _settings(),
        token_provider=token_provider,
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = executor(
            LingxingOpenApiRequest(
                interface_id="LX-F8354824E040",
                method="POST",
                api_path="/pb/mp/shop/v2/getSellerList",
                parameters=parameters,
            )
        )
    finally:
        executor.close()

    assert payload == {"code": 0, "data": {"list": []}}
    assert calls == 1
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == []


def test_get_business_request_sends_business_and_auth_params_in_query() -> None:
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/erp/sc/v2/cs/reviewReport/lists"
        assert set(request.url.params) == {
            "access_token",
            "app_key",
            "timestamp",
            "sign",
            "start_date",
            "end_date",
            "sid",
        }
        assert request.url.params["start_date"] == "2026-09-01"
        assert request.url.params["end_date"] == "2026-09-02"
        assert request.url.params["sid"] == "[1,2]"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"code": 0, "data": []})

    executor = LingxingBusinessApiExecutor(
        _settings(),
        token_provider=token_provider,
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = executor(
            LingxingOpenApiRequest(
                interface_id="LX-2C7CF1CE8AAE",
                method="GET",
                api_path="/erp/sc/v2/cs/reviewReport/lists",
                parameters={
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-02",
                    "sid": [1, 2],
                },
            )
        )
    finally:
        executor.close()

    assert payload == {"code": 0, "data": []}


@pytest.mark.parametrize(
    ("interface_id", "api_path"),
    [
        ("LX-ECC5B6E072BC", "/basicOpen/outboundOrder/outbound/delete"),
        ("LX-50E3A9271BE9", "/basicOpen/storageAllocationList/delete"),
        ("LX-9AE1466FB085", "/basicOpen/overSeaWarehouse/stockOrder/delete"),
        ("LX-1E89A7A2DA3C", "/bd/fee/management/open/feeManagement/otherFee/delete"),
        ("LX-2AD144D844C7", "/bd/sp/api/open/settlement/export/url/get"),
    ],
)
def test_owner_verified_method_corrections_execute_as_post(
    interface_id: str,
    api_path: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == api_path
        return httpx.Response(200, json={"code": 0})

    executor = LingxingBusinessApiExecutor(
        _settings(),
        token_provider=_FakeTokenProvider(),
        transport=httpx.MockTransport(handler),
    )
    try:
        result = executor(
            LingxingOpenApiRequest(
                interface_id=interface_id,
                method="DELETE" if interface_id != "LX-2AD144D844C7" else "GET",
                api_path=api_path,
                parameters={},
            )
        )
    finally:
        executor.close()

    assert result == {"code": 0}
    assert calls == 1


def test_access_token_provider_error_recovers_once_without_leaking_values() -> None:
    calls = 0
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        expected_token = SYNTHETIC_TOKEN if calls == 1 else "rotated-credential-fixture"
        assert request.url.params["access_token"] == expected_token
        if calls == 1:
            return httpx.Response(200, json={"code": 2001003})
        return httpx.Response(200, json={"code": 0})

    executor = LingxingBusinessApiExecutor(
        _settings(),
        token_provider=token_provider,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = executor(
            LingxingOpenApiRequest(
                interface_id="LX-F8354824E040",
                method="POST",
                api_path="/pb/mp/shop/v2/getSellerList",
                parameters={"offset": 0, "length": 3},
            )
        )
    finally:
        executor.close()

    assert result == {"code": 0}
    assert calls == 2
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == [2001003]


def test_business_executor_remains_fail_closed_when_real_calls_are_disabled() -> None:
    executor = LingxingBusinessApiExecutor(
        _settings(enabled=False),
        token_provider=_FakeTokenProvider(),
        transport=httpx.MockTransport(lambda _: pytest.fail("transport must not run")),
    )
    try:
        with pytest.raises(LingxingOpenApiError) as exc_info:
            executor(
                LingxingOpenApiRequest(
                    interface_id="LX-F8354824E040",
                    method="POST",
                    api_path="/pb/mp/shop/v2/getSellerList",
                    parameters={},
                )
            )
    finally:
        executor.close()

    assert exc_info.value.code == "LINGXING_OPENAPI_OUTBOUND_NOT_AUTHORIZED"
