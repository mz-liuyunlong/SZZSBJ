"""WFS creation adapter against the real unified Walmart gateway, contracts and write ledger.

Only the per-store cloud transport is replaced by a scripted fake: no network, no credential.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.gateway import (
    GatewayError,
    InMemoryWriteLedger,
    WalmartGateway,
)
from app.integrations.walmart.unified_api import reviewed_registry
from app.modules.pmc_wfs import creation_config
from app.modules.pmc_wfs.walmart_gateway import (
    DefinitiveRejection,
    NotSent,
    ResultUnknown,
    WalmartCreationGateway,
    gtin14,
    inbound_order,
    load_types,
    provider_reason,
    shipments_from,
    walmart_date,
)

STORE_ID, STORE = "lx-store-1", "HK2614"
TICKET = "PMC-HK2614-20261104-01"  # our order id: same format as the 8088 creations
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


class ScriptedTransport:
    """Plays the cloud function: returns queued results or raises queued errors."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def execute(self, *, store_code, request, approval_ref, actor=None):
        self.requests.append(SimpleNamespace(store=store_code, request=request, ref=approval_ref))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def snapshot(**extra):
    order = {
        "id": "o-1",
        "sku": "SKU-1",
        "msku": "MSKU-1",
        "gtin": "123456789012",
        "product_name": "Test product",
        "store_id": STORE_ID,
    }
    return {
        "source_account_ref": "acct",
        "shipment_count": 1,
        "order": order,
        "orders": [order],
        "return_address": {
            "address_line1": "1 Test St",
            "city": "Katy",
            "state_code": "TX",
            "postal_code": "77449",
            "country_code": "US",
        },
        "expected_delivery_at": "2026-11-25T00:00:00+08:00",
        "its": False,
        "approval_ref": "rocky-written:test#1",
        "creation_defaults": {"mixed_boxes": 0},
        "ticket_boxes": 3,
        **extra,
    }


ALLOCATION = {
    "boxes": 3,
    "ranges": [
        {"order_id": "o-1", "units_per_box": 4, "units": 8},
        {"order_id": "o-1", "units_per_box": 4, "units": 4},
    ],
}


def adapter(transport, mode="batch", ledger=None):
    client = WalmartClient(
        reviewed_registry(), allowed_stores=frozenset({STORE}), gateway=transport
    )
    audit = []
    walmart = WalmartGateway(client, audit=audit.append, ledger=ledger or InMemoryWriteLedger())
    gateway = WalmartCreationGateway(
        walmart, mode=mode, store_map={STORE_ID: STORE}, clock=lambda: NOW
    )
    return gateway, walmart, audit


CREATED = WalmartResult(
    200,
    {
        "status": "OK",
        "payload": [
            {
                "inboundOrderId": TICKET,
                "shipmentId": "SHIP123",
                "shipToAddress": {"fcName": "ATL1", "city": "Atlanta", "stateCode": "GA"},
                "shipmentItems": [{"sku": "MSKU-1", "itemQty": 12, "vendorPackQty": 4}],
            }
        ],
    },
)


# ----- pure mapping ------------------------------------------------------------------


def test_body_passes_reviewed_contract_and_aggregates_sku():
    body = inbound_order(TICKET, snapshot(), ALLOCATION)
    assert body["inboundOrderId"] == TICKET
    assert body["orderItems"] == [
        {
            "productId": "00123456789012",
            "productType": "GTIN",
            "sku": "MSKU-1",
            "itemDesc": "Test product",
            "itemQty": 12,
            "vendorPackQty": 4,
            "innerPackQty": 4,
            "expectedDeliveryDate": "2026-11-24T16:00:00.000Z",
        }
    ]
    assert "inboundServices" not in body
    reviewed_registry().prepare(
        "wfs_inbound_shipment_create", body=body, allow_writes=True
    )  # the cloud side validates the same schema
    its = inbound_order(TICKET, snapshot(its=True), ALLOCATION)
    assert its["inboundServices"] == {"inventoryTransferService": "Y"}


def test_mapping_guards():
    assert gtin14("0-12345-67890-5") == "00012345678905"
    with pytest.raises(NotSent):
        gtin14(None)
    mixed = {
        **ALLOCATION,
        "ranges": [*ALLOCATION["ranges"], {"order_id": "o-1", "units_per_box": 6, "units": 6}],
    }
    with pytest.raises(NotSent) as err:
        inbound_order(TICKET, snapshot(), mixed)
    assert err.value.code == "WFS_PACK_QTY_MIXED"
    assert walmart_date("2026-11-30T00:00:00Z") == "2026-11-30T00:00:00.000Z"
    assert load_types(10, 0) == [{"loadType": "SINGLE SKU", "count": "10"}]
    assert load_types(10, 3) == [
        {"loadType": "SINGLE SKU", "count": "7"},
        {"loadType": "MIXED SKUS", "count": "3"},
    ]


