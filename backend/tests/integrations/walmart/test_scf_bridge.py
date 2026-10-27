"""Mock-only SCF bridge tests: no network, secrets or production execution."""

import pytest

from app.integrations.walmart.contracts import PreparedRequest
from app.integrations.walmart.scf_bridge import GatewayRejected, ProtectedScfBridge


class FakeInvoker:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[object] = []

    def invoke(self, payload: object) -> dict[str, object]:
        self.calls.append(payload)
        return self.response


def request(*, write: bool = False) -> PreparedRequest:
    return PreparedRequest(
        "getInventory" if not write else "updateInventory",
        "GET" if not write else "PUT",
        "/v3/wfs/inventory",
        {},
        None if not write else {"sku": "fixture"},
        write,
    )


def test_mock_success_with_store_scope() -> None:
    fake = FakeInvoker(
        {
            "success": True,
            "store_code": "HK2615",
            "api_key": "getInventory",
            "status_code": 200,
            "data": {"items": []},
        }
    )
    bridge = ProtectedScfBridge(fake)
    result = bridge.execute(store_code="HK2615", request=request(), approval_ref=None)
    assert result.status_code == 200
    assert result.data == {"items": []}
    assert len(fake.calls) == 1


def test_write_stops_before_invocation_without_approval() -> None:
    fake = FakeInvoker({})
    bridge = ProtectedScfBridge(fake)
    with pytest.raises(GatewayRejected, match="WALMART_WRITE_APPROVAL_REQUIRED"):
        bridge.execute(store_code="HK2615", request=request(write=True), approval_ref=None)
    assert fake.calls == []


def test_rejects_wrong_store() -> None:
    fake = FakeInvoker(
        {
            "success": True,
            "store_code": "HK2614",
            "api_key": "getInventory",
            "status_code": 200,
            "data": {},
        }
    )
    with pytest.raises(GatewayRejected, match="WALMART_GATEWAY_SCOPE_MISMATCH"):
        ProtectedScfBridge(fake).execute(store_code="HK2615", request=request(), approval_ref=None)


def test_rejects_sensitive_response() -> None:
    fake = FakeInvoker(
        {
            "success": True,
            "store_code": "HK2615",
            "api_key": "getInventory",
            "status_code": 200,
            "data": {"AccessToken": "should_not_return"},
        }
    )
    with pytest.raises(GatewayRejected, match="WALMART_GATEWAY_SECRET_RESPONSE"):
        ProtectedScfBridge(fake).execute(store_code="HK2615", request=request(), approval_ref=None)


def test_rejects_invoker_failure_without_leakage() -> None:
    class Broken:
        def invoke(self, payload: object) -> None:
            raise ValueError("sensitive data must not escape")

    with pytest.raises(GatewayRejected, match="^WALMART_GATEWAY_UNAVAILABLE$"):
        ProtectedScfBridge(Broken()).execute(
            store_code="HK2615", request=request(), approval_ref=None
        )
