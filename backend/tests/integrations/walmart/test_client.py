"""In-memory fake transport; never calls Walmart/SSM/SSH."""

import pytest

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.planner import WalmartPlanError


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def execute(
        self, *, store_code: str, request: object, approval_ref: str | None
    ) -> WalmartResult:
        self.calls.append((store_code, request.key, approval_ref))
        return WalmartResult(status_code=200, data={"mock": True})


def registry() -> ContractRegistry:
    return ContractRegistry.from_openapi(
        {
            "openapi": "3.0.3",
            "paths": {
                "/v3/items": {
                    "get": {"operationId": "listItems"},
                    "post": {
                        "operationId": "submitItem",
                        "requestBody": {"content": {"application/json": {}}},
                    },
                }
            },
        },
        approved_keys=frozenset({"listItems", "submitItem"}),
    )


def test_sdk_denies_without_live_gateway() -> None:
    client = WalmartClient(registry(), allowed_stores=frozenset({"HK2615"}))
    with pytest.raises(WalmartPlanError, match="WALMART_PROTECTED_GATEWAY_UNAVAILABLE"):
        client.call("HK2615", "listItems")


def test_mock_sdk_read() -> None:
    fake = FakeGateway()
    client = WalmartClient(registry(), gateway=fake, allowed_stores=frozenset({"HK2615"}))
    assert client.call("HK2615", "listItems").data == {"mock": True}
    assert fake.calls == [("HK2615", "listItems", None)]


def test_write_needs_scope_and_approval() -> None:
    fake = FakeGateway()
    client = WalmartClient(registry(), gateway=fake, allowed_stores=frozenset({"HK2615"}))
    with pytest.raises(ValueError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        client.call("HK2615", "submitItem", body={"sku": "fictional"})
    with pytest.raises(WalmartPlanError, match="WALMART_WRITE_APPROVAL_REQUIRED"):
        client.call("HK2615", "submitItem", body={"sku": "fictional"}, allow_writes=True)
    assert fake.calls == []
    result = client.call(
        "HK2615",
        "submitItem",
        body={"sku": "fictional"},
        allow_writes=True,
        approval_ref="offline-mock-only",
    )
    assert result.status_code == 200
    assert len(fake.calls) == 1


def test_cn2502_is_not_disabled_but_has_no_egress() -> None:
    client = WalmartClient(registry(), allowed_stores=frozenset({"CN2502"}))
    with pytest.raises(WalmartPlanError, match="WALMART_EXIT_UNAVAILABLE"):
        client.call("CN2502", "listItems")