def test_response_parsing():
    shipments = shipments_from(CREATED.data, TICKET)
    assert shipments == [
        {
            "shipment_id": "SHIP123",
            "fc": "ATL1",
            "ship_to": {"city": "Atlanta", "stateCode": "GA"},
            "status": None,
            "cartons": 3,
        }
    ]
    assert (
        shipments_from({"payload": [{"inboundOrderId": "other", "shipmentId": "X1"}]}, TICKET) == []
    )
    reason = provider_reason(
        {"errors": [{"code": "INVALID", "description": "Invalid GTIN"}, {"info": "Retry later"}]}
    )
    assert reason == "Invalid GTIN；Retry later"


# ----- adapter over the real gateway ------------------------------------------------


def test_create_sends_once_with_business_key_and_approval():
    transport = ScriptedTransport(CREATED)
    gateway, walmart, audit = adapter(transport)
    assert gateway.create(TICKET, snapshot(), ALLOCATION)[0]["shipment_id"] == "SHIP123"
    sent = transport.requests[0]
    assert sent.store == STORE and sent.ref == "rocky-written:test#1"
    assert sent.request.path == "/v3/fulfillment/inbound-shipments"
    assert walmart.ledger.status(f"create:{TICKET}") == "ok"
    # Same ticket again: the ledger refuses before anything is sent -> read back instead.
    with pytest.raises(ResultUnknown) as err:
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert err.value.code == "WALMART_WRITE_ALREADY_DONE"
    assert len(transport.requests) == 1
    assert [r.outcome for r in audit].count("attempt") == 1


def test_rejection_carries_walmart_reason_and_allows_same_payload_retry():
    rejected = WalmartResult(
        400, None, provider_error={"errors": [{"description": "Invalid postal code"}]}
    )
    transport = ScriptedTransport(rejected, CREATED)
    gateway, walmart, _ = adapter(transport)
    with pytest.raises(DefinitiveRejection) as err:
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert err.value.reason == "Invalid postal code"
    assert walmart.ledger.status(f"create:{TICKET}") == "provider_error"
    assert gateway.create(TICKET, snapshot(), ALLOCATION)  # same order id, same body


def test_timeout_is_unknown_and_blocks_a_second_post_until_read_back():
    transport = ScriptedTransport(TimeoutError("socket"), WalmartResult(200, {"payload": []}))
    gateway, walmart, _ = adapter(transport)
    with pytest.raises(ResultUnknown):
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert walmart.ledger.status(f"create:{TICKET}") == "unknown"
    with pytest.raises(ResultUnknown) as err:
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert err.value.code == "WALMART_WRITE_PENDING_REVIEW"
    assert len(transport.requests) == 1  # never posted twice
    assert gateway.reconcile(TICKET, snapshot()) is None
    query = transport.requests[1].request.query
    assert query["inboundOrderId"] == TICKET and query["toCreatedDate"] > query["fromCreatedDate"]
    gateway.resolve(TICKET, "failed", "not found after polling")
    assert walmart.ledger.status(f"create:{TICKET}") == "failed"


def test_server_error_is_unknown_and_not_retried():
    transport = ScriptedTransport(WalmartResult(503, None))
    gateway, walmart, _ = adapter(transport)
    with pytest.raises(ResultUnknown):
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert walmart.ledger.status(f"create:{TICKET}") == "unknown"


def test_refusal_before_sending_is_not_sent():
    class Refuse:
        ledger = InMemoryWriteLedger()

        def call(self, *a, **k):
            raise GatewayError("WALMART_STORE_NOT_AUTHORIZED")

    gateway = WalmartCreationGateway(Refuse(), mode="batch", store_map={STORE_ID: STORE})
    with pytest.raises(NotSent) as err:
        gateway.create(TICKET, snapshot(), ALLOCATION)
    assert err.value.code == "WALMART_STORE_NOT_AUTHORIZED"


