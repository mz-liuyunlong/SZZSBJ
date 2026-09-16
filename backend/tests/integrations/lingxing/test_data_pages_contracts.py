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
from app.modules.integration_sync.parsers.lingxing_data_pages import (
    DATA_PAGES_PARSER_SPECS,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"

SELLER_ENDPOINT: LingxingEndpoint = "/pb/mp/shop/v2/getSellerList"
WALMART_LISTING_ENDPOINT: LingxingEndpoint = "/basicOpen/multiplatform/walmart/list"
SALE_STAT_ENDPOINT: LingxingEndpoint = "/basicOpen/platformStatisticsV2/saleStat/pageList"
ORDER_ENDPOINT: LingxingEndpoint = "/pb/mp/order/v2/list"
RETURN_ENDPOINT: LingxingEndpoint = "/basicOpen/openapi/multiplatform/walmart/returnOrder/list"
ADVERTISER_ENDPOINT: LingxingEndpoint = "/basicOpen/adReport/advertiser/list"
AD_ITEM_SP_ENDPOINT: LingxingEndpoint = "/basicOpen/multiplatform/ads/reportAdItemSpList"


class _FakeTokenProvider:
    def get_access_token(self) -> SecretStr:
        return SecretStr("credential-fixture")

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr("rotated-credential-fixture")


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_ENABLE_REAL_CALLS": True,
        }
    )


def _capture(
    endpoint: LingxingEndpoint,
    body: JsonValue,
    *,
    page_size: int = 3,
) -> LingxingCaptureRequest:
    return LingxingCaptureRequest(
        api_path=endpoint,
        pages=(
            LingxingPageRequest(
                page_no=1,
                page_size=page_size,
                body=body,
            ),
        ),
        store_ids=("scope-fixture", "secondary-scope"),
        object_type="data_pages_contract_fixture",
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


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        (
            SELLER_ENDPOINT,
            {"offset": 0, "length": 3, "platform_code": [10008]},
        ),
        (
            WALMART_LISTING_ENDPOINT,
            {"offset": 0, "length": 3},
        ),
        (
            SALE_STAT_ENDPOINT,
            {"page": 1, "length": 3, "data_type": 1, "result_type": 1},
        ),
        (
            ORDER_ENDPOINT,
            {
                "date_type": "global_purchase_time",
                "offset": 0,
                "length": 3,
                "platform_code": [10008],
                "store_id": "scope-fixture",
            },
        ),
        (
            RETURN_ENDPOINT,
            {
                "dateType": "1",
                "pageNum": 1,
                "pageSize": 3,
                "returnTypeList": ["REFUND"],
            },
        ),
        (
            ADVERTISER_ENDPOINT,
            {"paging": True, "page": 1, "limit": 3},
        ),
        (
            AD_ITEM_SP_ENDPOINT,
            {
                "advertiserIds": ["advertiser-fixture"],
                "campaignType": ["sponsoredProducts-manual", "sponsoredProducts-auto"],
                "startDate": "2026-09-01",
                "endDate": "2026-09-02",
                "pageNum": 1,
                "pageSize": 3,
            },
        ),
    ],
)
def test_data_pages_contracts_bind_safe_outbound_requests(
    endpoint: LingxingEndpoint,
    body: JsonValue,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == endpoint
        assert not request.url.query
        assert request.headers["Authorization"] == "credential-fixture"
        assert json.loads(request.content) == body
        assert b"credential-fixture" not in request.content
        return httpx.Response(200, json={"code": 0, "data": []})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=_FakeTokenProvider(),
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture(endpoint, body))[0]
    finally:
        client.close()

    assert envelope.is_success is True
    assert calls == 1
    assert "credential-fixture" not in envelope.model_dump_json()


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        (SELLER_ENDPOINT, {"offset": 0, "length": 3, "Authorization": "secret"}),
        (WALMART_LISTING_ENDPOINT, {"offset": 0, "length": 3, "storeIds": ["x"]}),
        (SALE_STAT_ENDPOINT, {"page": 1, "length": 3, "offset": 0}),
        (ORDER_ENDPOINT, {"date_type": "global_purchase_time", "page": 1, "length": 3}),
        (RETURN_ENDPOINT, {"dateType": "1", "page": 1, "pageSize": 3}),
        (ADVERTISER_ENDPOINT, {"paging": True, "page": 1, "limit": 3, "token": "x"}),
        (
            AD_ITEM_SP_ENDPOINT,
            {
                "advertiserIds": ["advertiser-fixture"],
                "campaignType": ["sponsoredProducts-manual"],
                "startDate": "2026-09-01",
                "endDate": "2026-09-02",
                "pageNum": 1,
                "pageSize": 3,
                "access_token": "x",
            },
        ),
    ],
)
def test_data_pages_contracts_reject_unapproved_body_fields(
    endpoint: LingxingEndpoint,
    body: JsonValue,
) -> None:
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=_FakeTokenProvider(),
        success_evaluator=_is_success,
        transport=httpx.MockTransport(lambda _: pytest.fail("transport must not run")),
    )
    try:
        with pytest.raises(LingxingClientError, match="endpoint contract"):
            client.fetch_pages(_capture(endpoint, body))
    finally:
        client.close()


def test_data_pages_parser_specs_cover_the_approved_endpoint_set() -> None:
    assert {spec.api_path for spec in DATA_PAGES_PARSER_SPECS.values()} == {
        SELLER_ENDPOINT,
        WALMART_LISTING_ENDPOINT,
        SALE_STAT_ENDPOINT,
        ORDER_ENDPOINT,
        RETURN_ENDPOINT,
        ADVERTISER_ENDPOINT,
        AD_ITEM_SP_ENDPOINT,
    }


def test_parser_specs_keep_order_and_refund_lineage_explicit() -> None:
    order_spec = DATA_PAGES_PARSER_SPECS["order_v2_list"]
    refund_spec = DATA_PAGES_PARSER_SPECS["walmart_return_order_list"]

    assert ("source_account_ref", "global_order_no", "source_line_hash") in (
        order_spec.unique_key_candidates
    )
    assert ("source_account_ref", "return_order_id", "source_line_hash") in (
        refund_spec.unique_key_candidates
    )
    assert any("return_line_id is not documented" in rule for rule in refund_spec.skip_rules)


def test_sale_stat_spec_warns_against_double_counting_volume_total() -> None:
    sale_spec = DATA_PAGES_PARSER_SPECS["sale_stat_page_list"]
    rules_text = " ".join(sale_spec.skip_rules)

    assert "date_collect" in rules_text
    assert "volumeTotal must not be double counted" in rules_text
    assert "allocation_status=needs_owner_decision" in rules_text


def test_parser_specs_do_not_embed_secrets_or_raw_payloads() -> None:
    serialized = repr(DATA_PAGES_PARSER_SPECS).lower()

    assert "access_token" not in serialized
    assert "authorization" not in serialized
    assert "appsecret" not in serialized
    assert "raw payload" not in serialized
