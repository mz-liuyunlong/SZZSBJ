"""Walmart creation adapter: offline, fake unified gateway, SQLite for settings + events."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.api import ApiError
from app.db.base import Base
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationEvent, WfsCreationTicket
from app.modules.pmc_wfs.creation_worker import DefinitiveRejection
from app.modules.pmc_wfs.gateway import DisabledGateway
from app.modules.pmc_wfs.store_settings_models import WfsStoreSetting
from app.modules.pmc_wfs.walmart_gateway import (
    WalmartScfCreationGateway,
    build_gateway_from_env,
    expected_delivery,
    inbound_order_id,
    reviewed_store_map,
)

ACCOUNT = "primary"
STORE_ID = "110711149920800256"
CODE = "HK2614"
T0 = datetime(2026, 10, 31, 2, 0, tzinfo=UTC)  # 10:00 Beijing
PDF = b"%PDF-1.4 label"
TABLES = (
    "ops_wfs_store_settings",
    "ops_wfs_creation_operations",
    "ops_wfs_creation_tickets",
    "evt_wfs_creation_events",
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


@dataclass
class FakeResult:
    status_code: int
    data: Any = None
    provider_error: Any = None
    pdf: bytes | None = None


class FakeLedger:
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    def begin(self, key: str, **fields: Any) -> None:
        current = self.entries.get(key)
        if current is not None:
            if current["outcome"] in ("attempting", "unknown"):
                raise LedgerBlocked("WALMART_WRITE_PENDING_REVIEW")
            if current["outcome"] == "ok":
                raise LedgerBlocked("WALMART_WRITE_ALREADY_DONE")
        self.entries[key] = {**fields, "outcome": "attempting"}

    def finish(self, key: str, *, outcome: str, status_code: int | None, error_code: str | None):
        self.entries[key].update(outcome=outcome, status_code=status_code, error_code=error_code)

    def status(self, key: str) -> str | None:
        entry = self.entries.get(key)
        return None if entry is None else entry["outcome"]

    def resolve(self, key: str, *, outcome: str, note: str) -> None:
        self.entries[key].update(outcome=outcome, note=note)


class LedgerBlocked(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class FakeGateway:
    """Scripted stand-in for ``WalmartGateway``: reads answer from state, writes mutate it."""

    shipments: dict[str, list[str]] = field(default_factory=dict)  # inboundOrderId -> ids
    items: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # shipmentId -> rows
    calls: list[tuple[str, str, dict[str, Any] | None, Any, str | None, str | None]] = field(
        default_factory=list
    )
    create_status: int = 201
    create_error: Any = None
    read_fail_status: int | None = None
    foreign_record: bool = False
    ledger: FakeLedger = field(default_factory=FakeLedger)
    page_size: int = 50

    def call(
        self,
        store_code: str,
        operation_key: str,
        *,
        actor: Any,
        params: dict[str, Any] | None = None,
        body: Any = None,
        approval_ref: str | None = None,
        idempotency_key: str | None = None,
    ):
        assert actor is ACTOR
        self.calls.append((store_code, operation_key, params, body, approval_ref, idempotency_key))
        if operation_key == "inbound_shipments":
            if self.read_fail_status:
                return FakeResult(self.read_fail_status, provider_error={"errors": ["read down"]})
            order_id = str(params["inboundOrderId"])
            records = [
                {"shipmentId": s, "inboundOrderId": order_id, "status": "PENDING_SHIPMENT_DETAILS"}
                for s in self.shipments.get(order_id, [])
            ]
            if self.foreign_record:
                records.append({"shipmentId": "9999999WFB", "inboundOrderId": "PMC-OTHER"})
            return FakeResult(200, {"headers": {"totalCount": len(records)}, "payload": records})
        if operation_key == "inbound_shipment_items":
            rows = self.items.get(str(params["shipmentId"]), [])
            offset, limit = int(params["offset"]), int(params["limit"])
            return FakeResult(
                200,
                {"headers": {"totalCount": len(rows)}, "payload": rows[offset : offset + limit]},
            )
        assert approval_ref and idempotency_key, operation_key  # every write carries both
        self.ledger.begin(idempotency_key, store_code=store_code, operation_key=operation_key)
        if operation_key == "wfs_inbound_shipment_create":
            if 200 <= self.create_status < 300:
                sid = f"{len(self.calls):07d}WFB"
                self.shipments[body["inboundOrderId"]] = [sid]
                self.items[sid] = [
                    {
                        "sku": item["sku"],
                        "gtin": item["productId"],
                        "itemQty": item["itemQty"],
                        "vendorPackQty": item["vendorPackQty"],
                    }
                    for item in body["orderItems"]
                ]
            result = FakeResult(self.create_status, {"status": "OK"}, self.create_error)
        elif operation_key == "wfs_shipment_label":
            result = FakeResult(200, None, pdf=PDF)
        elif operation_key == "wfs_inbound_preview":
            result = FakeResult(
                200,
                {
                    "payload": [
                        {
                            "previews": [
                                {
                                    "previewType": "inbound",
                                    "preview": [
                                        {
                                            "shipToAddress": {"fcName": "LAX2T"},
                                            "nodeType": "ICC",
                                            "totalNetTransferCharge": 78.3,
                                            "shipmentItems": [
                                                {"vendorSku": "YC00064-1U", "itemQty": 18}
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                },
            )
        else:
            raise AssertionError(operation_key)
        self.ledger.finish(
            idempotency_key,
            outcome="ok" if 200 <= result.status_code < 300 else "provider_error",
            status_code=result.status_code,
            error_code=None,
        )
        return result

    def writes(self) -> list[tuple[str, str, str, Any]]:
        return [(c[0], c[1], c[4], c[3]) for c in self.calls if c[4] is not None]

    def reads(self) -> list[str]:
        return [c[1] for c in self.calls if c[4] is None]


ACTOR = object()


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fn(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _seed(factory: sessionmaker[Session], *, its: bool = True, enabled: bool = True) -> str:
    with factory() as s:
        s.add(
            WfsStoreSetting(
                source_account_ref=ACCOUNT,
                store_id=STORE_ID,
                walmart_store_code=CODE,
                its_enabled=its,
                creation_enabled=enabled,
                actor_uid="fixture",
            )
        )
        op_id = uuid4()
        s.add(
            WfsCreation(
                id=op_id,
                order_id=uuid4(),
                source_account_ref=ACCOUNT,
                store_id=STORE_ID,
                idempotency_key=uuid4(),
                request_hash="x",
                snapshot={},
                actor_uid="fixture",
                state="QUEUED",
            )
        )
        ticket_id = uuid4()
        s.add(
            WfsCreationTicket(
                id=ticket_id, operation_id=op_id, number=1, state="QUEUED", allocation={}, result={}
            )
        )
        s.commit()
    return str(ticket_id)


def _snapshot(**over: Any) -> dict[str, Any]:
    base = {
        "source_account_ref": ACCOUNT,
        "its": True,
        "order": {
            "store_id": STORE_ID,
            "sku": "YC00064-1U",
            "gtin": "00460016364228",
            "product_name": "Colander",
            "business_test": True,
        },
        "orders": [
            {
                "store_id": STORE_ID,
                "sku": "YC00064-1U",
                "gtin": "00460016364228",
                "product_name": "Colander",
            }
        ],
    }
    base.update(over)
    return base


ALLOCATION = {
    "number": 1,
    "boxes": 3,
    "units": 18,
    "ranges": [
        {"sku": "YC00064-1U", "boxes": 2, "units_per_box": 6, "units": 12},
        {"sku": "YC00064-1U", "boxes": 1, "units_per_box": 6, "units": 6},
    ],
}


def _gateway(factory, fake: FakeGateway | None = None, **over: Any):
    fake = fake or FakeGateway()
    gw = WalmartScfCreationGateway(
        session_factory=factory,
        gateway=fake,
        actor=ACTOR,
        clock=lambda: T0,
        sleeper=lambda _s: None,
        **over,
    )
    return gw, fake


def test_helpers_are_deterministic() -> None:
    tid = "5c9f1cb5-971c-4e41-bab9-a7b3b9cd0deb"
    assert inbound_order_id(CODE, tid, test=True) == "PMC-TEST-HK2614-5C9F1CB5971C"
    assert inbound_order_id(CODE, tid, test=False) == "PMC-HK2614-5C9F1CB5971C"
    assert expected_delivery(lambda: T0, {}) == "2026-11-30T00:00:00.000Z"
    assert (
        expected_delivery(lambda: T0, {"expected_delivery_at": "2026-12-01T16:00:00+00:00"})
        == "2026-12-02T00:00:00.000Z"
    )


def test_validate_enforces_store_mapping_its_and_identity(factory) -> None:
    gw, _ = _gateway(factory)
    with pytest.raises(ApiError, match="WFS_STORE_NOT_CONFIGURED"):
        gw.validate(_snapshot())
    _seed(factory, its=False)
    with pytest.raises(ApiError, match="WFS_ITS_NOT_AVAILABLE"):
        gw.validate(_snapshot(its=True))
    gw.validate(_snapshot(its=False))
    bad = _snapshot(its=False)
    bad["orders"][0]["gtin"] = "123"
    with pytest.raises(ApiError, match="WFS_ITEM_IDENTITY_MISSING"):
        gw.validate(bad)


def test_create_prechecks_posts_reads_back_verifies_with_audit(factory) -> None:
    ticket = _seed(factory)
    gw, fake = _gateway(factory)
    ids = gw.create(ticket, _snapshot(), ALLOCATION)
    assert ids == ["0000002WFB"]
    # precheck -> create -> readback -> verify items of the created shipment
    assert fake.reads() == ["inbound_shipments", "inbound_shipments", "inbound_shipment_items"]
    store, op, approval, body = fake.writes()[0]
    assert (store, op, approval) == (CODE, "wfs_inbound_shipment_create", f"wfs-ticket:{ticket}")
    assert fake.calls[1][5] == "wfs-create:" + body["inboundOrderId"]
    assert fake.ledger.status("wfs-create:" + body["inboundOrderId"]) == "ok"
    assert body["inboundOrderId"].startswith("PMC-TEST-HK2614-")
    assert body["inboundServices"] == {"inventoryTransferService": "Y"}
    assert "returnAddress" not in body  # store default unless the operator supplied one
    assert body["orderItems"] == [
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
    ]
    with factory() as s:
        kinds = list(s.scalars(select(WfsCreationEvent.kind)))
        evidence = list(s.scalars(select(WfsCreationEvent.evidence)))
    assert kinds == ["walmart_call"] * 3  # item reads are not ticket-linked events
    assert [e["operation"] for e in evidence] == [
        "inbound_shipments",
        "wfs_inbound_shipment_create",
        "inbound_shipments",
    ]
    assert all("token" not in str(e).lower() for e in evidence)


def test_create_is_idempotent_when_plan_already_exists(factory) -> None:
    ticket = _seed(factory)
    fake = FakeGateway()
    order_id = inbound_order_id(CODE, ticket, test=True)
    fake.shipments[order_id] = ["3190698WFB"]
    gw, fake = _gateway(factory, fake)
    assert gw.create(ticket, _snapshot(), ALLOCATION) == ["3190698WFB"]
    assert fake.writes() == []
    assert gw.reconcile(ticket, _snapshot()) == ["3190698WFB"]


def test_readback_refuses_records_of_another_plan(factory) -> None:
    ticket = _seed(factory)
    gw, fake = _gateway(factory, FakeGateway(foreign_record=True))
    with pytest.raises(RuntimeError, match="WFS_READBACK_MISMATCH"):
        gw.create(ticket, _snapshot(), ALLOCATION)
    assert fake.writes() == []  # nothing was posted on an untrustworthy read-back


def test_open_ledger_entry_blocks_second_post_until_readback_decides(factory) -> None:
    ticket = _seed(factory)
    fake = FakeGateway()
    order_id = inbound_order_id(CODE, ticket, test=True)
    key = f"wfs-create:{order_id}"
    fake.ledger.entries[key] = {"outcome": "unknown"}
    gw, fake = _gateway(factory, fake)
    # Nothing visible at Walmart: stay UNKNOWN for a human, no second POST.
    with pytest.raises(RuntimeError, match="WFS_CREATE_PENDING_REVIEW"):
        gw.create(ticket, _snapshot(), ALLOCATION)
    assert [c[1] for c in fake.calls] == [
        "inbound_shipments",
        "wfs_inbound_shipment_create",
        "inbound_shipments",
    ]
    assert fake.ledger.status(key) == "unknown"
    # The shipment shows up later: reconcile resolves the ledger and returns it.
    fake.shipments[order_id] = ["7777777WFB"]
    assert gw.reconcile(ticket, _snapshot()) == ["7777777WFB"]
    assert fake.ledger.entries[key]["outcome"] == "ok"


def test_created_shipment_must_match_the_request(factory) -> None:
    ticket = _seed(factory)

    class ShortGateway(FakeGateway):
        def call(self, store_code, operation_key, **kwargs):
            result = super().call(store_code, operation_key, **kwargs)
            if operation_key == "wfs_inbound_shipment_create":
                for rows in self.items.values():
                    rows[0]["itemQty"] -= 1  # Walmart "lost" a unit
            return result

    gw, _ = _gateway(factory, ShortGateway())
    with pytest.raises(RuntimeError, match="WFS_SHIPMENT_QUANTITY_MISMATCH"):
        gw.create(ticket, _snapshot(), ALLOCATION)


def test_create_rejection_and_ambiguity_map_to_worker_semantics(factory) -> None:
    ticket = _seed(factory)
    gw, _ = _gateway(
        factory, FakeGateway(create_status=400, create_error={"errors": [{"code": "X"}]})
    )
    with pytest.raises(DefinitiveRejection, match="WALMART_HTTP_400"):
        gw.create(ticket, _snapshot(), ALLOCATION)
    with factory() as s:
        errors = [
            e["provider_error"]
            for e in s.scalars(select(WfsCreationEvent.evidence))
            if "provider_error" in e
        ]
    assert errors == [{"errors": [{"code": "X"}]}]
    # 5xx is ambiguous: no DefinitiveRejection, holds stay.
    gw5, _ = _gateway(factory, FakeGateway(create_status=503))
    with pytest.raises(RuntimeError, match="WALMART_HTTP_503"):
        gw5.create(ticket, _snapshot(), ALLOCATION)
    # A gateway refusal (permission, config, transport) is UNKNOWN with its stable code.

    class Refusing(FakeGateway):
        def call(self, store_code, operation_key, **kwargs):
            if operation_key == "wfs_inbound_shipment_create":
                raise LedgerBlocked("WALMART_PERMISSION_DENIED")
            return super().call(store_code, operation_key, **kwargs)

    gw_r, _ = _gateway(factory, Refusing())
    with pytest.raises(RuntimeError, match="WALMART_PERMISSION_DENIED"):
        gw_r.create(ticket, _snapshot(), ALLOCATION)
    # Mixed pack sizes inside one ticket never reach Walmart.
    gw_ok, fake_ok = _gateway(factory)
    mixed = {
        **ALLOCATION,
        "ranges": [{**ALLOCATION["ranges"][0], "units_per_box": 5}, ALLOCATION["ranges"][1]],
    }
    with pytest.raises(DefinitiveRejection, match="WFS_MIXED_PACK_SIZE_IN_TICKET"):
        gw_ok.create(ticket, _snapshot(), mixed)
    assert fake_ok.writes() == []


def test_label_pages_through_all_items_and_returns_pdf(factory) -> None:
    _seed(factory)
    rows = [
        {"sku": f"S{i}", "gtin": f"{i:014d}", "itemQty": 6, "vendorPackQty": 1} for i in range(120)
    ]
    gw, fake = _gateway(factory, FakeGateway(items={"3190698WFB": rows}))
    assert gw.label("3190698WFB", _snapshot()) == PDF
    item_calls = [c for c in fake.calls if c[1] == "inbound_shipment_items"]
    assert [c[2]["offset"] for c in item_calls] == [0, 50, 100]  # 120 rows = 3 pages
    store, op, approval, body = fake.writes()[0]
    assert body["loadTypes"] == [{"loadType": "SINGLE SKU", "count": "120"}]
    assert approval == "wfs-label:3190698WFB"
    with pytest.raises(RuntimeError, match="WALMART_CARTON_COUNT_UNKNOWN"):
        gw.label("UNKNOWN1WFB", _snapshot())


def test_preview_parses_plans(factory) -> None:
    _seed(factory)
    gw, _ = _gateway(factory)
    out = gw.preview(_snapshot(allocation={"tickets": [ALLOCATION]}))
    assert out["plans"] == [
        {
            "preview_type": "inbound",
            "fc_name": "LAX2T",
            "node_type": "ICC",
            "charge": 78.3,
            "units": 18,
            "skus": ["YC00064-1U"],
        }
    ]


def test_env_builder_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    for name in (
        "SZZSBJ_WFS_CREATION_GATEWAY",
        "SZZSBJ_WALMART_SCF_STORE_ID_MAP",
        "SZZSBJ_WALMART_SCF_PROTOCOL",
        "SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS",
        "SZZSBJ_WALMART_SCF_APPROVED_WRITE_KEYS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(build_gateway_from_env(factory), DisabledGateway)
    monkeypatch.setenv("SZZSBJ_WFS_CREATION_GATEWAY", "scf")
    # Switch on but no reviewed store map -> disabled.
    assert isinstance(build_gateway_from_env(factory), DisabledGateway)
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", json.dumps({STORE_ID: CODE}))
    # Store map present but the shared gateway cannot be configured (no identity, no
    # protocol-3 signing key, no legacy keys) -> disabled, never a half-configured adapter.
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_CVM_ROLE", raising=False)
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN", raising=False)
    assert isinstance(build_gateway_from_env(factory), DisabledGateway)
    assert reviewed_store_map() == {STORE_ID: CODE}


def test_store_mapping_conflict_is_refused(factory) -> None:
    _seed(factory)
    gw, _ = _gateway(factory, store_code_map={STORE_ID: "HK2615"})
    with pytest.raises(ApiError, match="WFS_STORE_MAPPING_CONFLICT"):
        gw.validate(_snapshot())
