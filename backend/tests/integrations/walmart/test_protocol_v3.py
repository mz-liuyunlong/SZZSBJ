"""Protocol v3: signed contracts replace per-operation cloud allowlists (handover ch. 76)."""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

import pytest

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contract_signing import (
    MAX_TTL_SECONDS,
    ContractSigner,
    ContractVerifier,
    FileReplayStore,
    MemoryReplayStore,
    RedisReplayStore,
    risk_for,
)
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
FUNCTION = "szzsbj-walmart-hk2614-executor"
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
    return ContractSigner.generate(kid="szzsbj-test", registry=reviewed_registry())


def _verifier(signer: ContractSigner, *, clock=lambda: NOW, **kwargs: Any) -> ContractVerifier:
    kwargs.setdefault("replay", FileReplayStore(_SHARED_DIR.path))
    return ContractVerifier.from_env_json(
        json.dumps({signer.kid: signer.public_key_b64()}),
        bound_store=STORE,
        bound_function=FUNCTION,
        clock=clock,
        **kwargs,
    )


class _SharedDir:
    """A fresh shared replay directory per test (set by the autouse fixture)."""

    path: Any = None


_SHARED_DIR = _SharedDir()


@pytest.fixture(autouse=True)
def _shared_replay_dir(tmp_path):
    _SHARED_DIR.path = tmp_path / "replay"
    _SHARED_DIR.path.mkdir()
    yield
    _SHARED_DIR.path = None


@pytest.fixture
def verifier(signer: ContractSigner) -> ContractVerifier:
    return _verifier(signer)


@pytest.fixture
def live_verifier(signer: ContractSigner) -> ContractVerifier:
    """Real clock: the bridge stamps issued_at itself."""
    import time

    return _verifier(signer, clock=time.time)


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
    function: str = FUNCTION,
    issued_at: int = NOW,
    ttl: int = 120,
    request_id: str = "0" * 32,
    registry: ContractRegistry | None = None,
) -> dict[str, Any]:
    registry = registry or reviewed_registry()
    request = registry.prepare(key, params=params, body=body, allow_writes=True)
    assert request.contract is not None
    auth = signer.sign(
        store_code=store,
        function_name=function,
        contract=request.contract,
        method=request.method,
        path=request.path,
        params=request.params or {},
        body=request.body,
        response_kind=request.response_kind,
        actor=dict(ACTOR),
        approval_ref=approval_ref,
        ttl_seconds=ttl,
        issued_at=issued_at,
        request_id=request_id,
    )
    return {
        "version": 3,
        "operation": "marketplace_call",
        "store_code": store,
        "function_name": function,
        "contract": dict(request.contract),
        "method": request.method,
        "path": request.path,
        "params": dict(request.params or {}),
        "body": request.body,
        "accept": request.response_kind,
        "risk": risk_for(request.method, key),
        "approval_ref": approval_ref,
        "actor": dict(ACTOR),
        "auth": auth,
    }


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
        # Reviewer requirement 3: server-side risk must equal the cloud's method-based risk.
        assert operation.risk == risk_for(operation.method, key)
    assert registry.get("wfs_inbound_shipment_cancel").permission == WFS_CANCEL_PERMISSION
    assert registry.get("wfs_inbound_preview").risk == "write"  # a POST, even if query-like
    assert len(registry.version()) == 16 and registry.version() == reviewed_registry().version()


def test_contract_roundtrip_and_version_changes_with_contract():
    registry = reviewed_registry()
    operation = registry.get("inbound_shipments")
    rebuilt = operation_from_contract(contract_dict(operation))
    assert contract_dict(rebuilt) == contract_dict(operation)
    assert rebuilt.enabled and rebuilt.permission == operation.permission
    base = Operation(
        key="x_op",
        method="GET",
        path="/v3/x",
        fields=(Field("limit", "query", kind="integer"),),
        enabled=True,
    )
    tightened = Operation(
        key="x_op",
        method="GET",
        path="/v3/x",
        fields=(Field("limit", "query", kind="integer", maximum=10),),
        enabled=True,
    )
    assert ContractRegistry((base,)).version() != ContractRegistry((tightened,)).version()


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
    verified = verifier.verify(event)
    assert verified.operation.key == "inbound_shipments"
    assert verified.contract_sha256 == sha256_hex(event["contract"])
    assert verified.risk == "read" and verified.request_id == "0" * 32
    assert event["auth"]["expires_at"] == NOW + 120


