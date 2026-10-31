"""Protocol v3: signed contracts replace per-operation cloud allowlists (handover ch. 76)."""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

import pytest

from app.integrations.walmart.client import WalmartClient
from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contract_signing import ContractSigner, ContractVerifier
from app.integrations.walmart.contracts import (
    ContractError,
    ContractRegistry,
    Field,
    Operation,
    contract_dict,
    operation_from_contract,
    sha256_hex,
)
from app.integrations.walmart.scf_bridge import GatewayRejected, ProtectedScfBridge
from app.integrations.walmart.unified_api import (
    WFS_CANCEL_PERMISSION,
    WFS_WRITE_PERMISSION,
    reviewed_registry,
)
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS

NOW = 1_761_900_000
STORE = "HK2614"
ACTOR = {"kind": "system", "uid": "pmc-wfs-creation"}


class FakeTransport:
    def __init__(self, status: int = 200, data: Any = None) -> None:
        self.status = status
        self.data = {"ok": True} if data is None else data
        self.calls: list[tuple[str, Any]] = []

    def execute(self, *, store_code: str, request: Any) -> tuple[int, Any]:
        self.calls.append((store_code, request))
        return self.status, self.data


class DenyAllPolicy:
    """v1/v2 keyed policy; v3 must never consult it."""

    def authorize(self, **_: Any) -> bool:  # pragma: no cover - asserts via behaviour
        raise AssertionError("v3 must not use the keyed policy")


@pytest.fixture
def signer() -> ContractSigner:
    return ContractSigner.generate(kid="szzsbj-test")


@pytest.fixture
def verifier(signer: ContractSigner) -> ContractVerifier:
    raw = json.dumps({signer.kid: signer.public_key_b64()})
    return ContractVerifier.from_env_json(raw, clock=lambda: NOW)


@pytest.fixture
def live_verifier(signer: ContractSigner) -> ContractVerifier:
    """Real clock: the bridge stamps issued_at itself."""
    return ContractVerifier.from_env_json(json.dumps({signer.kid: signer.public_key_b64()}))


def _executor(verifier: ContractVerifier, transport: FakeTransport, *, max_risk: str = "read"):
    return WalmartCloudExecutor(
        registry=ContractRegistry(()),
        store_allowlist=frozenset({STORE}),
        policy=DenyAllPolicy(),
        transport=transport,
        verifier=verifier,
        max_risk=max_risk,
    )


def _event(
    signer: ContractSigner,
    key: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
    approval_ref: str | None = None,
    store: str = STORE,
    issued_at: int = NOW,
) -> dict[str, Any]:
    registry = reviewed_registry()
    request = registry.prepare(key, params=params, body=body, allow_writes=True)
    assert request.contract is not None
    auth = signer.sign(
        store_code=store,
        contract=request.contract,
        method=request.method,
        path=request.path,
        params=request.params or {},
        body=request.body,
        approval_ref=approval_ref,
        issued_at=issued_at,
        nonce="0" * 32,
    )
    return {
        "version": 3,
        "operation": "marketplace_call",
        "store_code": store,
        "contract": dict(request.contract),
        "method": request.method,
        "path": request.path,
        "params": dict(request.params or {}),
        "body": request.body,
        "accept": request.response_kind,
        "approval_ref": approval_ref,
        "actor": dict(ACTOR),
        "auth": auth,
    }


# --- registry -------------------------------------------------------------------------


def test_reviewed_registry_enables_every_builtin_with_permissions():
    registry = reviewed_registry()
    assert WFS_WRITE_KEYS <= set(registry.keys())
    assert {"wfs_inventory", "inbound_shipments", "inbound_shipment_items"} <= set(registry.keys())
    for key in registry.keys():
        operation = registry.get(key)
        assert operation.enabled and operation.permission and operation.family
        if operation.is_write:
            assert operation.permission in {WFS_WRITE_PERMISSION, WFS_CANCEL_PERMISSION}
        else:
            assert operation.permission == f"action:walmart:{operation.family}:read"
    assert registry.get("wfs_inbound_shipment_cancel").permission == WFS_CANCEL_PERMISSION
    assert len(registry.version()) == 16 and registry.version() == reviewed_registry().version()


