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
from app.modules.pmc_wfs.creation_schemas import (
    AllocationCommand,
    ApprovalCommand,
    CreationCommand,
)
from app.modules.pmc_wfs.creation_service import CreationService
from app.modules.pmc_wfs.creation_worker import run_operation
from app.modules.pmc_wfs.gateway import DisabledGateway
from app.modules.pmc_wfs.repository import assert_not_occupied
from app.modules.pmc_wfs.service import WfsService
from tests.modules.pmc_wfs.v2_support import (
    SyntheticGateway,
    app_for,
    engine_and_local_schema,
    engine_and_schema,
    factory_for,
    seed_fixture,
)


@pytest.fixture(scope="module")
def engine():
    if os.environ.get("WFS_V2_TEST_DATABASE_URL"):
        get_settings.cache_clear()
        value = engine_and_schema()
        yield value
        value.dispose()
        return
    if os.environ.get("WFS_LOCAL_INTEGRATION") == "1":
        get_settings.cache_clear()
        value, drop = engine_and_local_schema()
        try:
            yield value
        finally:
            drop()
        return
    pytest.skip("requires WFS_V2_TEST_DATABASE_URL or WFS_LOCAL_INTEGRATION=1")


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


def approved(svc, op, ref="rocky-written:wfs-test"):
    """The written human approval every creation needs before execution (red line)."""
    return svc.approve(op.id, ApprovalCommand(approval_ref=ref), "approver-1")


def test_partial_boxes_no_ows_and_replay(case):
    session, svc, gateway, account, order, box, line = case
    cmd = command(svc, account, order)
    op = svc.submit(cmd, "fixture")
    assert [t.allocation.boxes for t in op.tickets] == [12, 8]
    assert svc.base.detail(order.id).available_boxes == 10
    assert svc.submit(cmd, "fixture").id == op.id
    # Machine checks are recorded, but nothing is approved and nothing is queued.
    assert op.state == "AWAITING_APPROVAL" and op.approval_mode == "manual"
    assert op.automatic_checks_at is not None
    assert op.approved_at is None and op.approval_ref is None and op.approved_by is None
    kinds = set(
        session.scalars(select(WfsCreationEvent.kind).where(WfsCreationEvent.operation_id == op.id))
    )
    assert "automatic_checks_passed" in kinds
    assert not any("approv" in kind and kind != "automatic_checks_passed" for kind in kinds)
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


def test_unknown_then_poll_does_not_recreate(case, engine):
    """No trustworthy answer -> 提交中, read back by our order id; never a second POST."""
    session, svc, gateway, account, order, *_ = case
    gateway.unknown = True
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    factory = factory_for(engine)
    scheduled = []
    schedule = lambda ident, action, delay: scheduled.append((action, delay))  # noqa: E731
    run_operation(factory, gateway, op.id, schedule=schedule)
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "RUNNING"
    assert all(t.state == "RUNNING" and t.polls == 0 and t.max_polls == 10 for t in current.tickets)
    assert scheduled == [("poll", 180)]
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id)  # a duplicate execute does nothing
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id, "poll", schedule=schedule)
    session.expire_all()
    assert svc.read(op.id).state == "SUCCEEDED"
    assert len(gateway.creates) == 2 and len(gateway.reads) == 2
    assert scheduled == [("poll", 180)]  # nothing left to poll