def test_signer_only_signs_registered_contracts(signer):
    """Reviewer requirement 2: business code cannot sign an ad-hoc method/path/schema."""
    adhoc = ContractRegistry(
        (
            Operation(
                key="adhoc_report",
                method="GET",
                path="/v3/reports/adhoc",
                fields=(),
                enabled=True,
            ),
        )
    )
    request = adhoc.prepare("adhoc_report")
    with pytest.raises(ContractError, match="WALMART_CONTRACT_NOT_REGISTERED"):
        signer.sign(
            store_code=STORE,
            function_name=FUNCTION,
            contract=request.contract,
            method="GET",
            path=request.path,
            params={},
            body=None,
            response_kind="json",
            actor=dict(ACTOR),
            approval_ref=None,
        )
    # A registered contract whose dict was edited after prepare() is refused too.
    good = reviewed_registry().prepare("wfs_inventory", params={"limit": 1})
    edited = dict(good.contract)
    edited["path"] = "/v3/wfs/inventory-all"
    with pytest.raises(ContractError, match="WALMART_CONTRACT_NOT_REGISTERED"):
        signer.sign(
            store_code=STORE,
            function_name=FUNCTION,
            contract=edited,
            method="GET",
            path="/v3/wfs/inventory-all",
            params={},
            body=None,
            response_kind="json",
            actor=dict(ACTOR),
            approval_ref=None,
        )
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_TTL_INVALID"):
        signer.sign(
            store_code=STORE,
            function_name=FUNCTION,
            contract=good.contract,
            method="GET",
            path=good.path,
            params=good.params,
            body=None,
            response_kind="json",
            actor=dict(ACTOR),
            approval_ref=None,
            ttl_seconds=MAX_TTL_SECONDS + 1,
        )


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
        (lambda e: e.__setitem__("method", "PUT"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("params", {"limit": 9}), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("store_code", "HK2613"), "WALMART_STORE_NOT_AUTHORIZED"),
        (
            lambda e: e.__setitem__("function_name", "szzsbj-walmart-hk2613-executor"),
            "WALMART_FUNCTION_MISMATCH",
        ),
        (lambda e: e.__setitem__("approval_ref", "other"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("accept", "pdf"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("risk", "read"), "WALMART_RISK_MISMATCH"),
        (lambda e: e["actor"].__setitem__("uid", "someone-else"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e["actor"].__setitem__("kind", "user"), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e.__setitem__("actor", {"kind": "root", "uid": "x"}), "WALMART_ACTOR_INVALID"),
        (lambda e: e["contract"].__setitem__("mutating", False), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e["auth"].__setitem__("kid", "someone-else"), "WALMART_SIGNATURE_KEY_UNKNOWN"),
        (lambda e: e["auth"].__setitem__("request_id", "f" * 32), "WALMART_SIGNATURE_INVALID"),
        (lambda e: e["auth"].__setitem__("expires_at", NOW + 500), "WALMART_SIGNATURE_TTL_INVALID"),
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


def test_freshness_window_and_replay(signer):
    replay = MemoryReplayStore()
    clock = {"now": NOW}
    verifier = _verifier(signer, clock=lambda: clock["now"], replay=replay)
    event = _event(signer, "wfs_inventory", params={"limit": 1}, request_id="a" * 32)
    assert verifier.verify(event).request_id == "a" * 32
    # Same signed request again within its lifetime: replay.
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_REPLAYED"):
        verifier.verify(event)
    # Different request id, same everything else: fine (a fresh signature).
    assert verifier.verify(
        _event(signer, "wfs_inventory", params={"limit": 1}, request_id="b" * 32)
    )
    # Expired.
    clock["now"] = NOW + 121
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_EXPIRED"):
        verifier.verify(_event(signer, "wfs_inventory", params={"limit": 1}, request_id="c" * 32))
    # Issued too far in the future (server clock ahead by more than the tolerance).
    clock["now"] = NOW
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_EXPIRED"):
        verifier.verify(
            _event(
                signer,
                "wfs_inventory",
                params={"limit": 1},
                issued_at=NOW + 61,
                request_id="d" * 32,
            )
        )
    # A forged request must not occupy the replay cache.
    forged = _event(signer, "wfs_inventory", params={"limit": 1}, request_id="e" * 32)
    forged["params"] = {"limit": 2}
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_INVALID"):
        verifier.verify(forged)
    assert verifier.verify(
        _event(signer, "wfs_inventory", params={"limit": 1}, request_id="e" * 32)
    )


def test_cross_instance_replay_is_refused_by_a_shared_store(signer, tmp_path):
    """Two cold instances of the same function share one CFS directory: one winner."""
    shared = tmp_path / "cfs"
    shared.mkdir()
    instance_a = _verifier(signer, replay=FileReplayStore(shared))
    instance_b = _verifier(signer, replay=FileReplayStore(shared))
    event = _event(signer, "wfs_inbound_preview", body=_preview_body(), approval_ref="t:1")
    assert instance_a.verify(event).request_id == "0" * 32
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_REPLAYED"):
        instance_b.verify(event)
    # Memory stores in two instances would each accept it once: that is why the executor
    # refuses writes unless the store is shared.
    mem_a = _verifier(signer, replay=MemoryReplayStore())
    mem_b = _verifier(signer, replay=MemoryReplayStore())
    assert mem_a.verify(event) and mem_b.verify(event)
    assert not mem_a.shared_replay and instance_a.shared_replay
    body = _preview_body()
    event2 = _event(
        signer, "wfs_inbound_preview", body=body, approval_ref="t:1", request_id="5" * 32
    )
    denied = _executor(mem_a, FakeTransport(), max_risk="write").handle(event2)
    assert denied == {"success": False, "status": "WALMART_REPLAY_STORE_REQUIRED"}
    ok = _executor(
        _verifier(signer, replay=FileReplayStore(shared)), FakeTransport(), max_risk="write"
    )
    assert ok.handle(event2)["success"] is True
    # Reads keep working on a memory store (no cross-instance requirement).
    read = _event(signer, "wfs_inventory", params={"limit": 1}, request_id="6" * 32)
    assert _executor(mem_b, FakeTransport()).handle(read)["success"] is True
    # Marker files hold the expiry; a missing directory is refused up front.
    assert sorted(p.name for p in shared.iterdir())[0].startswith("szzsbj-test.")
    with pytest.raises(ContractError, match="WALMART_REPLAY_STORE_UNAVAILABLE"):
        FileReplayStore(tmp_path / "missing")


def test_redis_replay_store_uses_set_nx():
    class FakeRedis:
        def __init__(self):
            self.keys: dict[str, int] = {}

        def set(self, key, value, nx=False, px=None):
            if nx and key in self.keys:
                return None
            self.keys[key] = px
            return True

    store = RedisReplayStore(FakeRedis())
    assert store.shared
    assert store.claim("szzsbj-test", "a" * 32, NOW + 120, NOW) is True
    assert store.claim("szzsbj-test", "a" * 32, NOW + 120, NOW) is False

    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    with pytest.raises(ContractError, match="WALMART_REPLAY_STORE_UNAVAILABLE"):
        RedisReplayStore(Broken()).claim("szzsbj-test", "b" * 32, NOW + 120, NOW)


def test_public_key_env_parsing_and_rotation():
    kwargs = {"bound_store": STORE, "bound_function": FUNCTION, "clock": lambda: NOW}
    for raw in ("not json", json.dumps({"k": "AAAA"}), "{}", "[]"):
        with pytest.raises(ContractError, match="WALMART_VERIFY_KEYS_INVALID"):
            ContractVerifier.from_env_json(raw, **kwargs)
    old = ContractSigner.generate(kid="rotation-a", registry=reviewed_registry())
    new = ContractSigner.generate(kid="rotation-b", registry=reviewed_registry())
    # Rotation: the cloud holds both public keys; either signer verifies; an unknown kid does not.
    both = ContractVerifier.from_env_json(
        json.dumps({"rotation-a": old.public_key_b64(), "rotation-b": new.public_key_b64()}),
        **kwargs,
    )
    assert both.verify(_event(old, "wfs_inventory", params={"limit": 1}, request_id="1" * 32))
    assert both.verify(_event(new, "wfs_inventory", params={"limit": 1}, request_id="2" * 32))
    only_new = ContractVerifier.from_env_json(
        json.dumps({"rotation-b": new.public_key_b64()}), **kwargs
    )
    with pytest.raises(ContractError, match="WALMART_SIGNATURE_KEY_UNKNOWN"):
        only_new.verify(_event(old, "wfs_inventory", params={"limit": 1}, request_id="3" * 32))


def test_pem_file_roundtrip(tmp_path, signer):
    pem = tmp_path / "k.pem"
    pem.write_bytes(signer.private_pem())
    loaded = ContractSigner.from_pem_file(pem, kid=signer.kid, registry=reviewed_registry())
    assert loaded.public_key_b64() == signer.public_key_b64()
    assert "BEGIN" not in repr(loaded) and "contracts=" in repr(loaded)
    with pytest.raises(ContractError, match="WALMART_SIGNING_KEY_UNAVAILABLE"):
        ContractSigner.from_pem_file(
            tmp_path / "missing.pem", kid="x-y-z", registry=reviewed_registry()
        )
    (tmp_path / "bad.pem").write_text("nope")
    with pytest.raises(ContractError, match="WALMART_SIGNING_KEY_INVALID"):
        ContractSigner.from_pem_file(
            tmp_path / "bad.pem", kid="x-y-z", registry=reviewed_registry()
        )


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
    assert result["request_id"] == "0" * 32 and result["risk"] == "read"
    assert result["data"] == {"elements": {"inventory": []}} and result["provider_error"] is None
    store, request = transport.calls[0]
    assert store == STORE and request.path == "/v3/fulfillment/inbound-shipments"
    assert request.query == {"fromCreatedDate": 1, "toCreatedDate": 2, "limit": 50}


def test_v3_new_contract_needs_only_a_registry_entry():
    """Adding an operation to the server registry is enough: no cloud env change.

    The cloud function here has no catalog knowledge of ``brand_new_report`` at all.
    """
    new_op = Operation(
        key="brand_new_report",
        method="GET",
        path="/v3/reports/brand-new",
        fields=(Field("limit", "query", kind="integer", maximum=50),),
        enabled=True,
        family="reports",
        permission="action:walmart:reports:read",
    )
    registry = ContractRegistry(
        (*(reviewed_registry().get(k) for k in reviewed_registry().keys()), new_op)
    )
    signer = ContractSigner.generate(kid="szzsbj-test", registry=registry)
    verifier = _verifier(signer)
    event = _event(signer, "brand_new_report", params={"limit": 5}, registry=registry)
    transport = FakeTransport()
    assert _executor(verifier, transport).handle(event)["success"] is True
    assert transport.calls[0][1].path == "/v3/reports/brand-new"
    # ...and the contract's own schema is still enforced on the cloud side.
    over = _event(
        signer, "brand_new_report", params={"limit": 50}, registry=registry, request_id="9" * 32
    )
    over["params"] = {"limit": 500}
    over["auth"] = signer.sign(
        store_code=STORE,
        function_name=FUNCTION,
        contract=over["contract"],
        method="GET",
        path=over["path"],
        params={"limit": 500},
        body=None,
        response_kind="json",
        actor=dict(ACTOR),
        approval_ref=None,
        issued_at=NOW,
        request_id="8" * 32,
    )
    assert (
        _executor(_verifier(signer), FakeTransport()).handle(over)["status"]
        == "WALMART_FIELD_INVALID"
    )


def test_v3_write_needs_write_ceiling_and_approval(signer, verifier):
    body = _preview_body()
    denied = _executor(_verifier(signer), FakeTransport(), max_risk="read").handle(
        _event(signer, "wfs_inbound_preview", body=body, approval_ref="wfs-ticket:1")
    )
    assert denied == {"success": False, "status": "WALMART_RISK_CEILING_DENIED"}
    no_approval = _executor(_verifier(signer), FakeTransport(), max_risk="write").handle(
        _event(signer, "wfs_inbound_preview", body=body, request_id="1" * 32)
    )
    assert no_approval["status"] == "WALMART_WRITE_APPROVAL_REQUIRED"
    transport = FakeTransport(data={"shipmentPlans": []})
    ok = _executor(_verifier(signer), transport, max_risk="write").handle(
        _event(
            signer,
            "wfs_inbound_preview",
            body=body,
            approval_ref="wfs-ticket:1",
            request_id="2" * 32,
        )
    )
    assert ok["success"] is True and ok["risk"] == "write" and transport.calls[0][1].body == body
    # The very same signed request again (any instance): refused before any transport call.
    replayed = _executor(_verifier(signer), FakeTransport(), max_risk="write").handle(
        _event(
            signer,
            "wfs_inbound_preview",
            body=body,
            approval_ref="wfs-ticket:1",
            request_id="2" * 32,
        )
    )
    assert replayed == {"success": False, "status": "WALMART_SIGNATURE_REPLAYED"}


def test_non_get_marked_read_only_is_still_a_write_in_the_cloud():
    """Reviewer requirement 3: a POST with ``mutating=False`` does not pass a read ceiling."""
    sneaky = Operation(
        key="sneaky_post",
        method="POST",
        path="/v3/items/search",
        fields=(),
        has_body=True,
        enabled=True,
        mutating=False,
        family="marketplace",
        permission="action:walmart:marketplace:read",
    )
    registry = ContractRegistry((sneaky,))
    signer = ContractSigner.generate(kid="szzsbj-test", registry=registry)
    assert risk_for("POST", "sneaky_post") == "write"
    event = _event(signer, "sneaky_post", body={"q": "x"}, registry=registry)
    assert event["risk"] == "write"
    result = _executor(_verifier(signer), FakeTransport(), max_risk="read").handle(event)
    assert result["status"] == "WALMART_RISK_CEILING_DENIED"
    forged = dict(event, risk="read")
    assert _executor(_verifier(signer), FakeTransport(), max_risk="read").handle(forged)[
        "status"
    ] == ("WALMART_RISK_MISMATCH")


def test_v3_provider_error_is_returned_not_raised(signer):
    transport = FakeTransport(status=400, data={"errors": [{"code": "INVALID"}]})
    result = _executor(_verifier(signer), transport, max_risk="write").handle(
        _event(signer, "wfs_inbound_preview", body=_preview_body(), approval_ref="wfs-ticket:1")
    )
    assert result["success"] is True and result["status_code"] == 400
    assert result["data"] is None and result["provider_error"] == {"errors": [{"code": "INVALID"}]}


def test_v3_event_shape_rejections(signer):
    executor = _executor(_verifier(signer), FakeTransport())
    event = _event(signer, "wfs_inventory", params={"limit": 1})
    bad_actor = copy.deepcopy(event)
    bad_actor["actor"] = {"kind": "root", "uid": "x"}
    assert executor.handle(bad_actor)["status"] == "WALMART_ACTOR_INVALID"
    extra = copy.deepcopy(event)
    extra["api_key"] = "wfs_inventory"
    assert executor.handle(extra)["status"] == "WALMART_EVENT_INVALID"
    headers = copy.deepcopy(event)
    headers["headers"] = {"Authorization": "x"}
    assert executor.handle(headers)["status"] == "WALMART_EVENT_INVALID"
    other_store = WalmartCloudExecutor(
        registry=ContractRegistry(()),
        store_allowlist=frozenset({"HK2613"}),
        policy=DenyAllPolicy(),
        transport=FakeTransport(),
        verifier=_verifier(signer),
    )
    assert other_store.handle(event)["status"] == "WALMART_STORE_NOT_AUTHORIZED"


def test_legacy_v1_keeps_its_own_allowlist_and_v3_is_off_without_keys(signer):
    """Reviewer requirement 5: v1/v2 gain nothing from the reviewed registry."""
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
    not_approved = dict(v1, api_key="inbound_shipments", path="/v3/fulfillment/inbound-shipments")
    not_approved["query"] = {"fromCreatedDate": 1, "toCreatedDate": 2}
    assert legacy.handle(not_approved)["status"] == "WALMART_OPERATION_NOT_APPROVED"
    # Even a v3-enabled function keeps the legacy allowlist for v1 events.
    mixed = WalmartCloudExecutor(
        registry=wfs_registry(approved_keys=frozenset({"wfs_inventory"})),
        store_allowlist=frozenset({STORE}),
        policy=AllowReads(),
        transport=FakeTransport(),
        verifier=_verifier(signer),
    )
    assert mixed.handle(not_approved)["status"] == "WALMART_OPERATION_NOT_APPROVED"
    assert mixed.handle(v1)["success"] is True


# --- bridge / client -------------------------------------------------------------------


class RecordingInvoker:
    def __init__(self, executor: WalmartCloudExecutor) -> None:
        self.executor = executor
        self.events: list[dict[str, Any]] = []

    def invoke(self, payload):
        self.events.append(copy.deepcopy(payload))
        return self.executor.handle(payload)


class _ClientGateway:
    def __init__(self, bridge: ProtectedScfBridge) -> None:
        self._bridge = bridge

    def execute(self, *, store_code, request, approval_ref, actor=None):
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


def test_bridge_v3_end_to_end_through_client(signer, live_verifier):
    transport = FakeTransport(data={"elements": {"inventory": [{"sku": "A"}]}})
    invoker = RecordingInvoker(_executor(live_verifier, transport))
    bridge = ProtectedScfBridge(invoker, version=3, signer=signer, function_name=FUNCTION)
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
    assert sent["function_name"] == FUNCTION and sent["risk"] == "read"
    assert sent["contract"]["key"] == "wfs_inventory" and sent["auth"]["kid"] == signer.kid
    assert sent["auth"]["expires_at"] - sent["auth"]["issued_at"] == 120
    # The same client sending the same call again gets a fresh request_id (no replay).
    assert client.call(STORE, "wfs_inventory", params={"limit": 1}, actor=ACTOR).ok
    assert invoker.events[1]["auth"]["request_id"] != sent["auth"]["request_id"]


def test_bridge_v3_requires_signer_function_and_actor_and_checks_echo(signer, live_verifier):
    invoker = RecordingInvoker(_executor(live_verifier, FakeTransport()))
    with pytest.raises(GatewayRejected, match="WALMART_SIGNER_REQUIRED"):
        ProtectedScfBridge(invoker, version=3)
    with pytest.raises(GatewayRejected, match="WALMART_SIGNER_REQUIRED"):
        ProtectedScfBridge(invoker, version=3, signer=signer)
    bridge = ProtectedScfBridge(invoker, version=3, signer=signer, function_name=FUNCTION)
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
                "request_id": payload["auth"]["request_id"],
                "contract_sha256": "0" * 64,
                "data": {},
            }

    with pytest.raises(GatewayRejected, match="WALMART_GATEWAY_SCOPE_MISMATCH"):
        ProtectedScfBridge(WrongEcho(), version=3, signer=signer, function_name=FUNCTION).execute(
            store_code=STORE, request=request, approval_ref=None, actor=ACTOR
        )


def test_bridge_v3_label_pdf_and_provider_error(signer, live_verifier):
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
                verifier=live_verifier,
                max_risk="write",
            )
        ),
        version=3,
        signer=signer,
        function_name=FUNCTION,
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
            _executor(
                live_verifier, FakeTransport(status=404, data={"errors": []}), max_risk="write"
            )
        ),
        version=3,
        signer=signer,
        function_name=FUNCTION,
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
    monkeypatch.setenv(scf_runtime.FUNCTION_NAME_ENV, FUNCTION)
    assert scf_runtime._verifier_from_env(STORE) is None
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
    monkeypatch.delenv(scf_runtime.REPLAY_DIR_ENV, raising=False)
    monkeypatch.delenv(scf_runtime.REPLAY_REDIS_ENV, raising=False)
    scf_runtime._REPLAY_CACHE.clear()
    verifier = scf_runtime._verifier_from_env(STORE)
    assert verifier is not None and not verifier.shared_replay  # memory only: reads only
    monkeypatch.setenv(scf_runtime.REPLAY_DIR_ENV, str(_SHARED_DIR.path))
    assert scf_runtime._verifier_from_env(STORE).shared_replay
    # Tencent's own SCF_FUNCTIONNAME is the fallback for the bound function name.
    monkeypatch.delenv(scf_runtime.FUNCTION_NAME_ENV)
    monkeypatch.setenv("SCF_FUNCTIONNAME", FUNCTION)
    assert scf_runtime._function_name_from_env() == FUNCTION

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