def test_contract_roundtrip_and_version_changes_with_contract():
    registry = reviewed_registry()
    operation = registry.get("inbound_shipments")
    rebuilt = operation_from_contract(contract_dict(operation))
    assert contract_dict(rebuilt) == contract_dict(operation)
    assert rebuilt.enabled and rebuilt.permission == operation.permission
    changed = ContractRegistry(
        (
            Operation(
                key="x_op",
                method="GET",
                path="/v3/x",
                fields=(Field("limit", "query", kind="integer"),),
                enabled=True,
            ),
        )
    )
    other = ContractRegistry(
        (
            Operation(
                key="x_op",
                method="GET",
                path="/v3/x",
                fields=(Field("limit", "query", kind="integer", maximum=10),),
                enabled=True,
            ),
        )
    )
    assert changed.version() != other.version()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(path="/v3/../token"),
        lambda c: c.update(path="/v2/items"),
        lambda c: c.update(method="CONNECT"),
        lambda c: c.update(response_kind="html"),
        lambda c: c.update(permission="action:evil"),
        lambda c: c.pop("fields"),
        lambda c: c.update(extra=1),
        lambda c: c["fields"].append(
            {
                "name": "authorization",
                "location": "query",
                "required": False,
                "kind": "string",
                "enum": [],
                "maximum": None,
                "schema": None,
                "style": "form",
                "explode": True,
            }
        ),
    ],
)
def test_contract_shape_violations_are_rejected(mutate):
    contract = contract_dict(reviewed_registry().get("inbound_shipments"))
    mutate(contract)
    with pytest.raises(ContractError, match="WALMART_CONTRACT_INVALID"):
        operation_from_contract(contract)


# --- signing ---------------------------------------------------------------------------


def test_sign_verify_roundtrip(signer, verifier):
    event = _event(signer, "inbound_shipments", params={"fromCreatedDate": 1, "toCreatedDate": 2})
    operation, digest = verifier.verify(event)
    assert operation.key == "inbound_shipments" and digest == sha256_hex(event["contract"])


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            lambda e: e["body"]["payload"].__setitem__("inboundOrderId", "X"),
            "WALMART_SIGNATURE_INVALID",
        ),
        (
            lambda e: e.__setitem__("path", "/v3/fulfillment/inbound-shipmentsX"),
            "WALMART_SIGNATURE_INVALID",
        ),
        (lambda e: e.__setitem__("store_code", "HK2613"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("approval_ref", "other"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e["contract"].__setitem__("mutating", False), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e["auth"].__setitem__("kid", "someone-else"), "WALMART_SIGNATURE_KEY_UNKNOWN"),
        (lambda e: e["auth"].__setitem__("issued_at", NOW - 301), "WALMART_SIGNATURE_EXPIRED"),
        (lambda e: e["auth"].__setitem__("issued_at", NOW + 301), "WALMART_SIGNATURE_EXPIRED"),
        (
            lambda e: e["auth"].__setitem__("sig", base64.b64encode(b"x" * 64).decode()),
            "WALMART_SIGNATURE_INVALID",
        ),
        (lambda e: e.__setitem__("auth", {"kid": "szzsbj-test"}), "WALMART_SIGNATURE_INVALID"),
    ],
)
def test_tampering_is_detected(signer, verifier, change, code):
    event = _event(signer, "wfs_inbound_preview", body=_preview_body(), approval_ref="wfs-ticket:1")
    change(event)
    with pytest.raises(ContractError, match=code):
        verifier.verify(event)


