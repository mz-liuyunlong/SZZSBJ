import csv
import json
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import (
    _ENDPOINT_CONTRACTS,
    LingxingClientError,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.pmc_purchase_contracts import (
    PMC_PURCHASE_ENDPOINT_SPECS,
    PMC_PURCHASE_ENDPOINTS,
    PMC_PURCHASE_MAX_PAGE_SIZE,
    PMC_PURCHASE_MAX_WINDOW_DAYS,
    PMC_PURCHASE_SPECS_BY_INTERFACE_KEY,
    PURCHASE_ORDER_ENDPOINT,
    PURCHASE_PLAN_ENDPOINT,
    RECEIPT_ORDER_ENDPOINT,
    PmcPurchaseContractError,
    build_pmc_purchase_page_body,
    get_pmc_purchase_spec,
    pmc_purchase_response_items,
    pmc_purchase_response_succeeded,
    pmc_purchase_response_total,
    validate_pmc_purchase_window,
)

RUN_ID = UUID("00000000-0000-0000-0000-00000000a001")
SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
SYNTHETIC_APP_ID = "0123456789ABCDEF"
SYNTHETIC_ACCESS = "synthetic-access-fixture"
WINDOW_START = date(2026, 8, 1)
WINDOW_END = date(2026, 8, 31)
REGISTRY_CSV = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "integrations"
    / "lingxing"
    / "data"
    / "official_verified_interfaces.csv"
)


class FakeTokenProvider:
    def __init__(self) -> None:
        self.get_calls = 0

    def get_access_token(self) -> SecretStr:
        self.get_calls += 1
        return SecretStr(SYNTHETIC_ACCESS)

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr(SYNTHETIC_ACCESS)


def _settings(*, real_calls: bool) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": SYNTHETIC_APP_ID,
            "LINGXING_ENABLE_REAL_CALLS": real_calls,
        }
    )


def _registry_rows() -> dict[str, dict[str, str]]:
    with REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return {row["interface_id"]: row for row in csv.DictReader(handle)}


# --- spec table integrity -----------------------------------------------------------


def test_three_endpoints_are_registered_and_indexed() -> None:
    assert PMC_PURCHASE_ENDPOINTS == {
        PURCHASE_PLAN_ENDPOINT,
        PURCHASE_ORDER_ENDPOINT,
        RECEIPT_ORDER_ENDPOINT,
    }
    assert set(PMC_PURCHASE_ENDPOINT_SPECS) == PMC_PURCHASE_ENDPOINTS
    assert set(PMC_PURCHASE_SPECS_BY_INTERFACE_KEY) == {
        "purchasePlanList",
        "purchaseOrderList",
        "purchaseReceiptOrderList",
    }
    for spec in PMC_PURCHASE_ENDPOINT_SPECS.values():
        assert spec.object_type.startswith("pmc_purchase_")
        assert spec.max_page_size == PMC_PURCHASE_MAX_PAGE_SIZE == 500
        assert spec.required_body_fields <= spec.allowed_body_fields
        assert set(spec.date_range_fields) <= spec.allowed_body_fields


def test_specs_match_official_registry_rows() -> None:
    rows = _registry_rows()
    for spec in PMC_PURCHASE_ENDPOINT_SPECS.values():
        row = rows[spec.registry_interface_id]
        assert row["api_path"] == spec.api_path
        assert row["http_method"] == "POST"
        assert row["is_read"] == "是"
        assert row["is_write"] == "否"
        assert row["has_side_effect"] == "否"
        assert row["pagination_method"] == "offset/length"
        assert int(row["max_page_size_or_length"]) == spec.max_page_size
        registry_fields = {
            field.strip() for field in row["request_fields"].split(",") if field.strip()
        }
        assert spec.allowed_body_fields == registry_fields
        assert (row["returns_total"] == "是") is spec.returns_total


def test_client_endpoint_contracts_are_derived_from_specs() -> None:
    for api_path, spec in PMC_PURCHASE_ENDPOINT_SPECS.items():
        contract = _ENDPOINT_CONTRACTS[api_path]
        assert contract.method == "POST"
        assert contract.require_json_body is True
        assert contract.allow_query_parameters is False
        assert contract.allowed_body_fields == spec.allowed_body_fields
        assert contract.required_body_fields == spec.required_body_fields
        assert contract.page_size_field == "length"
        assert contract.offset_field == "offset"
        assert contract.auth_strategy == "query_sign"


