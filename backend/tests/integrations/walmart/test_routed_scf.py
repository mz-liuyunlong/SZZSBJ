"""Per-store SCF routing tests, using a synthetic cloud invoker."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.integrations.walmart.planner import WalmartPlanError
from app.integrations.walmart.routed_scf import RoutedScfGateway, create_scoped_client
from app.integrations.walmart.wfs_catalog import wfs_registry


class MockCloudApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def request(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert service == "scf"
        event = json.loads(payload["ClientContext"])
        self.calls.append((event["store_code"], payload["FunctionName"]))
        reply = {
            "success": True,
            "status_code": 200,
            "store_code": event["store_code"],
            "api_key": event["api_key"],
            "data": {"items": []},
        }
        return {"Result": {"InvokeResult": 0, "RetMsg": json.dumps(reply)}}


def test_each_store_uses_own_cloud_function() -> None:
    api = MockCloudApi()
    client = create_scoped_client(
        wfs_registry(approved_keys=frozenset({"wfs_inventory"})),
        allowed_stores=frozenset({"HK2615", "CN2502"}),
        function_by_store={
            "HK2615": "walmart-HK2615-isolated",
            "CN2502": "walmart-CN2502-isolated",
        },
        cloud_api=api,
    )
    assert client.call("HK2615", "wfs_inventory", params={"limit": 1}).status_code == 200
    assert client.call("CN2502", "wfs_inventory", params={"limit": 1}).status_code == 200
    assert api.calls == [
        ("HK2615", "walmart-HK2615-isolated"),
        ("CN2502", "walmart-CN2502-isolated"),
    ]


def test_shared_function_name_is_rejected() -> None:
    with pytest.raises(WalmartPlanError, match="WALMART_SHARED_FUNCTION_FORBIDDEN"):
        RoutedScfGateway(
            MockCloudApi(),
            function_by_store={
                "HK2615": "shared",
                "CN2502": "shared",
            },
        )


def test_missing_function_fails_closed() -> None:
    api = MockCloudApi()
    client = create_scoped_client(
        wfs_registry(approved_keys=frozenset({"wfs_inventory"})),
        allowed_stores=frozenset({"HK2615"}),
        function_by_store={"CN2502": "walmart-CN2502-isolated"},
        cloud_api=api,
    )
    with pytest.raises(WalmartPlanError, match="WALMART_STORE_GATEWAY_UNAVAILABLE"):
        client.call("HK2615", "wfs_inventory")
    assert api.calls == []