def _preview_body() -> dict[str, Any]:
    return {
        "header": {"headerAttributes": {}},
        "payload": {
            "inboundOrderId": "PMC-TEST-HK2614-ABC123456789",
            "orderItems": [
                {
                    "productId": "00012345678905",
                    "productType": "GTIN",
                    "sku": "SKU-1",
                    "itemDesc": "test",
                    "itemQty": 1,
                    "vendorPackQty": 1,
                    "innerPackQty": 1,
                    "expectedDeliveryDate": "2026-11-30T00:00:00.000Z",
                }
            ],
        },
    }


def test_public_key_env_parsing_rejects_garbage():
    with pytest.raises(ContractError, match="WALMART_VERIFY_KEYS_INVALID"):
        ContractVerifier.from_env_json("not json")
    with pytest.raises(ContractError, match="WALMART_VERIFY_KEYS_INVALID"):
        ContractVerifier.from_env_json(json.dumps({"k": "AAAA"}))
    with pytest.raises(ContractError, match="WALMART_VERIFY_KEYS_INVALID"):
        ContractVerifier.from_env_json("{}")
    good = ContractSigner.generate(kid="rotation-b")
    pair = ContractVerifier.from_env_json(
        json.dumps(
            {
                "rotation-a": ContractSigner.generate(kid="rotation-a").public_key_b64(),
                "rotation-b": good.public_key_b64(),
            }
        ),
        clock=lambda: NOW,
    )
    event = _event(good, "wfs_inventory", params={"limit": 1})
    assert pair.verify(event)[0].key == "wfs_inventory"


def test_pem_file_roundtrip(tmp_path, signer):
    pem = tmp_path / "k.pem"
    pem.write_bytes(signer.private_pem())
    loaded = ContractSigner.from_pem_file(pem, kid=signer.kid)
    assert loaded.public_key_b64() == signer.public_key_b64()
    assert "REDACTED" not in repr(loaded) and "BEGIN" not in repr(loaded)
    with pytest.raises(ContractError, match="WALMART_SIGNING_KEY_UNAVAILABLE"):
        ContractSigner.from_pem_file(tmp_path / "missing.pem", kid="x-y-z")
    (tmp_path / "bad.pem").write_text("nope")
    with pytest.raises(ContractError, match="WALMART_SIGNING_KEY_INVALID"):
        ContractSigner.from_pem_file(tmp_path / "bad.pem", kid="x-y-z")


# --- cloud executor --------------------------------------------------------------------


def test_v3_read_executes_without_any_allowlist(signer, verifier):
    transport = FakeTransport(data={"elements": {"inventory": []}})
    executor = _executor(verifier, transport)
    event = _event(
        signer, "inbound_shipments", params={"fromCreatedDate": 1, "toCreatedDate": 2, "limit": 50}
    )
    result = executor.handle(event)
    assert result["success"] is True and result["protocol"] == 3
    assert result["api_key"] == "inbound_shipments" and result["store_code"] == STORE
    assert result["contract_sha256"] == sha256_hex(event["contract"])
    assert result["registry_version"] == reviewed_registry().version()
    assert result["data"] == {"elements": {"inventory": []}} and result["provider_error"] is None
    store, request = transport.calls[0]
    assert store == STORE and request.path == "/v3/fulfillment/inbound-shipments"
    assert request.query == {"fromCreatedDate": 1, "toCreatedDate": 2, "limit": 50}


