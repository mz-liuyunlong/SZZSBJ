"""Real V2 services and PostgreSQL constraints; only external platform is synthetic."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.config import get_settings
from app.modules.pmc_wfs.creation_models import WfsBoxHold, WfsCreationEvent
from app.modules.pmc_wfs.creation_schemas import AllocationCommand, CreationCommand
from app.modules.pmc_wfs.creation_service import CreationService
from app.modules.pmc_wfs.creation_worker import run_operation
from app.modules.pmc_wfs.gateway import DisabledGateway
from app.modules.pmc_wfs.repository import assert_not_occupied
from app.modules.pmc_wfs.service import WfsService
from tests.modules.pmc_wfs.v2_support import (
    SyntheticGateway,
    app_for,
    engine_and_schema,
    factory_for,
    seed_fixture,
)


@pytest.fixture(scope="module")
def engine():
    if not os.environ.get("WFS_V2_TEST_DATABASE_URL"):
        pytest.skip("requires an explicitly configured task-owned PostgreSQL instance")
    get_settings.cache_clear()
    value = engine_and_schema()
    yield value
    value.dispose()


@pytest.fixture
def case(engine):
    with Session(engine, expire_on_commit=False) as session:
        account, order, box, line = seed_fixture(session)
        gateway = SyntheticGateway()
        svc = CreationService(WfsService(session, {account}, None), gateway, lambda *_: None)
        yield session, svc, gateway, account, order, box, line


def allocation(order, counts=(12, 8)):
    return AllocationCommand(
        order_id=order.id,
        expected_version=1,
        expected_box_version=1,
        shipping_boxes=sum(counts),
        shipment_count=len(counts),
        shipment_boxes=list(counts),
    )


def command(svc, account, order, counts=(12, 8)):
    cmd = allocation(order, counts)
    return CreationCommand(
        **cmd.model_dump(),
        source_account_ref=account,
        preview_hash=svc.preview(cmd).preview_hash,
        idempotency_key=uuid4(),
        return_address=dict(
            address_line1="Test street", city="Katy", state_code="TX", postal_code="77449"
        ),
        expected_delivery_at=datetime.now(UTC) + timedelta(days=30),
    )


def test_partial_boxes_no_ows_and_replay(case):
    session, svc, gateway, account, order, box, line = case
    cmd = command(svc, account, order)
    op = svc.submit(cmd, "fixture")
    assert [t.allocation.boxes for t in op.tickets] == [12, 8]
    assert svc.base.detail(order.id).available_boxes == 10
    assert svc.submit(cmd, "fixture").id == op.id
    assert op.automatically_approved_at is not None
    assert (
        session.scalar(
            select(func.count())
            .select_from(WfsCreationEvent)
            .where(
                WfsCreationEvent.operation_id == op.id,
                WfsCreationEvent.kind == "automatically_approved",
            )
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count()).select_from(WfsBoxHold).where(WfsBoxHold.order_id == order.id)
        )
        == 20
    )
    with pytest.raises(ApiError):
        assert_not_occupied(session, order.id)
    session.rollback()
    with pytest.raises(ApiError):
        svc.submit(cmd.model_copy(update={"its": True}), "fixture")


def test_disabled_gateway_leaves_no_hold(case):
    session, svc, gateway, account, order, *_ = case
    cmd = command(svc, account, order)
    svc.gateway = DisabledGateway()
    with pytest.raises(ApiError, match="WFS_EXECUTION_DISABLED"):
        svc.submit(cmd, "fixture")
    assert svc.base.detail(order.id).available_boxes == 30
    assert svc.list(order.id, 1, 20).total == 0


def test_unknown_then_reconcile_does_not_recreate(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown = True
    op = svc.submit(command(svc, account, order), "fixture")
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    session.expire_all()
    assert svc.read(op.id).state == "UNKNOWN"
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id)
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id, "reconcile")
    session.expire_all()
    assert svc.read(op.id).state == "SUCCEEDED"
    assert len(gateway.creates) == 2


def test_labels_retry_only_and_scope(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.fail_label = True
    op = svc.submit(command(svc, account, order), "fixture")
    run_operation(factory_for(engine), gateway, op.id)
    session.expire_all()
    result = svc.read(op.id)
    assert result.state == "SUCCEEDED"
    assert result.tickets[0].shipments[0].label_state == "FAILED"
    gateway.fail_label = False
    run_operation(factory_for(engine), gateway, op.id, "labels")
    session.expire_all()
    result = svc.read(op.id)
    assert result.tickets[0].shipments[0].label_state == "READY"
    assert svc.label(op.id, result.tickets[0].shipments[0].shipment_id).startswith(b"%PDF-")
    assert len(gateway.creates) == 2
    other = CreationService(WfsService(session, {account}, {"other"}), gateway, lambda *_: None)
    with pytest.raises(ApiError):
        other.read(op.id)


def test_concurrent_same_boxes(case, engine):
    session, svc, gateway, account, order, *_ = case
    cmd = command(svc, account, order, (30,))
    session.rollback()

    def submit(key):
        with Session(engine) as db:
            service = CreationService(WfsService(db, {account}, None), gateway, lambda *_: None)
            try:
                service.submit(cmd.model_copy(update={"idempotency_key": key}), "fixture")
                return True
            except ApiError:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, [uuid4(), uuid4()])) == [False, True]


def test_typed_counts_reject_bool_zero_and_mismatch(case):
    order = case[4]
    for counts in ([0], [True]):
        with pytest.raises(ValidationError):
            AllocationCommand(
                order_id=order.id,
                expected_version=1,
                expected_box_version=1,
                shipping_boxes=1,
                shipment_count=1,
                shipment_boxes=counts,
            )
    with pytest.raises(ValidationError):
        AllocationCommand(
            order_id=order.id,
            expected_version=1,
            expected_box_version=1,
            shipping_boxes=5,
            shipment_count=1,
            shipment_boxes=[4],
        )


def test_real_http_contract(case, engine):
    _, svc, gateway, account, order, *_ = case
    app = app_for(engine, account, gateway)
    cmd = command(svc, account, order)
    with TestClient(app) as client:
        prefix = "/api/pmc/wfs/pending-packing"
        response = client.post(prefix + "/creation-operations", json=cmd.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["state"] == "SUCCEEDED"
        assert client.get(prefix + "/orders").json()["data"]["items"][0]["available_boxes"] == 10
        assert (
            client.get(prefix + "/creation-operations", params={"order_id": str(order.id)}).json()[
                "data"
            ]["total"]
            == 1
        )


def test_multiple_pk_same_store_and_mixed_tail(case):
    session, svc, gateway, account, order, box, line = case
    _, second, second_box, tail = seed_fixture(session, boxes=1, per=5)
    second.source_account_ref = account
    second.snapshot_json = {**second.snapshot_json, "source_account_ref": account}
    order.pk, second.pk = "PK-MAIN-" + order.id.hex[:16], "PK-TAIL-" + second.id.hex[:16]
    session.commit()
    cmd = allocation(order, (20, 11)).model_copy(
        update={
            "additional_selections": [
                __import__(
                    "app.modules.pmc_wfs.creation_schemas", fromlist=["OrderSelection"]
                ).OrderSelection(order_id=second.id, expected_version=1, expected_box_version=1)
            ]
        }
    )
    preview = svc.preview(cmd)
    assert [t.units for t in preview.tickets] == [80, 45]
    submit = CreationCommand(
        **cmd.model_dump(),
        source_account_ref=account,
        preview_hash=preview.preview_hash,
        idempotency_key=uuid4(),
        return_address=dict(
            address_line1="Test", city="Katy", state_code="TX", postal_code="77449"
        ),
        expected_delivery_at=datetime.now(UTC) + timedelta(days=1),
    )
    result = svc.submit(submit, "fixture")
    assert svc.list(second.id, 1, 20).items[0].id == result.id
    assert svc.base.detail(second.id).available_boxes == 0
    assert {r.order_id for t in result.tickets for r in t.allocation.ranges} == {
        order.id,
        second.id,
    }


def test_cross_store_cannot_auto_approve(case):
    from app.modules.pmc_wfs.creation_schemas import OrderSelection

    session, svc, gateway, account, order, *_ = case
    _, second, *_ = seed_fixture(session)
    second.source_account_ref, second.store_id = account, "different-store"
    session.commit()
    cmd = allocation(order).model_copy(
        update={
            "additional_selections": [
                OrderSelection(order_id=second.id, expected_version=1, expected_box_version=1)
            ]
        }
    )
    with pytest.raises(ApiError):
        svc.preview(cmd)
    assert gateway.creates == []


def test_create_action_permission_is_not_draft_permission(case, engine):
    from app.core.auth import Principal, get_optional_principal

    _, svc, gateway, account, order, *_ = case
    app = app_for(engine, account, gateway)
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="16",
        permissions=frozenset({"page:pmc:wfs:view", "action:pmc:wfs-pending-packing:draft-submit"}),
    )
    with TestClient(app) as client:
        result = client.post(
            "/api/pmc/wfs/pending-packing/creation-operations",
            json=command(svc, account, order).model_dump(mode="json"),
        )
        assert result.status_code == 403
        assert gateway.creates == []


def test_old_occupancy(case):
    from app.modules.pmc_wfs.models import WfsBoxAllocation, WfsDraft, WfsDraftItem

    session, svc, _, account, order, box, line = case
    draft = WfsDraft(
        id=uuid4(),
        number="LEGACY-" + uuid4().hex,
        source_account_ref=account,
        store_id=order.store_id,
        business_test=True,
        actor_uid="fixture",
        payload={},
    )
    session.add(draft)
    session.flush()
    item = WfsDraftItem(
        id=uuid4(),
        draft_id=draft.id,
        sku=order.sku,
        gtin="00000000000001",
        boxes=30,
        units_per_box=4,
        snapshot={},
    )
    session.add(item)
    session.flush()
    session.add(
        WfsBoxAllocation(
            item_id=item.id,
            order_id=order.id,
            box_line_id=line.id,
            box_version=box.version,
            snapshot={},
        )
    )
    session.commit()
    assert svc.base.detail(order.id).available_boxes == 0
    with pytest.raises(ApiError):
        svc.preview(allocation(order))


def test_audit_immutable(case):
    from sqlalchemy import delete
    from sqlalchemy.exc import DBAPIError

    session, svc, _, account, order, *_ = case
    result = svc.submit(command(svc, account, order), "fixture")
    event_id = session.scalar(
        select(WfsCreationEvent.id).where(WfsCreationEvent.operation_id == result.id)
    )
    assert event_id is not None
    with pytest.raises(DBAPIError):
        session.execute(delete(WfsCreationEvent).where(WfsCreationEvent.id == event_id))
    session.rollback()


def test_missing_creation_schema_is_explicit():
    from unittest.mock import Mock

    from app.modules.pmc_wfs.repository import require_creation_schema

    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(ApiError) as raised:
        require_creation_schema(session)
    assert raised.value.code == "WFS_SCHEMA_NOT_READY"
    assert raised.value.status_code == 503