# --- body builder --------------------------------------------------------------------


def test_builds_minimal_window_body() -> None:
    body = build_pmc_purchase_page_body(
        PURCHASE_ORDER_ENDPOINT,
        offset=500,
        length=500,
        start_date=WINDOW_START,
        end_date=WINDOW_END,
    )
    assert body == {
        "offset": 500,
        "length": 500,
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
    }


def test_builds_body_with_dimension_and_extra_filters() -> None:
    body = build_pmc_purchase_page_body(
        RECEIPT_ORDER_ENDPOINT,
        offset=0,
        length=200,
        start_date=WINDOW_START,
        end_date=WINDOW_END,
        date_dimension="receive_time",
        extra={"wid": 16168, "status": [3]},
    )
    assert body == {
        "offset": 0,
        "length": 200,
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "date_type": "receive_time",
        "wid": 16168,
        "status": [3],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"offset": -1, "length": 10}, "offset is invalid"),
        ({"offset": 0, "length": 0}, "page size is invalid"),
        ({"offset": 0, "length": 501}, "page size is invalid"),
        ({"offset": True, "length": 10}, "pagination values are invalid"),
        ({"offset": 0, "length": 10, "extra": {"offset": 5}}, "override window fields"),
        ({"offset": 0, "length": 10, "extra": {"foo": 1}}, "outside the contract"),
        ({"offset": 0, "length": 10, "extra": [1]}, "must be an object"),
    ],
)
def test_builder_rejects_contract_violations(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(PmcPurchaseContractError, match=message):
        build_pmc_purchase_page_body(
            PURCHASE_PLAN_ENDPOINT,
            start_date=WINDOW_START,
            end_date=WINDOW_END,
            **kwargs,  # type: ignore[arg-type]
        )


def test_builder_rejects_unknown_endpoint_and_missing_dimension() -> None:
    with pytest.raises(PmcPurchaseContractError, match="not registered"):
        get_pmc_purchase_spec("/erp/sc/routing/data/local_inventory/productList")
    spec = get_pmc_purchase_spec(PURCHASE_PLAN_ENDPOINT)
    assert spec.date_dimension_field == "search_field_time"


def test_window_bounds() -> None:
    max_end = WINDOW_START + timedelta(days=PMC_PURCHASE_MAX_WINDOW_DAYS - 1)
    validate_pmc_purchase_window(WINDOW_START, WINDOW_START)
    validate_pmc_purchase_window(WINDOW_START, max_end)
    with pytest.raises(PmcPurchaseContractError, match="exceeds"):
        validate_pmc_purchase_window(WINDOW_START, max_end + timedelta(days=1))
    with pytest.raises(PmcPurchaseContractError, match="precedes"):
        validate_pmc_purchase_window(WINDOW_END, WINDOW_START)


# --- response shape --------------------------------------------------------------------


def test_response_accessors_follow_contract_shapes() -> None:
    flat = {"code": 0, "data": [{"order_sn": "PO1"}], "total": 7}
    nested = {"code": 0, "data": {"list": [{"order_sn": "RC1"}], "total": 3}}
    assert pmc_purchase_response_items(PURCHASE_PLAN_ENDPOINT, flat) == [{"order_sn": "PO1"}]
    assert pmc_purchase_response_items(RECEIPT_ORDER_ENDPOINT, nested) == [{"order_sn": "RC1"}]
    assert pmc_purchase_response_items(RECEIPT_ORDER_ENDPOINT, flat) is None
    assert pmc_purchase_response_total(PURCHASE_PLAN_ENDPOINT, flat) == 7
    assert pmc_purchase_response_total(RECEIPT_ORDER_ENDPOINT, nested) == 3
    # purchaseOrderList never publishes a total, even if the provider adds one later.
    assert pmc_purchase_response_total(PURCHASE_ORDER_ENDPOINT, flat) is None
    assert pmc_purchase_response_succeeded(PURCHASE_ORDER_ENDPOINT, None, flat) is True
    assert pmc_purchase_response_succeeded(RECEIPT_ORDER_ENDPOINT, None, nested) is True
    assert pmc_purchase_response_succeeded(RECEIPT_ORDER_ENDPOINT, None, flat) is False
    failed = {"code": 1, "data": []}
    assert pmc_purchase_response_succeeded(PURCHASE_PLAN_ENDPOINT, None, failed) is False
    assert (
        pmc_purchase_response_succeeded(
            "/erp/sc/routing/data/local_inventory/productList", None, flat
        )
        is False
    )


# --- transport ------------------------------------------------------------------------


def test_transport_sends_only_contract_fields_and_keeps_auth_out_of_envelope() -> None:
    token_provider = FakeTokenProvider()
    captured: dict[str, object] = {}

    def transport(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["auth"] = {
            key: value
            for key, value in request.url.params.items()
            if key in {"access_token", "app_key", "sign"}
        }
        return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

    client = LingxingReadonlyClient(
        _settings(real_calls=True),
        token_provider=token_provider,
        success_evaluator=pmc_purchase_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    try:
        result = client.fetch_pmc_purchase_page(
            api_path=PURCHASE_PLAN_ENDPOINT,
            offset=0,
            length=500,
            page_no=1,
            start_date=WINDOW_START,
            end_date=WINDOW_END,
            date_dimension="create_time",
            source_account_ref="primary",
            run_id=str(RUN_ID),
            work_item_id=str(uuid4()),
        )
    finally:
        client.close()

    assert captured["path"] == PURCHASE_PLAN_ENDPOINT
    assert captured["body"] == {
        "offset": 0,
        "length": 500,
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "search_field_time": "create_time",
    }
    assert token_provider.get_calls == 1
    assert result.is_success is True
    serialized = result.model_dump_json()
    auth = captured["auth"]
    assert isinstance(auth, dict) and set(auth) == {"access_token", "app_key", "sign"}
    assert SYNTHETIC_ACCESS not in serialized
    assert SYNTHETIC_APP_ID not in serialized
    assert auth["sign"] not in serialized


def test_transport_is_single_attempt_and_refuses_when_calls_disabled() -> None:
    calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        del request
        return httpx.Response(500, json={"code": 500, "message": "boom"})

    client = LingxingReadonlyClient(
        _settings(real_calls=True),
        token_provider=FakeTokenProvider(),
        success_evaluator=pmc_purchase_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    try:
        result = client.fetch_pmc_purchase_page(
            api_path=PURCHASE_ORDER_ENDPOINT,
            offset=0,
            length=500,
            page_no=1,
            start_date=WINDOW_START,
            end_date=WINDOW_END,
            source_account_ref="primary",
            run_id=str(RUN_ID),
            work_item_id=str(uuid4()),
        )
    finally:
        client.close()
    assert result.is_success is False
    assert calls == 1

    disabled = LingxingReadonlyClient(
        _settings(real_calls=False),
        token_provider=FakeTokenProvider(),
        success_evaluator=pmc_purchase_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    try:
        with pytest.raises(LingxingClientError, match="disabled"):
            disabled.fetch_pmc_purchase_page(
                api_path=PURCHASE_ORDER_ENDPOINT,
                offset=0,
                length=500,
                page_no=1,
                start_date=WINDOW_START,
                end_date=WINDOW_END,
                source_account_ref="primary",
                run_id=str(RUN_ID),
                work_item_id=str(uuid4()),
            )
    finally:
        disabled.close()
    assert calls == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_path": "/erp/sc/routing/data/local_inventory/productList"},
        {"length": 501},
        {"extra": {"sids": [1], "offset": 9}},
        {"source_account_ref": " primary"},
        {"end_date": date(2026, 12, 31)},
    ],
)
def test_client_rejects_contract_violations_before_network(kwargs: dict[str, object]) -> None:
    calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        del request
        return httpx.Response(200, json={"code": 0, "data": []})

    client = LingxingReadonlyClient(
        _settings(real_calls=True),
        token_provider=FakeTokenProvider(),
        success_evaluator=pmc_purchase_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    params: dict[str, object] = {
        "api_path": PURCHASE_PLAN_ENDPOINT,
        "offset": 0,
        "length": 500,
        "page_no": 1,
        "start_date": WINDOW_START,
        "end_date": WINDOW_END,
        "source_account_ref": "primary",
        "run_id": str(RUN_ID),
        "work_item_id": str(uuid4()),
    }
    params.update(kwargs)
    try:
        with pytest.raises(LingxingClientError):
            client.fetch_pmc_purchase_page(**params)  # type: ignore[arg-type]
    finally:
        client.close()
    assert calls == 0