def test_v3_new_read_contract_needs_no_cloud_env_change(signer, verifier):
    """A contract that is not in the cloud's own catalog still executes when signed."""
    operation = Operation(
        key="brand_new_report",
        method="GET",
        path="/v3/reports/brand-new",
        fields=(Field("limit", "query", kind="integer", maximum=50),),
        enabled=True,
    )
    registry = ContractRegistry((operation,))
    request = registry.prepare("brand_new_report", params={"limit": 5})
    auth = signer.sign(
        store_code=STORE,
        contract=request.contract,
        method=request.method,
        path=request.path,
        params=request.params or {},
        body=None,
        approval_ref=None,
        issued_at=NOW,
    )
    event = {
        "version": 3,
        "operation": "marketplace_call",
        "store_code": STORE,
        "contract": dict(request.contract),
        "method": "GET",
        "path": "/v3/reports/brand-new",
        "params": {"limit": 5},
        "body": None,
        "accept": "json",
        "approval_ref": None,
        "actor": dict(ACTOR),
        "auth": auth,
    }
    transport = FakeTransport()
    assert _executor(verifier, transport).handle(event)["success"] is True
    # ...but the contract's own schema is still enforced on the cloud side.
    event["params"] = {"limit": 500}
    event["auth"] = signer.sign(
        store_code=STORE,
        contract=request.contract,
        method="GET",
        path="/v3/reports/brand-new",
        params={"limit": 500},
        body=None,
        approval_ref=None,
        issued_at=NOW,
    )
    assert _executor(verifier, FakeTransport()).handle(event)["status"] == "WALMART_FIELD_INVALID"


def test_v3_write_needs_write_ceiling_and_approval(signer, verifier):
    body = _preview_body()
    denied = _executor(verifier, FakeTransport(), max_risk="read").handle(
        _event(signer, "wfs_inbound_preview", body=body, approval_ref="wfs-ticket:1")
    )
    assert denied == {"success": False, "status": "WALMART_RISK_CEILING_DENIED"}
    no_approval = _executor(verifier, FakeTransport(), max_risk="write").handle(
        _event(signer, "wfs_inbound_preview", body=body)
    )
    assert no_approval["status"] == "WALMART_WRITE_APPROVAL_REQUIRED"
    transport = FakeTransport(data={"shipmentPlans": []})
    ok = _executor(verifier, transport, max_risk="write").handle(
        _event(signer, "wfs_inbound_preview", body=body, approval_ref="wfs-ticket:1")
    )
    assert ok["success"] is True and transport.calls[0][1].body == body


def test_v3_provider_error_is_returned_not_raised(signer, verifier):
    transport = FakeTransport(status=400, data={"errors": [{"code": "INVALID"}]})
    result = _executor(verifier, transport, max_risk="write").handle(
        _event(signer, "wfs_inbound_preview", body=_preview_body(), approval_ref="wfs-ticket:1")
    )
    assert result["success"] is True and result["status_code"] == 400
    assert result["data"] is None and result["provider_error"] == {"errors": [{"code": "INVALID"}]}


def test_v3_cross_store_and_mismatch_rejections(signer, verifier):
    executor = _executor(verifier, FakeTransport())
    other_store = _event(signer, "wfs_inventory", params={"limit": 1}, store="HK2613")
    assert executor.handle(other_store)["status"] == "WALMART_STORE_NOT_AUTHORIZED"
    event = _event(signer, "wfs_inventory", params={"limit": 1})
    bad_path = copy.deepcopy(event)
    bad_path["path"] = "/v3/token"
    assert executor.handle(bad_path)["status"] == "WALMART_SIGNATURE_INVALID"
    bad_accept = copy.deepcopy(event)
    bad_accept["accept"] = "pdf"
    assert executor.handle(bad_accept)["status"] == "WALMART_OPERATION_MISMATCH"
    bad_actor = copy.deepcopy(event)
    bad_actor["actor"] = {"kind": "root", "uid": "x"}
    assert executor.handle(bad_actor)["status"] == "WALMART_ACTOR_INVALID"
    extra = copy.deepcopy(event)
    extra["api_key"] = "wfs_inventory"
    assert executor.handle(extra)["status"] == "WALMART_EVENT_INVALID"


