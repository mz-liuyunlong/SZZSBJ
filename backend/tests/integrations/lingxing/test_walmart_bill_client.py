"""沃尔玛账单（statement/list）出站鉴权。

领星这个接口只认 query 签名，不能把 token 放在 Authorization 头里。
线上首次回填全部被领星拒绝（code 3001025，要求 Bearer 凭据），
原因是合同漏写 auth_strategy，落到了默认的 Authorization 头。
全部合成数据，不连网络。
"""

import json
from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import _ENDPOINT_CONTRACTS, LingxingReadonlyClient

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
BILL_ENDPOINT = "/basicOpen/multiplatformFinance/walmart/bill/statement/list"
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


def _is_success(endpoint: str, response: httpx.Response, payload: object) -> bool:
    del endpoint, response
    return isinstance(payload, dict) and payload.get("code") == 0


def test_walmart_bill_contract_uses_query_sign() -> None:
    assert _ENDPOINT_CONTRACTS[BILL_ENDPOINT].auth_strategy == "query_sign"


def test_walmart_bill_page_signs_in_query_and_keeps_paging_in_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.integrations.lingxing.query_sign.time", lambda: 1_712_345_678.9)
    calls = 0
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == BILL_ENDPOINT
        assert "Authorization" not in request.headers
        assert set(request.url.params) == {"access_token", "app_key", "timestamp", "sign"}
        assert request.url.params["app_key"] == SYNTHETIC_APP_ID
        assert json.loads(request.content) == {
            "offset": 0,
            "length": 20,
            "sids": ["900000000000000001"],
            "startDate": "2026-10-01",
            "endDate": "2026-10-31",
        }
        return httpx.Response(200, json={"code": 0, "data": {"list": [], "total": 0}})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_walmart_bill_page(
            store_id="900000000000000001",
            offset=0,
            length=20,
            page_no=1,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31),
            source_account_ref="primary",
            run_id="00000000-0000-0000-0000-000000000001",
            work_item_id="00000000-0000-0000-0000-000000000002",
        )
    finally:
        client.close()

    serialized = envelope.model_dump_json()
    assert calls == 1
    assert SYNTHETIC_TOKEN not in serialized
    assert SYNTHETIC_APP_ID not in serialized
    assert token_provider.recover_calls == []