def test_poll_ten_times_then_failed_and_boxes_released(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown, gateway.applied = True, False  # Walmart never created it
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    assert svc.base.detail(order.id).available_boxes == 10
    factory = factory_for(engine)
    scheduled = []
    schedule = lambda ident, action, delay: scheduled.append(action)  # noqa: E731
    run_operation(factory, gateway, op.id, schedule=schedule)
    for _ in range(9):
        run_operation(factory, gateway, op.id, "poll", schedule=schedule)
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "RUNNING" and current.tickets[0].polls == 9
    run_operation(factory, gateway, op.id, "poll", schedule=schedule)
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "FAILED"
    assert {t.error_code for t in current.tickets} == {"WFS_RESULT_TIMEOUT"}
    assert "共 10 次" in current.tickets[0].error_message
    assert len(scheduled) == 10 and len(gateway.creates) == 2
    assert len(gateway.reads) == 20
    assert svc.base.detail(order.id).available_boxes == 30  # boxes back on the order


def test_rejection_shows_reason_releases_boxes_and_retry_reads_back_first(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.reject = True
    dispatched = []
    svc.dispatch = lambda ident, action: dispatched.append(action)
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "FAILED"
    assert current.tickets[0].error_message == "Invalid returnAddress.postalCode"
    assert current.tickets[0].error_code == "WFS_PLATFORM_REJECTED"
    assert svc.base.detail(order.id).available_boxes == 30
    gateway.reject = False
    retried = svc.recover(op.id, "approver-1", "retry")
    assert retried.state == "QUEUED" and dispatched[-1] == "retry"
    assert svc.base.detail(order.id).available_boxes == 10  # held again
    run_operation(factory, gateway, op.id, "retry")
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "SUCCEEDED"
    assert all(t.submissions == 2 and t.error_message is None for t in current.tickets)
    # Each ticket was read back before being sent again with the same order id.
    assert len(gateway.reads) == 2 and len(gateway.creates) == 4
    assert len(set(gateway.creates)) == 2


def test_retry_finds_late_shipment_without_resending(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown, gateway.applied = True, False
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    for _ in range(10):
        run_operation(factory, gateway, op.id, "poll")
    session.expire_all()
    assert svc.read(op.id).state == "FAILED"
    gateway.created.update(gateway.creates)  # Walmart shows it late
    svc.dispatch = lambda *_: None
    svc.recover(op.id, "approver-1", "retry")
    run_operation(factory, gateway, op.id, "retry")
    session.expire_all()
    assert svc.read(op.id).state == "SUCCEEDED"
    assert len(gateway.creates) == 1  # never posted a second time


def test_no_resubmit_while_submitting(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown = True
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    run_operation(factory_for(engine), gateway, op.id)
    with pytest.raises(ApiError) as err:
        svc.recover(op.id, "approver-1", "retry")
    assert err.value.code == "WFS_SUBMITTING"
    session.rollback()
    with pytest.raises(ApiError) as err:
        approved(svc, op)
    assert err.value.details["reason"] == "WFS_APPROVAL_NOT_PENDING"
    session.rollback()


def test_retry_refused_when_boxes_taken_meanwhile(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.reject = True
    op = approved(svc, svc.submit(command(svc, account, order, (30,)), "fixture"))
    run_operation(factory_for(engine), gateway, op.id)
    session.expire_all()
    assert svc.base.detail(order.id).available_boxes == 30
    other = svc.submit(command(svc, account, order, (30,)), "fixture")  # takes all boxes
    assert other.state == "AWAITING_APPROVAL"
    with pytest.raises(ApiError) as err:
        svc.recover(op.id, "approver-1", "retry")
    assert err.value.code == "WFS_BOXES_OCCUPIED_OR_INVALID"
    session.rollback()


def test_defaults_from_settings_and_fc_from_walmart(case, engine):
    from app.modules.pmc_wfs.creation_models import WfsCreation
    from app.modules.pmc_wfs.settings_models import WfsCreationDefaults

    session, svc, gateway, account, order, *_ = case
    session.merge(
        WfsCreationDefaults(
            source_account_ref=account,
            transport="LTL",
            ship_date_offset=20,
            pallet_boxes=16,
            mixed_boxes=2,
            carrier_opt="own",
            updated_by="fixture",
        )
    )
    session.commit()
    defaults = svc.defaults(account)
    assert defaults.saved and defaults.ship_date_offset == 20 and defaults.mixed_boxes == 2
    cmd = command(svc, account, order, (20,)).model_copy(update={"expected_delivery_at": None})
    op = svc.submit(cmd, "fixture")
    snapshot = session.get(WfsCreation, op.id).snapshot
    assert snapshot["creation_defaults"]["mixed_boxes"] == 2
    assert snapshot["expected_delivery_at"].startswith(defaults.expected_delivery_date)
    gateway.fc = "ATL1-TEST"
    approved(svc, op)
    run_operation(factory_for(engine), gateway, op.id)
    session.expire_all()
    shipment = svc.read(op.id).tickets[0].shipments[0]
    assert shipment.fc == "ATL1-TEST"
    assert gateway.labels[0][1] == 20  # one shipment: carton count = ticket boxes


def test_labels_retry_only_and_scope(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.fail_label = True
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
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
        created = response.json()["data"]
        assert created["state"] == "AWAITING_APPROVAL" and gateway.creates == []
        assert created["approval_mode"] == "manual" and created["approved_at"] is None
        approve = prefix + f"/creation-operations/{created['id']}/approve"
        assert client.post(approve, json={"approval_ref": "bad ref"}).status_code == 422
        response = client.post(approve, json={"approval_ref": "rocky-written:http#1"})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["state"] == "SUCCEEDED"
        assert response.json()["data"]["approved_by"] == "16"
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
    # Creating (holding boxes) and approving the Walmart write are separate permissions.
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="16",
        permissions=frozenset({"page:pmc:wfs:view", "action:pmc:wfs-pending-packing:create"}),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/pmc/wfs/pending-packing/creation-operations",
            json=command(svc, account, order).model_dump(mode="json"),
        )
        assert created.status_code == 200, created.text
        denied = client.post(
            f"/api/pmc/wfs/pending-packing/creation-operations/{created.json()['data']['id']}"
            "/approve",
            json={"approval_ref": "rocky-written:perm#1"},
        )
        assert denied.status_code == 403
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


def test_worker_never_calls_walmart_without_human_approval(case, engine):
    """Red line: no create / reconcile / label call while the operation is unapproved."""
    session, svc, gateway, account, order, *_ = case
    dispatched = []
    svc.dispatch = lambda ident, action: dispatched.append((ident, action))
    op = svc.submit(command(svc, account, order), "fixture")
    assert dispatched == []  # submit holds boxes but dispatches nothing
    factory = factory_for(engine)
    for action in ("execute", "reconcile", "labels"):
        run_operation(factory, gateway, op.id, action)
    assert gateway.creates == []
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "AWAITING_APPROVAL"
    assert all(t.state == "QUEUED" for t in current.tickets)
    refusals = session.scalar(
        select(func.count())
        .select_from(WfsCreationEvent)
        .where(
            WfsCreationEvent.operation_id == op.id,
            WfsCreationEvent.kind == "refused_unapproved",
        )
    )
    assert refusals == 3
    with pytest.raises(ApiError) as err:
        svc.recover(op.id, "fixture", "reconcile")
    assert err.value.details["reason"] == "WFS_APPROVAL_REQUIRED"
    session.rollback()
    # The written approval is recorded with who and when, and only then is it dispatched.
    result = approved(svc, op, "rocky-written:2026-11-01#1")
    assert result.state == "QUEUED" and result.approval_ref == "rocky-written:2026-11-01#1"
    assert result.approved_by == "approver-1" and result.approved_at is not None
    assert dispatched == [(str(op.id), "execute")]
    with pytest.raises(ApiError) as err:
        approved(svc, op)
    assert err.value.details["reason"] == "WFS_APPROVAL_NOT_PENDING"
    session.rollback()
    run_operation(factory, gateway, op.id)
    assert len(gateway.creates) == 2
    session.expire_all()
    assert svc.read(op.id).state == "SUCCEEDED"


def test_database_refuses_leaving_awaiting_approval_without_a_record(case):
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    from app.modules.pmc_wfs.creation_models import WfsCreation

    session, svc, gateway, account, order, *_ = case
    op = svc.submit(command(svc, account, order), "fixture")
    with pytest.raises(IntegrityError):
        session.execute(update(WfsCreation).where(WfsCreation.id == op.id).values(state="QUEUED"))
        session.flush()
    session.rollback()


def test_approval_ref_is_validated():
    with pytest.raises(ValidationError):
        ApprovalCommand(approval_ref="")
    with pytest.raises(ValidationError):
        ApprovalCommand(approval_ref="has space")
    assert ApprovalCommand(approval_ref="rocky-written:2026-11-01#1").approval_ref


def test_http_defaults_capabilities_and_retry(case, engine):
    _, svc, gateway, account, order, *_ = case
    gateway.reject = True
    app = app_for(engine, account, gateway)
    prefix = "/api/pmc/wfs/pending-packing"
    with TestClient(app) as client:
        caps = client.get(prefix + "/capabilities").json()["data"]
        assert caps["creation_enabled"] is True and caps["preview_enabled"] is True
        defaults = client.get(prefix + "/creation-defaults", params={"source_account_ref": account})
        assert defaults.status_code == 200, defaults.text
        assert defaults.json()["data"]["ship_date_offset"] == 15  # 8088 default
        denied = client.get(prefix + "/creation-defaults", params={"source_account_ref": "x"})
        assert denied.status_code == 403
        body = command(svc, account, order, (20,)).model_dump(mode="json")
        body["expected_delivery_at"] = None
        created = client.post(prefix + "/creation-operations", json=body).json()["data"]
        approved = client.post(
            prefix + f"/creation-operations/{created['id']}/approve",
            json={"approval_ref": "rocky-written:http#2"},
        ).json()["data"]
        assert approved["state"] == "FAILED"
        assert approved["tickets"][0]["error_message"] == "Invalid returnAddress.postalCode"
        gateway.reject = False
        retried = client.post(prefix + f"/creation-operations/{created['id']}/retry")
        assert retried.status_code == 200, retried.text
        assert retried.json()["data"]["state"] == "SUCCEEDED"
        again = client.post(prefix + f"/creation-operations/{created['id']}/retry")
        assert again.status_code == 409