def test_v3_without_verifier_is_disabled_and_v1_still_works(signer):
    from app.integrations.walmart.wfs_catalog import wfs_registry

    class AllowReads:
        def authorize(self, *, store_code, operation_key, is_write, approval_ref):
            return store_code == STORE and not is_write

    legacy = WalmartCloudExecutor(
        registry=wfs_registry(approved_keys=frozenset({"wfs_inventory"})),
        store_allowlist=frozenset({STORE}),
        policy=AllowReads(),
        transport=FakeTransport(),
    )
    assert legacy.handle(_event(signer, "wfs_inventory", params={"limit": 1}))["status"] == (
        "WALMART_PROTOCOL_NOT_ENABLED"
    )
    v1 = {
        "version": 1,
        "operation": "marketplace_call",
        "store_code": STORE,
        "api_key": "wfs_inventory",
        "method": "GET",
        "path": "/v3/wfs/inventory",
        "query": {"limit": 1},
        "body": None,
        "approval_ref": None,
    }
    assert legacy.handle(v1)["success"] is True


# --- bridge / client -------------------------------------------------------------------


class RecordingInvoker:
    def __init__(self, executor: WalmartCloudExecutor) -> None:
        self.executor = executor
        self.events: list[dict[str, Any]] = []

    def invoke(self, payload):
        self.events.append(copy.deepcopy(payload))
        return self.executor.handle(payload)


def test_bridge_v3_end_to_end_through_client(signer, live_verifier):
    transport = FakeTransport(data={"elements": {"inventory": [{"sku": "A"}]}})
    invoker = RecordingInvoker(_executor(live_verifier, transport))
    bridge = ProtectedScfBridge(invoker, version=3, signer=signer)
    client = WalmartClient(
        reviewed_registry(),
        allowed_stores=frozenset({STORE}),
        configured_stores=frozenset({STORE}),
        gateway=_ClientGateway(bridge),
    )
    result = client.call(STORE, "wfs_inventory", params={"limit": 1}, actor=ACTOR)
    assert result.ok and result.data == {"elements": {"inventory": [{"sku": "A"}]}}
    sent = invoker.events[0]
    assert sent["version"] == 3 and sent["actor"] == ACTOR and "api_key" not in sent
    assert sent["contract"]["key"] == "wfs_inventory" and sent["auth"]["kid"] == signer.kid


class _ClientGateway:
    def __init__(self, bridge: ProtectedScfBridge) -> None:
        self._bridge = bridge

    def execute(self, *, store_code, request, approval_ref, actor=None):
        from app.integrations.walmart.client import WalmartResult

        reply = self._bridge.execute(
            store_code=store_code, request=request, approval_ref=approval_ref, actor=actor
        )
        return WalmartResult(
            status_code=reply.status_code,
            data=reply.data,
            provider_error=reply.provider_error,
            content_type=reply.content_type,
            pdf=reply.pdf,
        )


def test_bridge_v3_requires_signer_and_actor_and_checks_echo(signer, verifier):
    with pytest.raises(GatewayRejected, match="WALMART_SIGNER_REQUIRED"):
        ProtectedScfBridge(RecordingInvoker(_executor(verifier, FakeTransport())), version=3)
    bridge = ProtectedScfBridge(
        RecordingInvoker(_executor(verifier, FakeTransport())), version=3, signer=signer
    )
    request = reviewed_registry().prepare("wfs_inventory", params={"limit": 1})
    with pytest.raises(GatewayRejected, match="WALMART_ACTOR_INVALID"):
        bridge.execute(store_code=STORE, request=request, approval_ref=None)

    class WrongEcho:
        def invoke(self, payload):
            return {
                "success": True,
                "protocol": 3,
                "status_code": 200,
                "store_code": STORE,
                "api_key": "wfs_inventory",
                "contract_sha256": "0" * 64,
                "data": {},
            }

    with pytest.raises(GatewayRejected, match="WALMART_GATEWAY_SCOPE_MISMATCH"):
        ProtectedScfBridge(WrongEcho(), version=3, signer=signer).execute(
            store_code=STORE, request=request, approval_ref=None, actor=ACTOR
        )


