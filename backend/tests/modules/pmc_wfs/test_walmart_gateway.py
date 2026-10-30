"""Walmart creation adapter: offline, fake read/write APIs, SQLite for settings + events."""

from __future__ import annotations

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


@dataclass
class FakeReadApi:
    shipments: dict[str, list[str]] = field(default_factory=dict)  # inboundOrderId -> ids
    cartons: dict[str, int] = field(default_factory=dict)  # shipmentId -> vendorPackQty sum
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    fail_status: int | None = None

    def call(self, store_code: str, operation: str, *, params: dict[str, Any] | None = None):
        params = dict(params or {})
        self.calls.append((store_code, operation, params))
        if self.fail_status:
            return FakeResult(self.fail_status, provider_error={"errors": ["read down"]})
        if operation == "inbound_shipments":
            ids = self.shipments.get(str(params.get("inboundOrderId")), [])
            return FakeResult(
                200,
                {
                    "headers": {"totalCount": len(ids)},
                    "payload": [
                        {"shipmentId": s, "status": "PENDING_SHIPMENT_DETAILS"} for s in ids
                    ],
                },
            )
        if operation == "inbound_shipment_items":
            qty = self.cartons.get(str(params.get("shipmentId")), 0)
            return FakeResult(
                200, {"payload": [{"sku": "YC00064-1U", "vendorPackQty": qty, "itemQty": qty * 6}]}
            )
        raise AssertionError(operation)


@dataclass
class FakeWriteApi:
    read: FakeReadApi
    create_status: int = 201
    create_error: Any = None
    calls: list[tuple[str, str, str, Any]] = field(default_factory=list)

    def call(
        self,
        store_code: str,
        operation: str,
        *,
        approval_ref: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ):
        self.calls.append((store_code, operation, approval_ref, body))
        if operation == "wfs_inbound_shipment_create":
            if 200 <= self.create_status < 300:
                # Walmart "creates" one shipment per plan; read-back will see it.
                self.read.shipments[body["inboundOrderId"]] = [f"{len(self.calls):07d}WFB"]
            return FakeResult(self.create_status, {"status": "OK"}, self.create_error)
        if operation == "wfs_shipment_label":
            return FakeResult(200, None, pdf=PDF)
        if operation == "wfs_inbound_preview":
            return FakeResult(
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
        raise AssertionError(operation)


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


def _gateway(factory, read: FakeReadApi | None = None, write: FakeWriteApi | None = None):
    read = read or FakeReadApi()
    write = write or FakeWriteApi(read)
    gw = WalmartScfCreationGateway(
        session_factory=factory,
        read_api=read,
        write_api=write,
        clock=lambda: T0,
        sleeper=lambda _s: None,
    )
    return gw, read, write


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
    gw, *_ = _gateway(factory)
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


def test_create_prechecks_posts_and_reads_back_with_audit(factory) -> None:
    ticket = _seed(factory)
    gw, read, write = _gateway(factory)
    ids = gw.create(ticket, _snapshot(), ALLOCATION)
    assert ids == ["0000001WFB"]
    # precheck -> create -> readback
    assert [c[1] for c in read.calls] == ["inbound_shipments", "inbound_shipments"]
    store, op, approval, body = write.calls[0]
    assert (store, op, approval) == (CODE, "wfs_inbound_shipment_create", f"wfs-ticket:{ticket}")
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
    assert kinds == ["walmart_call"] * 3
    assert [e["operation"] for e in evidence] == [
        "inbound_shipments",
        "wfs_inbound_shipment_create",
        "inbound_shipments",
    ]
    assert all("token" not in str(e).lower() for e in evidence)


def test_create_is_idempotent_when_plan_already_exists(factory) -> None:
    ticket = _seed(factory)
    read = FakeReadApi()
    read.shipments[inbound_order_id(CODE, ticket, test=True)] = ["3190698WFB"]
    gw, read, write = _gateway(factory, read)
    assert gw.create(ticket, _snapshot(), ALLOCATION) == ["3190698WFB"]
    assert write.calls == []
    assert gw.reconcile(ticket, _snapshot()) == ["3190698WFB"]


def test_create_rejection_and_ambiguity_map_to_worker_semantics(factory) -> None:
    ticket = _seed(factory)
    read = FakeReadApi()
    write = FakeWriteApi(read, create_status=400, create_error={"errors": [{"code": "X"}]})
    gw, *_ = _gateway(factory, read, write)
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
    write5 = FakeWriteApi(FakeReadApi(), create_status=503)
    gw5, *_ = _gateway(factory, write5.read, write5)
    with pytest.raises(RuntimeError, match="WALMART_HTTP_503"):
        gw5.create(ticket, _snapshot(), ALLOCATION)
    # Mixed pack sizes inside one ticket never reach Walmart.
    gw_ok, read_ok, write_ok = _gateway(factory)
    mixed = {
        **ALLOCATION,
        "ranges": [{**ALLOCATION["ranges"][0], "units_per_box": 5}, ALLOCATION["ranges"][1]],
    }
    with pytest.raises(DefinitiveRejection, match="WFS_MIXED_PACK_SIZE_IN_TICKET"):
        gw_ok.create(ticket, _snapshot(), mixed)
    assert write_ok.calls == []


def test_label_uses_carton_count_and_returns_pdf(factory) -> None:
    _seed(factory)
    read = FakeReadApi(cartons={"3190698WFB": 3})
    gw, read, write = _gateway(factory, read)
    assert gw.label("3190698WFB", _snapshot()) == PDF
    assert write.calls[0][3]["loadTypes"] == [{"loadType": "SINGLE SKU", "count": "3"}]
    with pytest.raises(RuntimeError, match="WALMART_CARTON_COUNT_UNKNOWN"):
        gw.label("UNKNOWN1WFB", _snapshot())


def test_preview_parses_plans(factory) -> None:
    _seed(factory)
    gw, *_ = _gateway(factory)
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
    monkeypatch.delenv("WFS_WALMART_GATEWAY", raising=False)
    assert isinstance(build_gateway_from_env(factory), DisabledGateway)
    monkeypatch.setenv("WFS_WALMART_GATEWAY", "scf")
    monkeypatch.delenv("WALMART_SCF_STORES", raising=False)
    assert isinstance(build_gateway_from_env(factory), DisabledGateway)
