"""结算利润 PR-2 三个领星接口（发货单 / 明细 / 出库单）的出站合同。全部合成数据，不连网络。"""

import json
from datetime import date
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import (
    _ENDPOINT_CONTRACTS,
    LingxingClientError,
    LingxingReadonlyClient,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
LIST_ENDPOINT = "/basicOpen/multiplatform/query/shippingList"
DETAIL_ENDPOINT = "/basicOpen/multiplatform/query/shippingDetail"
WMS_ENDPOINT = "/erp/sc/routing/wms/order/wmsOrderList"
STORE = "990000000000000001"
RUN = "00000000-0000-0000-0000-000000000001"
WORK = "00000000-0000-0000-0000-000000000002"


class _FakeTokenProvider:
    def get_access_token(self) -> SecretStr:
        return SecretStr("access-token-fixture")

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr("rotated-access-token-fixture")


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": "0123456789ABCDEF",
            "LINGXING_ENABLE_REAL_CALLS": True,
        }
    )


def _is_success(endpoint: str, response: httpx.Response, payload: object) -> bool:
    del endpoint, response
    return isinstance(payload, dict) and payload.get("code") == 0


def _client(
    expected_path: str, expected_body: dict[str, Any]
) -> tuple[LingxingReadonlyClient, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.method == "POST"
        assert request.url.path == expected_path
        assert "Authorization" not in request.headers
        assert set(request.url.params) == {"access_token", "app_key", "timestamp", "sign"}
        assert json.loads(request.content) == expected_body
        return httpx.Response(200, json={"code": 0, "data": {"list": [], "total": "0"}})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=_FakeTokenProvider(),
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    return client, calls


@pytest.mark.parametrize("endpoint", [LIST_ENDPOINT, DETAIL_ENDPOINT, WMS_ENDPOINT])
def test_contracts_use_query_sign_and_post(endpoint: str) -> None:
    contract = _ENDPOINT_CONTRACTS[endpoint]
    assert contract.auth_strategy == "query_sign"
    assert contract.method == "POST"
    assert contract.allow_query_parameters is False


def test_shipping_list_page_only_walmart_one_store_by_delivery_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.integrations.lingxing.query_sign.time", lambda: 1_712_345_678.9)
    client, calls = _client(
        LIST_ENDPOINT,
        {
            "platformCodes": ["10008"],
            "storeIds": [STORE],
            "timeField": 2,
            "startTime": "2026-08-01",
            "endTime": "2026-10-31",
            "offset": 100,
            "length": 100,
        },
    )
    try:
        envelope = client.fetch_fin_shipping_list_page(
            store_id=STORE,
            offset=100,
            length=100,
            page_no=2,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 10, 31),
            source_account_ref="primary",
            run_id=RUN,
            work_item_id=WORK,
        )
        with pytest.raises(LingxingClientError):
            client.fetch_fin_shipping_list_page(
                store_id=STORE,
                offset=0,
                length=101,
                page_no=1,
                start_date=date(2026, 8, 1),
                end_date=date(2026, 10, 31),
                source_account_ref="primary",
                run_id=RUN,
                work_item_id=WORK,
            )
    finally:
        client.close()
    assert calls == [1]
    assert envelope.is_success is True
    assert "access-token-fixture" not in envelope.model_dump_json()


def test_shipping_detail_sends_one_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.integrations.lingxing.query_sign.time", lambda: 1_712_345_678.9)
    client, calls = _client(DETAIL_ENDPOINT, {"shippingListCode": "SP2026T0001"})
    try:
        client.fetch_fin_shipping_detail(
            store_id=STORE,
            shipping_list_code="SP2026T0001",
            source_account_ref="primary",
            run_id=RUN,
            work_item_id=WORK,
        )
        with pytest.raises(LingxingClientError):
            client.fetch_fin_shipping_detail(
                store_id=STORE,
                shipping_list_code=" ",
                source_account_ref="primary",
                run_id=RUN,
                work_item_id=WORK,
            )
    finally:
        client.close()
    assert calls == [1]


def test_wms_order_page_uses_update_time_and_page_number(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.integrations.lingxing.query_sign.time", lambda: 1_712_345_678.9)
    client, calls = _client(
        WMS_ENDPOINT,
        {
            "sid_arr": [STORE],
            "time_type": "update_at",
            "start_date": "2026-08-01",
            "end_date": "2026-10-31",
            "page": 3,
            "page_size": 200,
        },
    )
    try:
        client.fetch_fin_wms_order_page(
            store_id=STORE,
            page_no=3,
            page_size=200,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 10, 31),
            source_account_ref="primary",
            run_id=RUN,
            work_item_id=WORK,
        )
        with pytest.raises(LingxingClientError):
            client.fetch_fin_wms_order_page(
                store_id="not-a-store",
                page_no=1,
                page_size=200,
                start_date=date(2026, 8, 1),
                end_date=date(2026, 10, 31),
                source_account_ref="primary",
                run_id=RUN,
                work_item_id=WORK,
            )
    finally:
        client.close()
    assert calls == [1]