def test_bridge_v3_label_pdf_and_provider_error(signer, live_verifier):
    verifier = live_verifier
    pdf = b"%PDF-1.4 test"

    class PdfTransport:
        def execute(self, *, store_code, request):
            return 200, {
                "content_type": "application/pdf",
                "data_base64": base64.b64encode(pdf).decode(),
            }

    bridge = ProtectedScfBridge(
        RecordingInvoker(
            WalmartCloudExecutor(
                registry=ContractRegistry(()),
                store_allowlist=frozenset({STORE}),
                policy=DenyAllPolicy(),
                transport=PdfTransport(),
                verifier=verifier,
                max_risk="write",
            )
        ),
        version=3,
        signer=signer,
    )
    request = reviewed_registry().prepare(
        "wfs_shipment_label",
        body={
            "shipmentId": "SHP1",
            "labelSize": "X4_6",
            "labelFormat": "PDF",
            "loadTypes": [{"loadType": "SINGLE SKU", "count": "1"}],
        },
        allow_writes=True,
    )
    reply = bridge.execute(
        store_code=STORE, request=request, approval_ref="wfs-ticket:1", actor=ACTOR
    )
    assert reply.pdf == pdf and reply.content_type == "application/pdf"
    rejected = ProtectedScfBridge(
        RecordingInvoker(
            _executor(verifier, FakeTransport(status=404, data={"errors": []}), max_risk="write")
        ),
        version=3,
        signer=signer,
    ).execute(store_code=STORE, request=request, approval_ref="wfs-ticket:1", actor=ACTOR)
    assert (
        rejected.status_code == 404
        and rejected.provider_error == {"errors": []}
        and rejected.pdf is None
    )


# --- SCF runtime environment ------------------------------------------------------------


def test_runtime_env_helpers_and_v3_gate(monkeypatch, signer):
    from app.integrations.walmart import scf_runtime

    monkeypatch.delenv(scf_runtime.PUBLIC_KEYS_ENV, raising=False)
    monkeypatch.delenv(scf_runtime.MAX_RISK_ENV, raising=False)
    assert scf_runtime._verifier_from_env() is None
    assert scf_runtime._max_risk_from_env(True) == "read"
    monkeypatch.setenv(scf_runtime.MAX_RISK_ENV, "write")
    assert scf_runtime._max_risk_from_env(False) == "read"  # read-only live mode wins
    assert scf_runtime._max_risk_from_env(True) == "write"
    monkeypatch.setenv(scf_runtime.MAX_RISK_ENV, "admin")
    with pytest.raises(ValueError, match="WALMART_RISK_CEILING_INVALID"):
        scf_runtime._max_risk_from_env(True)
    monkeypatch.setenv(
        scf_runtime.PUBLIC_KEYS_ENV, json.dumps({signer.kid: signer.public_key_b64()})
    )
    assert scf_runtime._verifier_from_env() is not None

    # A v3 event against a function deployed without public keys is refused before any
    # identity, secret or transport work happens; v1 behaviour is untouched.
    monkeypatch.delenv(scf_runtime.PUBLIC_KEYS_ENV, raising=False)
    monkeypatch.setenv("SZZSBJ_WALMART_LIVE_MODE", scf_runtime.LIVE_MODE_READ_ONLY)
    monkeypatch.setenv("SZZSBJ_WALMART_BOUND_STORE", STORE)
    monkeypatch.delenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", raising=False)
    event = _event(signer, "wfs_inventory", params={"limit": 1})
    assert scf_runtime.main_handler(event, None) == {
        "success": False,
        "status": "WALMART_PROTOCOL_NOT_ENABLED",
    }
    assert scf_runtime.main_handler({"version": 1, "operation": "marketplace_call"}, None) == {
        "success": False,
        "status": "WALMART_RUNTIME_UNAVAILABLE",
    }
