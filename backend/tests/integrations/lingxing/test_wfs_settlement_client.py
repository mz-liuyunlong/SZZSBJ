import json
from datetime import date

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import LingxingClientError, LingxingReadonlyClient

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"


class TokenProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_access_token(self) -> SecretStr:
        self.calls += 1
        return SecretStr("synthetic-access-value")

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr("synthetic-rotated-value")


def settings(*, enabled: bool = True) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_ENABLE_REAL_CALLS": enabled,
        }
    )


def succeeded(_: str, __: httpx.Response, payload: JsonValue) -> bool:
    return isinstance(payload, dict) and payload.get("code") == 0


def test_wfs_page_binds_exact_store_window_and_pagination() -> None:
    token = TokenProvider()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/basicOpen/multiplatform/profit/report/order"
        assert not request.url.query
        assert request.headers["Authorization"] == "synthetic-access-value"
        assert json.loads(request.content) == {
            "offset": 20,
            "length": 20,
            "sids": "110704872940532224",
            "platformCodeS": ["10008"],
            "transactionTypeS": [0],
            "currencyCode": "USD",
            "searchDateType": "2",
            "startDate": "2026-08-19",
            "endDate": "2026-10-17",
            "searchField": "msku",
            "searchValue": "SKU-A",
        }
        return httpx.Response(200, json={"code": 0, "data": {"list": [], "total": 0}})

    client = LingxingReadonlyClient(
        settings(),
        token_provider=token,
        success_evaluator=succeeded,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_wfs_settlement_page(
            store_id="110704872940532224",
            offset=20,
            length=20,
            page_no=2,
            start_date=date(2026, 8, 19),
            end_date=date(2026, 10, 17),
            source_account_ref="primary",
            run_id="run-fixture",
            work_item_id="work-fixture",
            msku="SKU-A",
        )
    finally:
        client.close()

    assert envelope.is_success is True
    assert calls == 1
    assert token.calls == 1
    assert "synthetic-access-value" not in envelope.model_dump_json()


def test_disabled_real_calls_reject_before_token_or_transport() -> None:
    token = TokenProvider()
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    client = LingxingReadonlyClient(
        settings(enabled=False),
        token_provider=token,
        success_evaluator=succeeded,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="disabled"):
            client.fetch_wfs_settlement_page(
                store_id="110704872940532224",
                offset=0,
                length=20,
                page_no=1,
                start_date=date(2026, 8, 19),
                end_date=date(2026, 10, 17),
                source_account_ref="primary",
                run_id="run-fixture",
                work_item_id="work-fixture",
            )
    finally:
        client.close()

    assert calls == 0
    assert token.calls == 0


@pytest.mark.parametrize(
    ("store_id", "length"),
    [("not-numeric", 20), ("110704872940532224", 21)],
)
def test_wfs_scope_and_page_size_fail_closed(store_id: str, length: int) -> None:
    token = TokenProvider()
    client = LingxingReadonlyClient(
        settings(),
        token_provider=token,
        success_evaluator=succeeded,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"code": 0})),
    )
    try:
        with pytest.raises(LingxingClientError):
            client.fetch_wfs_settlement_page(
                store_id=store_id,
                offset=0,
                length=length,
                page_no=1,
                start_date=date(2026, 8, 19),
                end_date=date(2026, 10, 17),
                source_account_ref="primary",
                run_id="run-fixture",
                work_item_id="work-fixture",
            )
    finally:
        client.close()

    assert token.calls == 0
