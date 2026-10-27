"""Cloud executor tests: independent authorization, no external I/O."""

from __future__ import annotations

from typing import Any

import pytest

from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contracts import ContractRegistry


class FakePolicy:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, str, bool, str | None]] = []

    def authorize(
        self, *, store_code: str, operation_key: str, is_write: bool, approval_ref: str | None
    ) -> bool:
        self.calls.append((store_code, operation_key, is_write, approval_ref))
        return self.allow


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def execute(self, *, store_code: str, request: object) -> tuple[int, Any]:
        self.calls.append((store_code, request))
        return 200, {"data": [{"sku": "synthetic"}]}


def registry() -> ContractRegistry:
    return ContractRegistry.from_openapi(
        {
            "openapi": "3.0.3",
            "paths": {
                "/v3/items": {
                    "get": {"operationId": "listItems"},
                    "post": {
                        "operationId": "updateItem",
                        "requestBody": {"content": {"application/json": {}}},
                    },
                }
            },
        },
        approved_keys=frozenset({"listItems", "updateItem"}),
    )


def event(*, store: str = "HK2615", operation: str = "listItems") -> dict[str, Any]:
    write = operation == "updateItem"
    return {
        "version": 1,
        "operation": "marketplace_call",
        "store_code": store,
        "api_key": operation,
        "method": "POST" if write else "GET",
        "path": "/v3/items",
        "query": {},
        "body": {"sku": "synthetic"} if write else None,
        "approval_ref": "owner-review" if write else None,
    }


def test_safe_get_uses_cloud_policy() -> None:
    policy = FakePolicy()
    transport = FakeTransport()
    executor = WalmartCloudExecutor(
        registry=registry(),
        store_allowlist=frozenset({"HK2615"}),
        policy=policy,
        transport=transport,
    )
    reply = executor.handle(event())
    assert reply["success"] is True
    assert reply["data"] == {"data": [{"sku": "synthetic"}]}
    assert policy.calls == [("HK2615", "listItems", False, None)]
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"store_code": "HK2614"}, "WALMART_STORE_NOT_AUTHORIZED"),
        ({"method": "DELETE"}, "WALMART_OPERATION_MISMATCH"),
        ({"path": "/v3/other"}, "WALMART_OPERATION_MISMATCH"),
        ({"api_key": "notApproved"}, "WALMART_API_NOT_REGISTERED"),
        ({"unexpected": "x"}, "WALMART_EVENT_INVALID"),
        ({"version": 99}, "WALMART_EVENT_INVALID"),
    ],
)
def test_rejects_untrusted_main_server_events(change: dict[str, object], code: str) -> None:
    transport = FakeTransport()
    executor = WalmartCloudExecutor(
        registry=registry(),
        store_allowlist=frozenset({"HK2615"}),
        policy=FakePolicy(),
        transport=transport,
    )
    reply = executor.handle({**event(), **change})
    assert reply == {"success": False, "status": code}
    assert transport.calls == []


def test_write_without_approval_never_transmits() -> None:
    transport = FakeTransport()
    executor = WalmartCloudExecutor(
        registry=registry(),
        store_allowlist=frozenset({"HK2615"}),
        policy=FakePolicy(),
        transport=transport,
    )
    reply = executor.handle({**event(operation="updateItem"), "approval_ref": None})
    assert reply["status"] == "WALMART_WRITE_APPROVAL_REQUIRED"
    assert transport.calls == []


def test_policy_denial_prevents_write() -> None:
    transport = FakeTransport()
    executor = WalmartCloudExecutor(
        registry=registry(),
        store_allowlist=frozenset({"HK2615"}),
        policy=FakePolicy(allow=False),
        transport=transport,
    )
    assert executor.handle(event(operation="updateItem"))["status"] == (
        "WALMART_OWNER_POLICY_DENIED"
    )
    assert transport.calls == []


def test_cn2502_supported_when_independently_configured() -> None:
    executor = WalmartCloudExecutor(
        registry=registry(),
        store_allowlist=frozenset({"CN2502"}),
        policy=FakePolicy(),
        transport=FakeTransport(),
    )
    assert executor.handle(event(store="CN2502"))["success"] is True
