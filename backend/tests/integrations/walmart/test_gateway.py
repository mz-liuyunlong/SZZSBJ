"""WalmartGateway: one business entry point with server-side authorization and audit."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contract_signing import (
    ContractSigner,
    ContractVerifier,
    FileReplayStore,
)
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.gateway import (
    Actor,
    CallRecord,
    FileOutbox,
    GatewayError,
    InMemoryWriteLedger,
    MemoryOutbox,
    WalmartGateway,
    reviewed_store_id_map,
    write_outcome,
)
from app.integrations.walmart.pagination import PageContract
from app.integrations.walmart.scf_bridge import ProtectedScfBridge
from app.integrations.walmart.unified_api import (
    WFS_CANCEL_PERMISSION,
    WFS_WRITE_PERMISSION,
    reviewed_registry,
)

STORE = "HK2614"
OTHER = "HK2613"


class ScriptedTransport:
    """Answers by (store, path) -> list of (status, data) consumed in order."""

    def __init__(self) -> None:
        self.answers: dict[tuple[str, str], list[tuple[int, Any]]] = {}
        self.calls: list[tuple[str, str, dict[str, Any], Any]] = []

    def push(self, store: str, path: str, status: int, data: Any) -> None:
        self.answers.setdefault((store, path), []).append((status, data))

    def execute(self, *, store_code: str, request: Any) -> tuple[int, Any]:
        self.calls.append((store_code, request.path, dict(request.query), request.body))
        queue = self.answers.get((store_code, request.path))
        if not queue:
            return 200, {"ok": True}
        return queue.pop(0)


class _Gateway:
    def __init__(self, bridges: dict[str, ProtectedScfBridge]) -> None:
        self._bridges = bridges

    def execute(self, *, store_code, request, approval_ref, actor=None):
        reply = self._bridges[store_code].execute(
            store_code=store_code, request=request, approval_ref=approval_ref, actor=actor
        )
        return WalmartResult(
            status_code=reply.status_code,
            data=reply.data,
            provider_error=reply.provider_error,
            content_type=reply.content_type,
            pdf=reply.pdf,
        )


class _Invoker:
    def __init__(self, executor: WalmartCloudExecutor) -> None:
        self._executor = executor

    def invoke(self, payload):
        return self._executor.handle(payload)


@pytest.fixture
def world(tmp_path):
    signer = ContractSigner.generate(kid="gw-test", registry=reviewed_registry())
    transport = ScriptedTransport()
    bridges = {}
    for store in (STORE, OTHER):
        function = f"szzsbj-walmart-{store.lower()}-executor"
        replay_dir = tmp_path / f"replay-{store}"
        replay_dir.mkdir()
        verifier = ContractVerifier.from_env_json(
            json.dumps({signer.kid: signer.public_key_b64()}),
            bound_store=store,
            bound_function=function,
            replay=FileReplayStore(replay_dir),
        )
        bridges[store] = ProtectedScfBridge(
            _Invoker(
                WalmartCloudExecutor(
                    registry=ContractRegistry(()),
                    store_allowlist=frozenset({store}),
                    policy=None,  # type: ignore[arg-type]  # v3 never consults it
                    transport=transport,
                    verifier=verifier,
                    max_risk="write",
                )
            ),
            version=3,
            signer=signer,
            function_name=function,
        )
    client = WalmartClient(
        reviewed_registry(),
        allowed_stores=frozenset({STORE, OTHER}),
        configured_stores=frozenset({STORE, OTHER}),
        gateway=_Gateway(bridges),
    )
    records: list[CallRecord] = []
    gateway = WalmartGateway(client, audit=records.append, ledger=InMemoryWriteLedger())
    return gateway, transport, records


def _user(*permissions: str, stores: set[str] | None = None) -> Actor:
    return Actor(
        kind="user",
        uid="42",
        permissions=frozenset(permissions),
        store_codes=None if stores is None else frozenset(stores),
    )


def test_read_call_authorizes_executes_and_audits(world):
    gateway, transport, records = world
    transport.push(STORE, "/v3/wfs/inventory", 200, {"elements": {"inventory": [{"sku": "A"}]}})
    actor = _user("action:walmart:wfs:read", stores={STORE})
    result = gateway.call(STORE, "wfs_inventory", actor=actor, params={"limit": 1})
    assert result.ok and result.data["elements"]["inventory"][0]["sku"] == "A"
    assert transport.calls == [(STORE, "/v3/wfs/inventory", {"limit": 1}, None)]
    record = records[-1]
    assert record.outcome == "ok" and record.status_code == 200 and record.risk == "read"
    assert record.actor_uid == "42" and record.operation_key == "wfs_inventory"
    assert record.contract_sha256 and record.request_sha256
    assert record.registry_version == reviewed_registry().version()


@pytest.mark.parametrize(
    ("actor", "store", "operation", "approval", "code"),
    [
        (
            _user("action:walmart:feeds:read"),
            STORE,
            "wfs_inventory",
            None,
            "WALMART_PERMISSION_DENIED",
        ),
        (
            _user("action:walmart:wfs:read", stores={OTHER}),
            STORE,
            "wfs_inventory",
            None,
            "WALMART_STORE_NOT_AUTHORIZED",
        ),
        (_user("*"), "CN2502", "wfs_inventory", None, "WALMART_STORE_NOT_AUTHORIZED"),
        (_user("*"), STORE, "not_registered", None, "WALMART_API_NOT_REGISTERED"),
        (
            _user(WFS_WRITE_PERMISSION),
            STORE,
            "wfs_inbound_shipment_cancel",
            "t:1",
            "WALMART_PERMISSION_DENIED",
        ),
        (
            _user(WFS_WRITE_PERMISSION),
            STORE,
            "wfs_inbound_preview",
            None,
            "WALMART_WRITE_APPROVAL_REQUIRED",
        ),
        (_user("*"), STORE, "wfs_inventory", "bad\nref", "WALMART_APPROVAL_INVALID"),
    ],
)
def test_authorization_matrix(world, actor, store, operation, approval, code):
    gateway, transport, records = world
    with pytest.raises(GatewayError) as caught:
        gateway.call(store, operation, actor=actor, approval_ref=approval)
    assert caught.value.code == code
    assert transport.calls == []  # denied before any cloud call
    assert records[-1].outcome == "denied" and records[-1].error_code == code


def test_write_call_with_permission_and_approval(world):
    gateway, transport, records = world
    transport.push(STORE, "/v3/fulfillment/inbound-shipments/PMC-X", 200, {"status": "OK"})
    actor = _user(WFS_CANCEL_PERMISSION, stores={STORE})
    cancel = {"params": {"inboundOrderId": "PMC-X"}, "approval_ref": "wfs-ticket:abc"}
    with pytest.raises(GatewayError, match="WALMART_IDEMPOTENCY_KEY_REQUIRED"):
        gateway.call(STORE, "wfs_inbound_shipment_cancel", actor=actor, **cancel)
    result = gateway.call(
        STORE,
        "wfs_inbound_shipment_cancel",
        actor=actor,
        idempotency_key="cancel:PMC-X:1",
        **cancel,
    )
    assert result.ok
    # Audit before (attempt) and after (ok) the cloud call, both carrying the key.
    assert [r.outcome for r in records[-2:]] == ["attempt", "ok"]
    assert all(r.idempotency_key == "cancel:PMC-X:1" for r in records[-2:])
    assert records[-1].risk == "write" and records[-1].approval_ref == "wfs-ticket:abc"
    assert gateway.ledger.status("cancel:PMC-X:1") == "ok"
    # A finished key is never executed twice.
    with pytest.raises(GatewayError, match="WALMART_WRITE_ALREADY_DONE"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-X:1",
            **cancel,
        )
    # Walmart rejecting the write is a result, not an exception.
    transport.push(
        STORE, "/v3/fulfillment/inbound-shipments/PMC-X", 404, {"errors": [{"code": "NF"}]}
    )
    rejected = gateway.call(
        STORE,
        "wfs_inbound_shipment_cancel",
        actor=actor,
        idempotency_key="cancel:PMC-X:2",
        **cancel,
    )
    assert rejected.status_code == 404 and rejected.provider_error == {"errors": [{"code": "NF"}]}
    assert records[-1].outcome == "provider_error" and records[-1].status_code == 404
    assert gateway.ledger.status("cancel:PMC-X:2") == "provider_error"


def test_unknown_write_outcome_blocks_retry_until_reconciled(world):
    gateway, transport, records = world
    actor = _user(WFS_CANCEL_PERMISSION)
    cancel = {"params": {"inboundOrderId": "PMC-Y"}, "approval_ref": "wfs-ticket:y"}
    original = transport.execute

    def crash(**_: Any):
        raise RuntimeError("socket closed")

    transport.execute = crash  # type: ignore[method-assign]
    with pytest.raises(GatewayError):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-Y",
            **cancel,
        )
    assert records[-1].outcome == "unknown" and gateway.ledger.status("cancel:PMC-Y") == "unknown"
    transport.execute = original  # type: ignore[method-assign]
    # Transport is healthy again, but the same business write is refused until reviewed.
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-Y",
            **cancel,
        )
    assert transport.calls == []
    # Reconcile (after a read-back) decides; "failed" allows one more identical attempt.
    gateway.ledger.resolve("cancel:PMC-Y", outcome="failed", note="read-back: shipment still open")
    assert gateway.call(
        STORE, "wfs_inbound_shipment_cancel", actor=actor, idempotency_key="cancel:PMC-Y", **cancel
    ).ok
    # ok is terminal: a reconcile job can never reopen a finished write (round 3).
    with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
        gateway.ledger.resolve("cancel:PMC-Y", outcome="failed", note="test")
    # Same key with a different payload is not a retry.
    transport.push(STORE, "/v3/fulfillment/inbound-shipments/PMC-W", 400, {"errors": []})
    gateway.call(
        STORE,
        "wfs_inbound_shipment_cancel",
        actor=actor,
        params={"inboundOrderId": "PMC-W"},
        approval_ref="wfs-ticket:w",
        idempotency_key="cancel:PMC-W",
    )
    assert gateway.ledger.status("cancel:PMC-W") == "provider_error"
    with pytest.raises(GatewayError, match="WALMART_WRITE_PAYLOAD_CHANGED"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            params={"inboundOrderId": "PMC-Z"},
            approval_ref="wfs-ticket:w",
            idempotency_key="cancel:PMC-W",
        )
    assert isinstance(gateway.ledger, InMemoryWriteLedger)


def test_system_actor_is_limited_to_its_operation_allowlist(world):
    gateway, transport, records = world
    worker = Actor.system(
        "pmc-wfs-creation", operations={"inbound_shipments", "wfs_inbound_shipment_create"}
    )
    with pytest.raises(GatewayError, match="WALMART_PERMISSION_DENIED"):
        gateway.call(STORE, "wfs_inventory", actor=worker)
    transport.push(
        STORE,
        "/v3/fulfillment/inbound-shipments",
        200,
        {"payload": [], "headers": {"totalCount": 0}},
    )
    assert gateway.call(
        STORE, "inbound_shipments", actor=worker, params={"fromCreatedDate": 1, "toCreatedDate": 2}
    ).ok
    with pytest.raises(GatewayError, match="WALMART_ACTOR_INVALID"):
        Actor.system("nothing", operations=())


def test_invalid_params_do_not_reach_the_cloud(world):
    gateway, transport, records = world
    with pytest.raises(GatewayError, match="WALMART_PARAM_NOT_ALLOWED"):
        gateway.call(STORE, "wfs_inventory", actor=_user("*"), params={"evil": 1})
    assert transport.calls == [] and records[-1].outcome == "gateway_error"


def test_pages_collects_all_pages_with_actor(world):
    gateway, transport, records = world
    path = "/v3/fulfillment/inbound-shipment-items"
    transport.push(
        STORE, path, 200, {"payload": {"items": [{"n": 1}, {"n": 2}]}, "headers": {"totalCount": 3}}
    )
    transport.push(
        STORE, path, 200, {"payload": {"items": [{"n": 3}]}, "headers": {"totalCount": 3}}
    )
    contract = PageContract(
        operation="inbound_shipment_items",
        items_path=("payload", "items"),
        mode="offset",
        total_path=("headers", "totalCount"),
    )
    rows = gateway.pages(
        STORE,
        actor=_user("action:walmart:wfs:read"),
        contract=contract,
        params={"shipmentId": "SHP1"},
        page_size=2,
    )
    assert [row["n"] for row in rows] == [1, 2, 3]
    assert [call[2]["offset"] for call in transport.calls] == [0, 2]
    assert records[-1].outcome == "ok" and records[-1].operation_key == "inbound_shipment_items"
    with pytest.raises(GatewayError, match="WALMART_PERMISSION_DENIED"):
        gateway.pages(STORE, actor=_user("action:walmart:feeds:read"), contract=contract)


def test_call_many_isolates_store_failures(world):
    gateway, transport, _ = world
    transport.push(OTHER, "/v3/wfs/inventory", 200, {"elements": {"inventory": []}})
    results = gateway.call_many(
        [STORE, OTHER, STORE],
        "wfs_inventory",
        actor=_user("action:walmart:wfs:read", stores={OTHER}),
        params={"limit": 1},
    )
    assert set(results) == {STORE, OTHER}
    assert (
        isinstance(results[STORE], GatewayError)
        and results[STORE].code == "WALMART_STORE_NOT_AUTHORIZED"
    )
    assert isinstance(results[OTHER], WalmartResult) and results[OTHER].ok


def test_unknown_transport_failure_is_recorded_as_unknown(world):
    gateway, transport, records = world

    def boom(**_: Any):
        raise RuntimeError("socket closed")

    transport.execute = boom  # type: ignore[method-assign]
    with pytest.raises(GatewayError, match="WALMART_GATEWAY_REJECTED"):
        gateway.call(STORE, "wfs_inventory", actor=_user("*"), params={"limit": 1})
    # The executor turned the crash into WALMART_EXECUTOR_FAILURE and the bridge into a
    # rejection; the business side sees a stable code and an "unknown" audit outcome.
    assert records[-1].outcome == "unknown"


def test_without_a_ledger_every_write_is_refused_but_reads_work(world):
    gateway, transport, records = world
    bare = WalmartGateway(gateway._client, audit=records.append)  # noqa: SLF001
    transport.push(STORE, "/v3/wfs/inventory", 200, {"elements": {"inventory": []}})
    assert bare.call(STORE, "wfs_inventory", actor=_user("*"), params={"limit": 1}).ok
    with pytest.raises(GatewayError, match="WALMART_LEDGER_REQUIRED"):
        bare.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=_user("*"),
            params={"inboundOrderId": "PMC-X"},
            approval_ref="wfs-ticket:abc",
            idempotency_key="cancel:PMC-X",
        )
    assert transport.calls[-1][1] == "/v3/wfs/inventory"  # the write never left


def test_audit_failure_before_a_write_refuses_it_and_closes_the_ledger(world, caplog):
    gateway, transport, records = world
    state = {"fail": True}

    def flaky(record: CallRecord) -> None:
        if state["fail"]:
            raise OSError("disk full")
        records.append(record)

    gateway._audit = flaky  # noqa: SLF001 - exercising the guard
    cancel = {"params": {"inboundOrderId": "PMC-A"}, "approval_ref": "wfs-ticket:a"}
    with caplog.at_level("INFO", logger="szzsbj.walmart.gateway"):
        with pytest.raises(GatewayError, match="WALMART_AUDIT_UNAVAILABLE"):
            gateway.call(
                STORE,
                "wfs_inbound_shipment_cancel",
                actor=_user("*"),
                idempotency_key="cancel:PMC-A",
                **cancel,
            )
    assert transport.calls == []  # intent could not be recorded -> nothing sent
    assert gateway.ledger.status("cancel:PMC-A") == "failed"
    assert gateway.pending_audit >= 1 and "walmart_call store=HK2614" in caplog.text
    # Sink back: the outbox flushes first, then the write proceeds and is fully recorded.
    state["fail"] = False
    transport.push(STORE, "/v3/fulfillment/inbound-shipments/PMC-A", 200, {"status": "OK"})
    assert gateway.call(
        STORE,
        "wfs_inbound_shipment_cancel",
        actor=_user("*"),
        idempotency_key="cancel:PMC-A",
        **cancel,
    ).ok
    assert gateway.pending_audit == 0
    outcomes = [r.outcome for r in records]
    assert outcomes[-2:] == ["attempt", "ok"] and "denied" in outcomes  # replayed from the outbox


def test_audit_failure_after_a_read_keeps_the_record_and_blocks_writes_until_flushed(world):
    gateway, transport, records = world
    state = {"fail": False}

    def flaky(record: CallRecord) -> None:
        if state["fail"]:
            raise OSError("disk full")
        records.append(record)

    gateway._audit = flaky  # noqa: SLF001
    state["fail"] = True
    transport.push(STORE, "/v3/wfs/inventory", 200, {"elements": {"inventory": []}})
    assert gateway.call(STORE, "wfs_inventory", actor=_user("*"), params={"limit": 1}).ok
    assert gateway.pending_audit == 1  # the read happened; its evidence waits in the outbox
    with pytest.raises(GatewayError, match="WALMART_AUDIT_UNAVAILABLE"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=_user("*"),
            params={"inboundOrderId": "PMC-B"},
            approval_ref="wfs-ticket:b",
            idempotency_key="cancel:PMC-B",
        )
    assert gateway.ledger.status("cancel:PMC-B") is None  # refused before any ledger claim
    state["fail"] = False
    transport.push(STORE, "/v3/wfs/inventory", 200, {"elements": {"inventory": []}})
    assert gateway.call(STORE, "wfs_inventory", actor=_user("*"), params={"limit": 1}).ok
    assert gateway.pending_audit == 0
    # Outbox replayed in order (the read, then the refused write), then the new read.
    assert [r.operation_key for r in records[-3:]] == [
        "wfs_inventory",
        "wfs_inbound_shipment_cancel",
        "wfs_inventory",
    ]
    assert records[-2].outcome == "denied"


def test_persistent_ledger_errors_surface_as_stable_codes(world):
    gateway, transport, records = world

    class Refusing:
        def begin(self, key, **fields):
            raise RuntimeError("WALMART_WRITE_PENDING_REVIEW")

        def finish(self, *a, **k):
            raise AssertionError("not opened")

        def status(self, key):
            return "unknown"

        def resolve(self, *a, **k):
            pass

    gateway._ledger = Refusing()  # noqa: SLF001
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=_user("*"),
            params={"inboundOrderId": "PMC-C"},
            approval_ref="wfs-ticket:c",
            idempotency_key="cancel:PMC-C",
        )
    assert records[-1].outcome == "denied" and transport.calls == []


# --- construction from the server environment --------------------------------------------


class _Identity:
    def get_identity(self):  # pragma: no cover - never called without a real invocation
        raise AssertionError("no network in tests")


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (200, "ok"),
        (201, "ok"),
        (400, "provider_error"),
        (404, "provider_error"),
        (408, "unknown"),
        (429, "unknown"),
        (500, "unknown"),
        (502, "unknown"),
        (503, "unknown"),
    ],
)
def test_write_outcome_classification(status, outcome):
    assert write_outcome(status) == outcome


@pytest.mark.parametrize("status", [500, 503, 429])
def test_http_5xx_on_a_write_is_unknown_until_read_back(world, status):
    """Round 3 (reviewer P0): a 5xx/429 answer may still have been applied by Walmart.

    The key must stay open (``unknown``) and refuse a second POST until reconciliation
    resolves it; it must never be recorded as a definitive ``provider_error``.
    """
    gateway, transport, records = world
    actor = _user(WFS_CANCEL_PERMISSION, stores={STORE})
    cancel = {"params": {"inboundOrderId": "PMC-5XX"}, "approval_ref": "wfs-ticket:5xx"}
    key = f"cancel:PMC-5XX:{status}"
    transport.push(
        STORE, "/v3/fulfillment/inbound-shipments/PMC-5XX", status, {"errors": [{"code": "X"}]}
    )
    result = gateway.call(
        STORE, "wfs_inbound_shipment_cancel", actor=actor, idempotency_key=key, **cancel
    )
    assert result.status_code == status and not result.ok
    assert records[-1].outcome == "unknown" and records[-1].error_code == f"WALMART_HTTP_{status}"
    assert gateway.ledger.status(key) == "unknown"
    sent = len(transport.calls)
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        gateway.call(
            STORE, "wfs_inbound_shipment_cancel", actor=actor, idempotency_key=key, **cancel
        )
    assert len(transport.calls) == sent  # nothing left the server
    # Read-back says it was applied: ok, terminal.
    gateway.ledger.resolve(key, outcome="ok", note="read-back: shipment cancelled")
    with pytest.raises(GatewayError, match="WALMART_WRITE_ALREADY_DONE"):
        gateway.call(
            STORE, "wfs_inbound_shipment_cancel", actor=actor, idempotency_key=key, **cancel
        )
    with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
        gateway.ledger.resolve(key, outcome="failed", note="never from ok")


def test_ledger_state_machine_is_enforced():
    ledger = InMemoryWriteLedger()
    fields = {
        "store_code": STORE,
        "operation_key": "wfs_inbound_shipment_cancel",
        "actor_uid": "42",
        "approval_ref": "t:1",
        "request_sha256": "a" * 64,
    }
    ledger.begin("k", **fields)
    # finish only accepts known outcomes and only from attempting
    with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
        ledger.finish("k", outcome="done", status_code=200, error_code=None)
    ledger.finish("k", outcome="failed", status_code=None, error_code="X")
    with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
        ledger.finish("k", outcome="ok", status_code=200, error_code=None)
    # re-claim must be the same store / operation / payload
    with pytest.raises(GatewayError, match="WALMART_LEDGER_KEY_REUSED"):
        ledger.begin("k", **{**fields, "store_code": OTHER})
    with pytest.raises(GatewayError, match="WALMART_LEDGER_KEY_REUSED"):
        ledger.begin("k", **{**fields, "operation_key": "wfs_inbound_shipment_create"})
    with pytest.raises(GatewayError, match="WALMART_WRITE_PAYLOAD_CHANGED"):
        ledger.begin("k", **{**fields, "request_sha256": "b" * 64})
    ledger.begin("k", **fields)
    assert ledger.entries["k"]["attempts"] == 2
    ledger.finish("k", outcome="ok", status_code=201, error_code=None)
    # ok is terminal for every path
    for outcome in ("failed", "provider_error", "ok"):
        with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
            ledger.resolve("k", outcome=outcome, note="x")
    with pytest.raises(GatewayError, match="WALMART_LEDGER_RESOLUTION_INVALID"):
        ledger.resolve("k", outcome="attempting", note="x")
    with pytest.raises(GatewayError, match="WALMART_WRITE_ALREADY_DONE"):
        ledger.begin("k", **fields)


def test_ledger_failure_after_walmart_answered_is_a_stable_code_and_still_audited(world):
    """Round 4 (P3): Walmart already applied the write but ``finish`` blew up. The result
    row must still be written (carrying the ledger failure), the key stays attempting so a
    retry is refused until reconciliation, and the caller gets a stable code."""
    gateway, transport, records = world
    actor = _user(WFS_CANCEL_PERMISSION, stores={STORE})
    cancel = {"params": {"inboundOrderId": "PMC-LF"}, "approval_ref": "wfs-ticket:lf"}
    inner = gateway.ledger

    class FinishBreaks:
        def begin(self, key, **fields):
            inner.begin(key, **fields)

        def finish(self, key, **fields):
            raise ConnectionError("database went away")

        def status(self, key):
            return inner.status(key)

        def resolve(self, key, **fields):
            inner.resolve(key, **fields)

    gateway._ledger = FinishBreaks()  # noqa: SLF001
    transport.push(STORE, "/v3/fulfillment/inbound-shipments/PMC-LF", 200, {"status": "OK"})
    with pytest.raises(GatewayError, match="WALMART_LEDGER_UNAVAILABLE"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-LF",
            **cancel,
        )
    assert transport.calls[-1][1] == "/v3/fulfillment/inbound-shipments/PMC-LF"  # it was sent
    assert [r.outcome for r in records[-2:]] == ["attempt", "ok"]
    assert records[-1].status_code == 200 and records[-1].error_code == "WALMART_LEDGER_UNAVAILABLE"
    assert inner.status("cancel:PMC-LF") == "attempting"
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-LF",
            **cancel,
        )

    # A ledger that raises its own stable code passes it through unchanged.
    class FinishRefuses(FinishBreaks):
        def finish(self, key, **fields):
            raise RuntimeError("WALMART_LEDGER_TRANSITION_INVALID")

    gateway._ledger = FinishRefuses()  # noqa: SLF001
    transport.push(STORE, "/v3/fulfillment/inbound-shipments/PMC-LG", 200, {"status": "OK"})
    with pytest.raises(GatewayError, match="WALMART_LEDGER_TRANSITION_INVALID"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-LG",
            params={"inboundOrderId": "PMC-LG"},
            approval_ref="wfs-ticket:lg",
        )


def test_file_outbox_survives_a_process_restart(world, tmp_path):
    """Round 3 (reviewer P0): audit evidence that could not reach the database must be
    replayed by the *next* process, not lost with the one that produced it."""
    gateway, transport, records = world
    outbox_dir = tmp_path / "audit-outbox"
    state = {"fail": True}

    def flaky(record: CallRecord) -> None:
        if state["fail"]:
            raise OSError("database down")
        records.append(record)

    first = WalmartGateway(
        gateway._client,  # noqa: SLF001
        audit=flaky,
        ledger=InMemoryWriteLedger(),
        outbox=FileOutbox(outbox_dir),
    )
    transport.push(STORE, "/v3/wfs/inventory", 200, {"elements": {"inventory": []}})
    assert first.call(STORE, "wfs_inventory", actor=_user("*"), params={"limit": 1}).ok
    with pytest.raises(GatewayError, match="WALMART_AUDIT_UNAVAILABLE"):
        first.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=_user("*"),
            params={"inboundOrderId": "PMC-R"},
            approval_ref="wfs-ticket:r",
            idempotency_key="cancel:PMC-R",
        )
    assert first.pending_audit == 2 and len(list(outbox_dir.glob("*.json"))) == 2
    del first  # process gone; only the directory remembers
    state["fail"] = False
    before = len(records)
    second = WalmartGateway(
        gateway._client,  # noqa: SLF001
        audit=flaky,
        ledger=InMemoryWriteLedger(),
        outbox=FileOutbox(outbox_dir),
    )
    # Drained on construction, oldest first, and the files are gone only after the sink took them.
    assert second.pending_audit == 0 and list(outbox_dir.glob("*.json")) == []
    replayed = records[before:]
    assert [r.operation_key for r in replayed] == ["wfs_inventory", "wfs_inbound_shipment_cancel"]
    assert replayed[0].outcome == "ok" and replayed[1].outcome == "denied"
    assert replayed[1].idempotency_key == "cancel:PMC-R"


def test_transport_failure_plus_ledger_failure_is_a_stable_code_and_audited(world):
    """P3 (round 5): the cloud call blew up and finish(unknown) could not be recorded. The
    caller still gets a stable code, the unknown audit row is written with the ledger
    failure, and the key stays attempting (a retry is refused until reconciliation)."""
    gateway, transport, records = world
    actor = _user(WFS_CANCEL_PERMISSION, stores={STORE})
    cancel = {"params": {"inboundOrderId": "PMC-TL"}, "approval_ref": "wfs-ticket:tl"}
    inner = gateway.ledger

    class FinishBreaks:
        def begin(self, key, **fields):
            inner.begin(key, **fields)

        def finish(self, key, **fields):
            raise ConnectionError("database went away")

        def status(self, key):
            return inner.status(key)

        def resolve(self, key, **fields):
            inner.resolve(key, **fields)

    def crash(**_: Any):
        raise RuntimeError("socket closed")

    gateway._ledger = FinishBreaks()  # noqa: SLF001
    transport.execute = crash  # type: ignore[method-assign]
    with pytest.raises(GatewayError, match="WALMART_LEDGER_UNAVAILABLE"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-TL",
            **cancel,
        )
    assert records[-1].outcome == "unknown"
    assert records[-1].error_code == "WALMART_LEDGER_UNAVAILABLE"
    assert records[-1].idempotency_key == "cancel:PMC-TL" and records[-2].outcome == "attempt"
    assert inner.status("cancel:PMC-TL") == "attempting"
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        gateway.call(
            STORE,
            "wfs_inbound_shipment_cancel",
            actor=actor,
            idempotency_key="cancel:PMC-TL",
            **cancel,
        )


def _record(n: int) -> CallRecord:
    return CallRecord(
        store_code=STORE,
        operation_key="wfs_inventory",
        risk="read",
        actor_kind="user",
        actor_uid=str(n),
        approval_ref=None,
        idempotency_key=None,
        contract_sha256=None,
        registry_version="v",
        request_sha256="a" * 64,
        status_code=200,
        outcome="ok",
        error_code=None,
        duration_ms=n,
    )


def test_two_workers_draining_one_outbox_deliver_each_record_once(tmp_path):
    """P3 (round 5): drain claims a file by rename before handing it to the sink, so two
    processes sharing the directory never persist the same record twice."""
    import threading

    directory = tmp_path / "shared-outbox"
    producer = FileOutbox(directory)
    for n in range(40):
        producer.append(_record(n))
    assert producer.pending() == 40
    delivered: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def slow_sink(record: CallRecord) -> None:
        time.sleep(0.002)  # widen the window in which both workers look at the same file
        with lock:
            delivered.append(record.duration_ms)

    results: list[bool] = []
    workers = [FileOutbox(directory), FileOutbox(directory)]  # two "processes", one directory

    def worker(outbox: FileOutbox) -> None:
        try:
            barrier.wait(timeout=5)
            results.append(outbox.drain(slow_sink))
        except Exception as error:  # never leave the other thread parked on the barrier
            barrier.abort()
            results.append(error)  # type: ignore[arg-type]

    threads = [threading.Thread(target=worker, args=(w,), daemon=True) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(delivered) == list(range(40)), "a record was delivered twice or lost"
    assert results == [True, True] and producer.pending() == 0
    assert list(directory.iterdir()) == []  # no .json, .claimed or .tmp left behind


def test_outbox_releases_claims_on_sink_failure_and_reclaims_stale_ones(tmp_path):
    directory = tmp_path / "ob"
    outbox = FileOutbox(directory)
    outbox.append(_record(1))

    def refusing(_: CallRecord) -> None:
        raise OSError("still down")

    assert outbox.drain(refusing) is False
    assert [p.suffix for p in directory.iterdir()] == [".json"]  # released, still pending
    # A worker that died mid-drain leaves a .claimed file; after the stale window it is retried.
    (claimed,) = directory.iterdir()
    stale = claimed.with_suffix(".claimed")
    claimed.rename(stale)
    old = time.time() - FileOutbox.STALE_CLAIM_SECONDS - 5
    import os

    os.utime(stale, (old, old))
    assert outbox.pending() == 1
    taken: list[CallRecord] = []
    assert outbox.drain(taken.append) is True and len(taken) == 1
    assert list(directory.iterdir()) == []


def test_file_outbox_keeps_records_the_sink_rejects(tmp_path):
    outbox = FileOutbox(tmp_path / "ob")
    record = CallRecord(
        store_code=STORE,
        operation_key="wfs_inventory",
        risk="read",
        actor_kind="user",
        actor_uid="42",
        approval_ref=None,
        idempotency_key=None,
        contract_sha256=None,
        registry_version="v",
        request_sha256="a" * 64,
        status_code=200,
        outcome="ok",
        error_code=None,
        duration_ms=1,
    )
    outbox.append(record)
    outbox.append(record)

    def refusing(_: CallRecord) -> None:
        raise OSError("still down")

    assert outbox.drain(refusing) is False and outbox.pending() == 2
    taken: list[CallRecord] = []
    assert outbox.drain(taken.append) is True and outbox.pending() == 0
    assert taken == [record, record]


def _env(tmp_path, protocol: str, **extra: str) -> dict[str, str]:
    signer = ContractSigner.generate(kid="szzsbj-2026-10", registry=reviewed_registry())
    pem = tmp_path / "signing.pem"
    pem.write_bytes(signer.private_pem())
    env = {
        "SZZSBJ_WALMART_SCF_PROTOCOL": protocol,
        "SZZSBJ_WALMART_SCF_STORE_ID_MAP": json.dumps(
            {"110711149920800256": STORE, "110711149541688320": OTHER}
        ),
        "SZZSBJ_WALMART_SCF_CVM_ROLE": "role",
        "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN": "qcs::cam::uin/1:roleName/x",
        "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE": str(pem),
        "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_ID": "szzsbj-2026-10",
    }
    env.update(extra)
    return env


def _persistent(tmp_path):
    return {
        "audit": lambda record: None,
        "ledger": _FakePersistentLedger(),
        "outbox": FileOutbox(tmp_path / "outbox"),
    }


class _FakePersistentLedger:
    def begin(self, key, **fields):
        pass

    def finish(self, key, **fields):
        pass

    def status(self, key):
        return None

    def resolve(self, key, **fields):
        pass


def test_from_env_requires_persistent_ledger_and_audit(tmp_path):
    env = _env(tmp_path, "3")
    with pytest.raises(GatewayError, match="WALMART_LEDGER_REQUIRED"):
        WalmartGateway.from_env(environ=env, identity_provider=_Identity())
    with pytest.raises(GatewayError, match="WALMART_LEDGER_REQUIRED"):
        WalmartGateway.from_env(
            environ=env,
            identity_provider=_Identity(),
            audit=lambda r: None,
            ledger=InMemoryWriteLedger(),
        )
    with pytest.raises(GatewayError, match="WALMART_LEDGER_REQUIRED"):
        WalmartGateway.from_env(
            environ=env, identity_provider=_Identity(), ledger=_FakePersistentLedger()
        )
    # Round 3: the audit outbox must be durable too (in-memory evidence dies with the process).
    with pytest.raises(GatewayError, match="WALMART_AUDIT_OUTBOX_REQUIRED"):
        WalmartGateway.from_env(
            environ=env,
            identity_provider=_Identity(),
            audit=lambda r: None,
            ledger=_FakePersistentLedger(),
        )
    with pytest.raises(GatewayError, match="WALMART_AUDIT_OUTBOX_REQUIRED"):
        WalmartGateway.from_env(
            environ=env,
            identity_provider=_Identity(),
            audit=lambda r: None,
            ledger=_FakePersistentLedger(),
            outbox=MemoryOutbox(),
        )


def test_from_env_protocol_3_uses_reviewed_registry_and_signer(tmp_path):
    gateway = WalmartGateway.from_env(
        environ=_env(tmp_path, "3"), identity_provider=_Identity(), **_persistent(tmp_path)
    )
    assert gateway.stores == {STORE, OTHER}
    assert set(gateway.registry.keys()) == set(reviewed_registry().keys())
    assert gateway.registry.get("wfs_inbound_shipment_create").enabled
    missing_key = _env(tmp_path, "3")
    missing_key["SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE"] = str(tmp_path / "nope.pem")
    with pytest.raises(GatewayError, match="WALMART_SIGNING_KEY_UNAVAILABLE"):
        WalmartGateway.from_env(
            environ=missing_key, identity_provider=_Identity(), **_persistent(tmp_path)
        )


def test_from_env_protocol_1_keeps_legacy_allowlists(tmp_path):
    env = _env(
        tmp_path, "1", SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS="wfs_inventory,inbound_shipments"
    )
    gateway = WalmartGateway.from_env(
        environ=env, identity_provider=_Identity(), **_persistent(tmp_path)
    )
    assert set(gateway.registry.keys()) == {"wfs_inventory", "inbound_shipments"}
    assert gateway.registry.get("wfs_inventory").permission == "action:walmart:wfs:read"
    with pytest.raises(GatewayError, match="WALMART_API_NOT_REGISTERED"):
        gateway.authorize(
            actor=_user("*"), store_code=STORE, operation_key="inventory_log", approval_ref=None
        )
    bad = _env(tmp_path, "1")
    with pytest.raises(GatewayError, match="WALMART_GATEWAY_CONFIG_INVALID"):
        WalmartGateway.from_env(environ=bad, identity_provider=_Identity(), **_persistent(tmp_path))


def test_store_id_map_validation():
    assert reviewed_store_id_map({"SZZSBJ_WALMART_SCF_STORE_ID_MAP": json.dumps({"1": STORE})}) == {
        "1": STORE
    }
    for raw in (
        "nope",
        json.dumps({"1": "US9999"}),
        json.dumps({"1": STORE, "2": STORE}),
        json.dumps([1]),
    ):
        with pytest.raises(GatewayError, match="WALMART_SCF_MAPPING_INVALID"):
            reviewed_store_id_map({"SZZSBJ_WALMART_SCF_STORE_ID_MAP": raw})
    assert reviewed_store_id_map({}) == {}
