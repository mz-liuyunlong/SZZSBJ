"""Shipment board M1 reads creation label keys only."""

from uuid import uuid4

from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.shipment_board_schemas import ShipmentBoardQuery
from app.modules.pmc_wfs.shipment_board_service import ShipmentBoardService, row_id

pytest_plugins = ["tests.modules.pmc_wfs.test_pending"]


def _seed_shipment(db, account, order):
    op_id = uuid4()
    ticket_id = uuid4()
    snap = {
        "its": False,
        "order": {
            "pk": order.pk,
            "sku": order.sku,
            "store_name": "测试店",
            "item_id": order.item_id,
            "gtin": order.snapshot_json.get("gtin"),
            "msku": order.snapshot_json.get("msku"),
            "business_test": order.business_test,
        },
    }
    db.add(
        WfsCreation(
            id=op_id,
            order_id=order.id,
            source_account_ref=account,
            store_id=order.store_id,
            idempotency_key=uuid4(),
            request_hash="abc",
            snapshot=snap,
            actor_uid="fixture",
            state="SUCCEEDED",
        )
    )
    db.add(
        WfsCreationTicket(
            id=ticket_id,
            operation_id=op_id,
            number=1,
            state="SUCCEEDED",
            allocation={"number": 1, "boxes": 2, "units": 8, "ranges": []},
            result={"labels": {"WFS-TEST-001": {"state": "READY"}}},
        )
    )
    db.flush()
    return ticket_id


def test_list_and_detail(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    ticket_id = _seed_shipment(db, account, order)
    svc = ShipmentBoardService(db, frozenset({account}), None)
    listed = svc.list(ShipmentBoardQuery())
    assert listed.total == 1
    assert listed.items[0].shipment_id == "WFS-TEST-001"
    assert listed.items[0].label_state == "READY"
    assert listed.items[0].lingxing_sync_status == "PENDING"
    detail = svc.detail(row_id(ticket_id, "WFS-TEST-001"))
    assert detail.pk == order.pk
    assert svc.summary(ShipmentBoardQuery()).test == 1


def test_keyword_filter(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    _seed_shipment(db, account, order)
    svc = ShipmentBoardService(db, frozenset({account}), None)
    q = ShipmentBoardQuery(keyword="WFS-TEST", keyword_field="shipment")
    assert svc.list(q).total == 1
    assert svc.list(ShipmentBoardQuery(keyword="no-match", keyword_field="shipment")).total == 0
