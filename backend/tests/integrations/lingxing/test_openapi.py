import pytest
from pydantic import JsonValue

from app.integrations.lingxing.openapi import (
    EXPECTED_INTERFACE_COUNT,
    LingxingOpenApiClient,
    LingxingOpenApiDryRun,
    LingxingOpenApiError,
    LingxingOpenApiRequest,
    lingxing_openapi_registry,
)

BATCH_PRODUCT_INFO_ID = "LX-BB8D0DF598AF"
SIDE_EFFECT_INTERFACE_ID = "LX-633648A48963"


def test_registry_contains_all_official_non_page_interfaces() -> None:
    registry = lingxing_openapi_registry()

    assert len(registry) == EXPECTED_INTERFACE_COUNT == 329
    assert len({(item.method, item.api_path) for item in registry.values()}) == 329
    assert {item.verification_status for item in registry.values()} == {"OFFICIAL_VERIFIED"}
    assert sum(item.requires_owner_authorization for item in registry.values()) == 133


def test_product_info_contract_builds_only_verified_request_fields() -> None:
    client = LingxingOpenApiClient()
    contract = client.registry[BATCH_PRODUCT_INFO_ID]

    assert contract.request_param_count == 3
    assert contract.response_field_count == 124
    assert contract.request_fields == ("productIds", "sku_identifiers", "skus")

    request = client.build_request(
        BATCH_PRODUCT_INFO_ID,
        {"productIds": ["synthetic-id"]},
    )

    assert request.api_path == "/erp/sc/routing/data/local_inventory/batchGetProductInfo"
    assert request.method == "POST"
    assert request.parameters == {"productIds": ["synthetic-id"]}

    with pytest.raises(LingxingOpenApiError) as exc_info:
        client.build_request(BATCH_PRODUCT_INFO_ID, {"unverified_field": "sensitive-value"})

    assert exc_info.value.code == "CONTRACT_FIELD_MISMATCH"
    assert "unverified_field" not in str(exc_info.value)
    assert "sensitive-value" not in str(exc_info.value)


def test_all_callable_stubs_are_dry_run_and_default_deny() -> None:
    client = LingxingOpenApiClient()
    stubs = client.stubs()

    assert len(stubs) == 329
    for stub in stubs:
        dry_run = stub()
        assert isinstance(dry_run, LingxingOpenApiDryRun)
        assert dry_run.outbound_attempted is False
        with pytest.raises(LingxingOpenApiError) as exc_info:
            stub(dry_run=False)
        assert exc_info.value.code == "LINGXING_OPENAPI_OUTBOUND_NOT_AUTHORIZED"


def test_request_builder_covers_every_registered_interface() -> None:
    client = LingxingOpenApiClient()

    for contract in client.registry.values():
        parameters = {field_name: None for field_name in contract.request_fields}
        request = client.build_request(contract.interface_id, parameters)
        assert request.interface_id == contract.interface_id
        assert request.method == contract.method
        assert request.api_path == contract.api_path
        assert tuple(request.parameters) == contract.request_fields


def test_explicit_fake_executor_can_run_a_read_only_stub_without_network() -> None:
    calls: list[LingxingOpenApiRequest] = []

    def fake_executor(request: LingxingOpenApiRequest) -> JsonValue:
        calls.append(request)
        return {"code": 0, "data": []}

    client = LingxingOpenApiClient(
        executor=fake_executor,
        enabled_interface_ids=frozenset({BATCH_PRODUCT_INFO_ID}),
    )

    result = client.stub(BATCH_PRODUCT_INFO_ID)({"productIds": ["synthetic-id"]}, dry_run=False)

    assert result == {"code": 0, "data": []}
    assert len(calls) == 1
    assert "synthetic-id" not in repr(calls[0])


def test_side_effect_stub_requires_separate_owner_authorization() -> None:
    calls = 0
    contract = lingxing_openapi_registry()[SIDE_EFFECT_INTERFACE_ID]
    assert contract.is_read is False
    assert contract.requires_owner_authorization is True

    def fake_executor(request: LingxingOpenApiRequest) -> JsonValue:
        nonlocal calls
        del request
        calls += 1
        return {"code": 0}

    client = LingxingOpenApiClient(
        executor=fake_executor,
        enabled_interface_ids=frozenset({SIDE_EFFECT_INTERFACE_ID}),
    )

    with pytest.raises(LingxingOpenApiError) as exc_info:
        client.stub(SIDE_EFFECT_INTERFACE_ID)(dry_run=False)

    assert exc_info.value.code == "LINGXING_OPENAPI_OWNER_AUTHORIZATION_REQUIRED"
    assert calls == 0

    owner_authorized = LingxingOpenApiClient(
        executor=fake_executor,
        enabled_interface_ids=frozenset({SIDE_EFFECT_INTERFACE_ID}),
        owner_authorized_interface_ids=frozenset({SIDE_EFFECT_INTERFACE_ID}),
    )
    assert owner_authorized.stub(SIDE_EFFECT_INTERFACE_ID)(dry_run=False) == {"code": 0}
    assert calls == 1


def test_unknown_interface_fails_closed() -> None:
    client = LingxingOpenApiClient()

    with pytest.raises(LingxingOpenApiError) as exc_info:
        client.stub("LX-NOT-REGISTERED")

    assert exc_info.value.code == "LINGXING_OPENAPI_INTERFACE_UNKNOWN"