def test_rollout_modes_and_store_mapping(monkeypatch):
    probe, *_ = adapter(ScriptedTransport(), mode="probe")
    with pytest.raises(ApiError) as err:
        probe.validate(snapshot())
    assert err.value.code == "WFS_EXECUTION_DISABLED" and probe.preview_enabled
    single, *_ = adapter(ScriptedTransport(), mode="single")
    single.validate(snapshot())
    with pytest.raises(ApiError) as err:
        single.validate(snapshot(shipment_count=2))
    assert err.value.code == "WFS_SINGLE_MODE_ONE_SHIPMENT"
    batch, *_ = adapter(ScriptedTransport(), mode="batch")
    batch.validate(snapshot(shipment_count=5))
    with pytest.raises(ApiError) as err:
        batch.validate(snapshot(order={**snapshot()["order"], "store_id": "unknown"}))
    assert err.value.code == "WFS_STORE_NOT_MAPPED"
    monkeypatch.setenv("WFS_CREATION_MODE", "BATCH")
    assert creation_config.creation_mode() == "batch"
    monkeypatch.setenv("WFS_CREATION_MODE", "everything")
    assert creation_config.creation_mode() == "off"


def test_probe_is_read_only():
    transport = ScriptedTransport(
        WalmartResult(200, {"payload": [{"shipmentId": "A1"}]}),
        WalmartResult(204, None),  # 8088: an order id Walmart does not have -> 204
    )
    gateway, walmart, _ = adapter(transport, mode="probe")
    result = gateway.probe(STORE_ID)
    assert result == {
        "ok": True,
        "status_code": 200,
        "store_code": STORE,
        "recent_shipments": 1,
        "lookup_status_code": 204,
        "lookup_not_found_ok": True,
    }
    assert all(r.request.is_write is False for r in transport.requests)
    lookup = transport.requests[1].request.query
    assert lookup["inboundOrderId"] == "PMC-PROBE-HK2614-20261104120000"
    assert walmart.ledger.status(f"create:{TICKET}") is None


def test_probe_fails_when_unknown_order_id_is_an_error():
    transport = ScriptedTransport(
        WalmartResult(200, {"payload": []}), WalmartResult(400, {"errors": [{"code": "x"}]})
    )
    gateway, *_ = adapter(transport, mode="probe")
    result = gateway.probe(STORE_ID)
    assert result["ok"] is False and result["lookup_not_found_ok"] is False


def test_read_back_204_or_404_means_not_found():
    for status in (204, 404):
        gateway, *_ = adapter(ScriptedTransport(WalmartResult(status, None)))
        assert gateway.reconcile(TICKET, snapshot()) is None
    gateway, *_ = adapter(ScriptedTransport(WalmartResult(503, None)))
    with pytest.raises(ResultUnknown):
        gateway.reconcile(TICKET, snapshot())
    assert gateway.store_code(snapshot()) == STORE


def test_label_uses_carton_count_and_mixed_boxes():
    pdf = WalmartResult(200, None, content_type="application/pdf", pdf=b"%PDF-1.4 x")
    transport = ScriptedTransport(pdf)
    gateway, *_ = adapter(transport)
    snap = snapshot(creation_defaults={"mixed_boxes": 1})
    assert gateway.label("SHIP123", snap, cartons=3) == b"%PDF-1.4 x"
    assert transport.requests[0].request.body["loadTypes"] == [
        {"loadType": "SINGLE SKU", "count": "2"},
        {"loadType": "MIXED SKUS", "count": "1"},
    ]


def test_default_gateway_is_disabled_without_mode(monkeypatch):
    from app.modules.pmc_wfs.gateway import DisabledGateway, get_creation_gateway

    monkeypatch.delenv("WFS_CREATION_MODE", raising=False)
    assert isinstance(get_creation_gateway(), DisabledGateway)
    monkeypatch.setenv("WFS_CREATION_MODE", "single")
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", raising=False)
    from app.modules.pmc_wfs import gateway as module

    module._production_gateway.cache_clear()
    disabled = get_creation_gateway()  # configuration missing -> refuses with a reason
    assert isinstance(disabled, DisabledGateway) and "Walmart 通道配置不可用" in disabled.reason
    module._production_gateway.cache_clear()


def test_guard_write_outside_local(monkeypatch):
    from app.modules.pmc_wfs import creation_service

    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            url=SimpleNamespace(host="10.0.0.5", port=5432, database="szzsbj")
        )
    )
    monkeypatch.setattr(
        creation_service,
        "get_settings",
        lambda: SimpleNamespace(app_env=SimpleNamespace(value="production")),
    )
    monkeypatch.setenv("WFS_CREATION_MODE", "probe")
    with pytest.raises(ApiError) as err:
        creation_service.guard_write(session)
    assert err.value.code == "WFS_CREATION_DISABLED"
    monkeypatch.setenv("WFS_CREATION_MODE", "single")
    creation_service.guard_write(session)
