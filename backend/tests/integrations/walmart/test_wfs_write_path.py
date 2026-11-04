"""WFS write path: catalog, write API, bridge v2, executor v2, runtime policy, transport.

Everything here is offline: fake gateways, fake invokers, fake HTTP client. No Walmart,
Tencent or network I/O, and no credential appears anywhere.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contracts import ContractError, PreparedRequest
from app.integrations.walmart.https_transport import (
    ClientCredentials,
    TransportRejected,
    WalmartHttpsTransport,
)
from app.integrations.walmart.scf_bridge import GatewayRejected, ProtectedScfBridge
from app.integrations.walmart.scf_runtime import StoreWritePolicy, _load_registry
from app.integrations.walmart.unified_api import (
    WalmartIntegrationError,
    WalmartReadAPI,
    WalmartWriteAPI,
    load_unified_registry,
)
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS, wfs_write_registry

STORE = "HK2614"
CREATE_BODY: dict[str, Any] = {
    "inboundOrderId": "PMC-TEST-HK2614-20261031-01",
    "orderItems": [
        {
            "productId": "00460016364228",
            "productType": "GTIN",
            "sku": "YC00064-1U",
            "itemDesc": "Colander",
            "itemQty": 18,
            "vendorPackQty": 3,
            "innerPackQty": 6,
            "expectedDeliveryDate": "2026-11-30T00:00:00.000Z",
        }
    ],
    "inboundServices": {"inventoryTransferService": "Y"},
}
LABEL_BODY = {
    "shipmentId": "3109378WFB",
    "labelSize": "X4_6",
    "labelFormat": "PDF",
    "loadTypes": [{"loadType": "SINGLE SKU", "count": "3"}],
}
PDF = b"%PDF-1.4 synthetic label"
PDF_B64 = base64.b64encode(PDF).decode()


class FakeGateway:
    def __init__(self, result: WalmartResult | None = None) -> None:
        self.calls: list[tuple[str, PreparedRequest, str | None]] = []
        self.result = result or WalmartResult(status_code=200, data={"ok": True})

    def execute(
        self, *, store_code: str, request: PreparedRequest, approval_ref: str | None
    ) -> WalmartResult:
        self.calls.append((store_code, request, approval_ref))
        return self.result


# ---------------------------------------------------------------- catalog / registry


def test_write_catalog_is_disabled_by_default_and_all_mutating() -> None:
    registry = wfs_write_registry()
    assert set(registry.keys()) == WFS_WRITE_KEYS
    for key in WFS_WRITE_KEYS:
        op = registry.get(key)
        assert op.is_write and not op.enabled
    assert registry.get("wfs_shipment_label").response_kind == "pdf"
    assert registry.get("wfs_inbound_shipment_cancel").method == "DELETE"


def test_unified_registry_keeps_writes_closed_unless_write_approved() -> None:
    read_only = load_unified_registry(frozenset({"wfs_inventory"}))
    assert not read_only.get("wfs_inbound_shipment_create").enabled
    # A write key passed as a *read* approval is refused outright.
    with pytest.raises(WalmartIntegrationError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        load_unified_registry(frozenset({"wfs_inbound_shipment_create"}))
    writes = load_unified_registry(approved_write_keys=frozenset({"wfs_inbound_shipment_create"}))
    assert writes.get("wfs_inbound_shipment_create").enabled
    assert not writes.get("wfs_shipment_label").enabled
    assert not writes.get("wfs_inventory").enabled


def test_create_body_schema_rejects_bad_items() -> None:
    registry = load_unified_registry(approved_write_keys=WFS_WRITE_KEYS)
    prepared = registry.prepare("wfs_inbound_shipment_create", body=CREATE_BODY, allow_writes=True)
    assert prepared.is_write and prepared.path == "/v3/fulfillment/inbound-shipments"
    bad = {**CREATE_BODY, "orderItems": [{**CREATE_BODY["orderItems"][0], "productType": "UPC"}]}
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("wfs_inbound_shipment_create", body=bad, allow_writes=True)
    with pytest.raises(ContractError, match="WALMART_BODY_REQUIRED"):
        registry.prepare("wfs_inbound_shipment_create", allow_writes=True)
    label_bad = {**LABEL_BODY, "loadTypes": ["SINGLE SKU"]}
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("wfs_shipment_label", body=label_bad, allow_writes=True)
    cancel = registry.prepare(
        "wfs_inbound_shipment_cancel",
        params={"inboundOrderId": "PMC-TEST-HK2614-20261031-01"},
        allow_writes=True,
    )
    assert cancel.path == "/v3/fulfillment/inbound-shipments/PMC-TEST-HK2614-20261031-01"


# ---------------------------------------------------------------- write API


def test_write_api_requires_approval_and_refuses_reads() -> None:
    registry = load_unified_registry(
        frozenset({"wfs_inventory"}), approved_write_keys=WFS_WRITE_KEYS
    )
    gateway = FakeGateway()
    client = WalmartClient(registry, allowed_stores=frozenset({STORE}), gateway=gateway)
    api = WalmartWriteAPI(client)
    with pytest.raises(WalmartIntegrationError, match="WALMART_WRITE_APPROVAL_REQUIRED"):
        api.call(STORE, "wfs_inbound_shipment_create", approval_ref="", body=CREATE_BODY)
    with pytest.raises(WalmartIntegrationError, match="WALMART_WRITE_API_READ_OPERATION"):
        api.call(STORE, "wfs_inventory", approval_ref="op-1", params={"limit": 1})
    result = api.call(STORE, "wfs_inbound_shipment_create", approval_ref="op-1", body=CREATE_BODY)
    assert result.ok and gateway.calls[0][2] == "op-1"
    # The read API still cannot issue the write even though it is enabled in the registry.
    with pytest.raises(ValueError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        WalmartReadAPI(client).call(STORE, "wfs_inbound_shipment_create", params=None)


# ---------------------------------------------------------------- bridge protocol v2


class FakeInvoker:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.events: list[dict[str, Any]] = []

    def invoke(self, payload: Any) -> dict[str, Any]:
        self.events.append(dict(payload))
        return self.response


def _write_request(kind: str = "json") -> PreparedRequest:
    return PreparedRequest(
        "wfs_shipment_label" if kind == "pdf" else "wfs_inbound_shipment_create",
        "POST",
        "/v3/fulfillment/x",
        {},
        {"a": 1},
        True,
        response_kind=kind,
    )


def test_bridge_v2_passes_provider_error_and_decodes_pdf() -> None:
    error = FakeInvoker(
        {
            "success": True,
            "store_code": STORE,
            "api_key": "wfs_inbound_shipment_create",
            "status_code": 400,
            "data": None,
            "provider_error": {"errors": [{"code": "INVALID_REQUEST"}]},
        }
    )
    result = ProtectedScfBridge(error, version=2).execute(
        store_code=STORE, request=_write_request(), approval_ref="op-1"
    )
    assert result.status_code == 400 and result.data is None
    assert result.provider_error == {"errors": [{"code": "INVALID_REQUEST"}]}
    assert error.events[0]["version"] == 2 and error.events[0]["accept"] == "json"

    pdf = FakeInvoker(
        {
            "success": True,
            "store_code": STORE,
            "api_key": "wfs_shipment_label",
            "status_code": 200,
            "data": {
                "content_type": "application/pdf",
                "data_base64": PDF_B64,
            },
        }
    )
    result = ProtectedScfBridge(pdf, version=2).execute(
        store_code=STORE, request=_write_request("pdf"), approval_ref="op-1"
    )
    assert result.pdf == PDF and result.content_type == "application/pdf"
    assert pdf.events[0]["accept"] == "pdf"


def test_bridge_v1_still_rejects_provider_errors() -> None:
    invoker = FakeInvoker(
        {"success": True, "store_code": STORE, "api_key": "k", "status_code": 404, "data": None}
    )
    with pytest.raises(GatewayRejected, match="WALMART_PROVIDER_NOT_SUCCESSFUL"):
        ProtectedScfBridge(invoker).execute(
            store_code=STORE,
            request=PreparedRequest("k", "GET", "/v3/x", {}, None, False),
            approval_ref=None,
        )
    assert "accept" not in invoker.events[0] and invoker.events[0]["version"] == 1


def test_bridge_v2_rejects_bad_pdf_payload() -> None:
    invoker = FakeInvoker(
        {
            "success": True,
            "store_code": STORE,
            "api_key": "wfs_shipment_label",
            "status_code": 200,
            "data": {
                "content_type": "application/pdf",
                "data_base64": base64.b64encode(b"not a pdf").decode(),
            },
        }
    )
    with pytest.raises(GatewayRejected, match="WALMART_GATEWAY_RESPONSE_INVALID"):
        ProtectedScfBridge(invoker, version=2).execute(
            store_code=STORE, request=_write_request("pdf"), approval_ref="op-1"
        )


# ---------------------------------------------------------------- cloud executor v2


class RecordingTransport:
    def __init__(self, status: int, data: Any) -> None:
        self.status = status
        self.data = data
        self.requests: list[Any] = []

    def execute(self, *, store_code: str, request: Any) -> tuple[int, Any]:
        self.requests.append(request)
        return self.status, self.data


def _executor(transport: RecordingTransport) -> WalmartCloudExecutor:
    return WalmartCloudExecutor(
        registry=_load_registry(frozenset({"wfs_inventory"}), WFS_WRITE_KEYS),
        store_allowlist=frozenset({STORE}),
        policy=StoreWritePolicy(STORE, frozenset({"wfs_inventory"}), WFS_WRITE_KEYS),
        transport=transport,
    )


def _event(version: int, **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "version": version,
        "operation": "marketplace_call",
        "store_code": STORE,
        "api_key": "wfs_inbound_shipment_create",
        "method": "POST",
        "path": "/v3/fulfillment/inbound-shipments",
        "query": {},
        "body": CREATE_BODY,
        "approval_ref": "op-1",
    }
    event.update(overrides)
    return event


def test_executor_v2_returns_provider_error_instead_of_failing() -> None:
    transport = RecordingTransport(400, {"errors": [{"code": "DUPLICATE_ORDER"}]})
    out = _executor(transport).handle(_event(2, accept="json"))
    assert out == {
        "success": True,
        "status_code": 400,
        "store_code": STORE,
        "api_key": "wfs_inbound_shipment_create",
        "data": None,
        "provider_error": {"errors": [{"code": "DUPLICATE_ORDER"}]},
    }
    # v1 keeps the historical contract: a provider error is an executor failure.
    out_v1 = _executor(RecordingTransport(400, {"errors": []})).handle(_event(1))
    assert out_v1 == {"success": False, "status": "WALMART_PROVIDER_ERROR"}


def test_executor_requires_approval_and_matching_accept() -> None:
    transport = RecordingTransport(200, {"ok": True})
    assert _executor(transport).handle(_event(2, accept="json", approval_ref=None)) == {
        "success": False,
        "status": "WALMART_WRITE_APPROVAL_REQUIRED",
    }
    assert _executor(transport).handle(_event(2, accept="pdf")) == {
        "success": False,
        "status": "WALMART_OPERATION_MISMATCH",
    }
    assert _executor(transport).handle(_event(1, accept="json")) == {
        "success": False,
        "status": "WALMART_EVENT_INVALID",
    }
    assert transport.requests == []


def test_runtime_registry_refuses_write_key_in_read_set() -> None:
    with pytest.raises(ValueError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        _load_registry(frozenset({"wfs_inbound_shipment_create"}))
    policy = StoreWritePolicy(
        STORE, frozenset({"wfs_inventory"}), frozenset({"wfs_shipment_label"})
    )
    assert policy.authorize(
        store_code=STORE, operation_key="wfs_shipment_label", is_write=True, approval_ref="op"
    )
    assert not policy.authorize(
        store_code=STORE, operation_key="wfs_shipment_label", is_write=True, approval_ref=None
    )
    assert not policy.authorize(
        store_code=STORE, operation_key="wfs_inbound_preview", is_write=True, approval_ref="op"
    )
    assert policy.authorize(
        store_code=STORE, operation_key="wfs_inventory", is_write=False, approval_ref=None
    )


# ---------------------------------------------------------------- https transport


class FakeSecretResolver:
    def get_store_credentials(self, store_code: str) -> ClientCredentials:
        return ClientCredentials(client_id="fake-id", client_secret="fake-secret")


class FakeStream:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self.body = body

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_bytes(self) -> list[bytes]:
        return [self.body]


def _fake_client_factory(status: int, body: bytes):
    class FakeClient:
        last_headers: dict[str, str] = {}

        def __init__(self, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: Any) -> FakeStream:
            if url.endswith("/v3/token"):
                return FakeStream(200, b'{"access_token":"synthetic-token"}')
            FakeClient.last_headers = dict(kwargs.get("headers", {}))
            return FakeStream(status, body)

    return FakeClient


def test_transport_passes_provider_error_only_in_write_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_client_factory(400, b'{"errors":[{"code":"X"}]}'))
    request = PreparedRequest("k", "POST", "/v3/fulfillment/inbound-shipments", {}, {"a": 1}, True)
    proxies = {STORE: "http://10.3.4.5:3128"}
    strict = WalmartHttpsTransport(proxy_by_store=proxies, secret_resolver=FakeSecretResolver())
    with pytest.raises(TransportRejected, match="WALMART_HTTP_ERROR"):
        strict.execute(store_code=STORE, request=request)
    lenient = WalmartHttpsTransport(
        proxy_by_store=proxies, secret_resolver=FakeSecretResolver(), pass_provider_errors=True
    )
    assert lenient.execute(store_code=STORE, request=request) == (400, {"errors": [{"code": "X"}]})


def test_transport_returns_pdf_as_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_client_factory(200, PDF)
    monkeypatch.setattr(httpx, "Client", fake)
    request = PreparedRequest(
        "wfs_shipment_label",
        "POST",
        "/v3/fulfillment/shipment-label",
        {},
        LABEL_BODY,
        True,
        response_kind="pdf",
    )
    transport = WalmartHttpsTransport(
        proxy_by_store={STORE: "http://10.3.4.5:3128"},
        secret_resolver=FakeSecretResolver(),
        pass_provider_errors=True,
    )
    status, data = transport.execute(store_code=STORE, request=request)
    assert status == 200
    assert data == {
        "content_type": "application/pdf",
        "data_base64": PDF_B64,
    }
    assert fake.last_headers["Accept"] == "application/pdf"
