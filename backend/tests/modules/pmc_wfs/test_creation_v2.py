"""Real V2 services and PostgreSQL constraints; only external platform is synthetic."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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


def command(svc, account, order, counts=(12, 8), postal="77449"):
    cmd = allocation(order, counts)
    return CreationCommand(
        **cmd.model_dump(),
        source_account_ref=account,
        preview_hash=svc.preview(cmd).preview_hash,
        idempotency_key=uuid4(),
        return_address=dict(
            address_line1="Test street", city="Katy", state_code="TX", postal_code=postal
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
    assert run_operation(factory, gateway, op.id) is True  # waits for a read-back
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "RUNNING"
    assert all(t.state == "RUNNING" and t.polls == 0 and t.max_polls == 10 for t in current.tickets)
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id)  # a duplicate execute does nothing
    assert len(gateway.creates) == 2
    run_operation(factory, gateway, op.id, "poll")  # not due yet: 3 minutes apart
    assert gateway.reads == []
    make_due(factory, op.id)
    assert run_operation(factory, gateway, op.id, "poll") is False  # nothing left to poll
    session.expire_all()
    assert svc.read(op.id).state == "SUCCEEDED"
    assert len(gateway.creates) == 2 and len(gateway.reads) == 2


def make_due(factory, ident):
    """Move every polling ticket's next read-back into the past (instead of waiting 3 min)."""
    from app.modules.pmc_wfs.creation_models import WfsCreationTicket

    with factory() as s:
        for t in s.scalars(
            select(WfsCreationTicket).where(WfsCreationTicket.operation_id == ident)
        ):
            if t.result.get("polling"):
                past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                t.result = {**t.result, "polling": {**t.result["polling"], "next_at": past}}
        s.commit()


def test_poll_ten_times_then_failed_and_boxes_released(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown, gateway.applied = True, False  # Walmart never created it
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    assert svc.base.detail(order.id).available_boxes == 10
    factory = factory_for(engine)
    waits = [run_operation(factory, gateway, op.id)]
    for _ in range(9):
        make_due(factory, op.id)
        waits.append(run_operation(factory, gateway, op.id, "poll"))
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "RUNNING" and current.tickets[0].polls == 9
    make_due(factory, op.id)
    waits.append(run_operation(factory, gateway, op.id, "poll"))
    session.expire_all()
    current = svc.read(op.id)
    assert current.state == "FAILED"
    assert {t.error_code for t in current.tickets} == {"WFS_RESULT_TIMEOUT"}
    assert "共 10 次" in current.tickets[0].error_message
    assert waits == [True] * 10 + [False] and len(gateway.creates) == 2
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
    # Each ticket was read back before being sent again with the same order id, and once
    # more right after the create (the FC only comes back in the read-back, as on 8088).
    assert len(gateway.reads) == 4 and len(gateway.creates) == 4
    assert len(gateway.prechecks) == 2  # first submission: looked up before the POST
    assert len(set(gateway.creates)) == 2


def test_retry_finds_late_shipment_without_resending(case, engine):
    session, svc, gateway, account, order, *_ = case
    gateway.unknown, gateway.applied = True, False
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    for _ in range(10):
        make_due(factory, op.id)
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


def _tickets(session, ident):
    from app.modules.pmc_wfs.creation_models import WfsCreationTicket

    session.expire_all()
    return list(
        session.scalars(
            select(WfsCreationTicket)
            .where(WfsCreationTicket.operation_id == ident)
            .order_by(WfsCreationTicket.number)
        )
    )


def test_8088_call_order_order_id_precheck_create_read_back(case, engine):
    """Same as the 14 real 8088 creations: look up the order id, POST, read back (FC)."""
    import re

    session, svc, gateway, account, order, *_ = case
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    run_operation(factory_for(engine), gateway, op.id)
    tickets = _tickets(session, op.id)
    ids = [t.inbound_order_id for t in tickets]
    assert all(re.fullmatch(r"PMC-TEST01-\d{8}-\d{2}", i) for i in ids)
    assert len(set(ids)) == 2 and ids == sorted(ids)
    assert gateway.prechecks == ids  # looked up before the first POST
    assert gateway.creates == ids  # Walmart inboundOrderId = our order id
    assert gateway.reads == ids  # read back right after creating
    current = svc.read(op.id)
    assert current.state == "SUCCEEDED"
    assert all(t.shipments[0].fc == "LAX2T-TEST" for t in current.tickets)
    assert all("fc_check" not in t.result for t in tickets)


def test_order_id_already_on_walmart_moves_to_next_number(case, engine):
    from app.modules.pmc_wfs.creation_worker import next_order_id

    session, svc, gateway, account, order, *_ = case
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    first = next_order_id(session, "TEST01")
    prefix, number = first.rsplit("-", 1)
    second = f"{prefix}-{int(number) + 1:02d}"
    gateway.taken = {first, second}  # e.g. made on 8088 the same day
    run_operation(factory_for(engine), gateway, op.id)
    (ticket,) = _tickets(session, op.id)
    third = f"{prefix}-{int(number) + 2:02d}"
    assert ticket.state == "SUCCEEDED" and ticket.inbound_order_id == third
    assert ticket.result["skipped_order_ids"] == [first, second]
    assert gateway.creates == [third]  # never sent under an id Walmart already had
    assert next_order_id(session, "TEST01") == f"{prefix}-{int(number) + 3:02d}"


def test_precheck_failure_sends_nothing_and_retry_keeps_the_order_id(case, engine):
    session, svc, gateway, account, order, *_ = case
    real = gateway.reconcile

    def broken(order_id, snapshot):
        if order_id not in gateway.creates:
            raise TimeoutError()
        return real(order_id, snapshot)

    gateway.reconcile = broken
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    (ticket,) = _tickets(session, op.id)
    assert ticket.state == "FAILED" and ticket.error_code == "WFS_PRECHECK_FAILED"
    assert "未提交" in ticket.result["error_message"]
    assert ticket.result["submissions"] == 0 and gateway.creates == []
    assert svc.base.detail(order.id).available_boxes == 30  # boxes back on the order
    order_id = ticket.inbound_order_id
    gateway.reconcile = real
    svc.dispatch = lambda *_: None
    svc.recover(op.id, "approver-1", "retry")
    run_operation(factory, gateway, op.id, "retry")
    (ticket,) = _tickets(session, op.id)
    assert ticket.state == "SUCCEEDED" and ticket.inbound_order_id == order_id
    assert gateway.prechecks == [order_id] and gateway.creates == [order_id]


def test_fc_missing_after_create_is_read_back_by_the_task(case, engine):
    from app.modules.pmc_wfs.creation_models import WfsCreationTicket
    from app.modules.pmc_wfs.creation_task import due_actions

    session, svc, gateway, account, order, *_ = case
    gateway.fc_on_read = False  # Walmart has not assigned the FC yet
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    factory = factory_for(engine)
    run_operation(factory, gateway, op.id)
    (ticket,) = _tickets(session, op.id)
    assert ticket.state == "SUCCEEDED" and ticket.result["fc_check"]["count"] == 0
    assert svc.read(op.id).tickets[0].shipments[0].fc is None
    assert due_actions([ticket], datetime.now(UTC)) == []  # not due: 3 minutes apart
    later = datetime.now(UTC) + timedelta(minutes=4)
    assert due_actions([ticket], later) == ["labels"]
    with factory() as s:
        t = s.get(WfsCreationTicket, ticket.id)
        past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        t.result = {**t.result, "fc_check": {**t.result["fc_check"], "next_at": past}}
        s.commit()
    gateway.fc_on_read = True
    run_operation(factory, gateway, op.id, "labels")
    (ticket,) = _tickets(session, op.id)
    assert "fc_check" not in ticket.result
    assert svc.read(op.id).tickets[0].shipments[0].fc == "LAX2T-TEST"
    assert len(gateway.creates) == 1


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
        # Rocky 2026-11-04：「确认创建」直接发出，没有单独的「待批准」；点的人就是批准人。
        assert created["state"] == "SUCCEEDED" and len(gateway.creates) == 2
        assert created["approved_by"] == "16"
        assert created["approval_ref"] == f"confirm:{cmd.idempotency_key}"
        replay = client.post(prefix + "/creation-operations", json=cmd.model_dump(mode="json"))
        assert replay.json()["data"]["id"] == created["id"] and len(gateway.creates) == 2
        approve = prefix + f"/creation-operations/{created['id']}/approve"
        again = client.post(approve, json={"approval_ref": "rocky-written:http#1"})
        assert again.status_code == 409  # nothing left to approve
        assert client.get(prefix + "/orders").json()["data"]["items"][0]["available_boxes"] == 10
        assert (
            client.get(prefix + "/creation-operations", params={"order_id": str(order.id)}).json()[
                "data"
            ]["total"]
            == 1
        )
        # 单列表：待创建 1 行 + 2 票各 1 个货件；状态可多选；打印箱唛返回 PDF 并计数
        listed = client.get(prefix + "/rows").json()["data"]
        assert [r["status"] for r in listed["items"]].count("created") == 2
        assert listed["counts"]["pending"] == 1 and listed["total"] == 3
        only = client.get(prefix + "/rows", params=[("status", "pending"), ("status", "failed")])
        assert only.json()["data"]["total"] == 1
        assert client.get(prefix + "/rows", params={"status": "nope"}).status_code == 422
        row = next(r for r in listed["items"] if r["kind"] == "shipment")
        printed = client.post(
            prefix + f"/creation-operations/{created['id']}/labels/{row['shipment_id']}/print"
        )
        assert printed.status_code == 200 and printed.content.startswith(b"%PDF")
        assert printed.headers["content-type"] == "application/octet-stream"
        again = client.get(prefix + "/rows").json()["data"]["items"]
        assert next(r for r in again if r["key"] == row["key"])["print_count"] == 1
        # 不在本机模拟模式：没有「立即拉取」，能力里 simulator = false
        assert client.post(prefix + "/simulator/pull").status_code == 404
        assert client.get(prefix + "/capabilities").json()["data"]["simulator"] is False


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
    # Rocky 2026-11-04: the create permission alone now sends (「待批准」 removed).
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
        assert created.json()["data"]["state"] == "SUCCEEDED" and len(gateway.creates) == 2


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
        created = approved = client.post(prefix + "/creation-operations", json=body).json()["data"]
        assert approved["state"] == "FAILED"
        assert approved["tickets"][0]["error_message"] == "Invalid returnAddress.postalCode"
        gateway.reject = False
        retried = client.post(prefix + f"/creation-operations/{created['id']}/retry")
        assert retried.status_code == 200, retried.text
        assert retried.json()["data"]["state"] == "SUCCEEDED"
        again = client.post(prefix + f"/creation-operations/{created['id']}/retry")
        assert again.status_code == 409


# ----- 待创建货件页签（Rocky 2026-11-04） ---------------------------------------------------


def _store(session, account, store_id="fixture-store", name="测试店铺"):
    from app.modules.data_pages.models import LingxingStoreDimension

    session.add(
        LingxingStoreDimension(
            source_account_ref=account,
            platform_code_raw="walmart",
            platform_code="walmart",
            store_id=store_id,
            store_name=name,
            synced_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_board_tabs_follow_ticket_state(case, engine, monkeypatch):
    from app.modules.pmc_wfs import creation_board
    from app.modules.pmc_wfs.creation_board import CreationBoard

    session, svc, gateway, account, order, *_ = case
    board = CreationBoard(session, {account}, None)
    waiting = svc.submit(command(svc, account, order, (10,)), "fixture")
    rows = board.list("submitting", None, "", 1, 20).items
    assert [r.status_label for r in rows] == ["待人工批准"] and rows[0].awaiting_approval
    assert rows[0].boxes == 10 and rows[0].pks
    gateway.reject = True
    approved(svc, waiting)
    run_operation(factory_for(engine), gateway, waiting.id)
    session.expire_all()
    failed = board.list("failed", None, "", 1, 20).items
    assert failed[0].status_label == "Walmart 拒绝"
    assert failed[0].error_message == "Invalid returnAddress.postalCode"
    gateway.reject = False
    gateway.fc = "ATL1-TEST"
    ok = approved(svc, svc.submit(command(svc, account, order, (12, 8)), "fixture"))
    run_operation(factory_for(engine), gateway, ok.id)
    session.expire_all()
    created = board.list("created", None, "", 1, 20)
    assert created.total == 2
    assert all(r.shipments and r.shipments[0].fc == "ATL1-TEST" for r in created.items)
    assert board.counts(None, "").model_dump() == {"submitting": 0, "failed": 1, "created": 2}
    sid = created.items[0].shipments[0].shipment_id
    assert board.list("created", None, sid, 1, 20).total == 1
    assert board.counts("other-store", "").created == 0
    # SP 发货单已发货的货件移出「已创建未发货」（接入位置）
    monkeypatch.setattr(creation_board, "shipped_shipment_ids", lambda s, ids, *_: {sid})
    assert board.list("created", None, "", 1, 20).total == 1
    assert CreationBoard(session, {"other"}, None).counts(None, "").failed == 0


def test_store_defaults_override_account_and_dialog_change_is_one_off(case):
    from app.modules.pmc_wfs.creation_board import StoreDefaults, StoreDefaultsUpdate
    from app.modules.pmc_wfs.creation_models import WfsCreation
    from app.modules.pmc_wfs.settings_models import WfsSettingsChange

    session, svc, gateway, account, order, *_ = case
    _store(session, account)
    stores = StoreDefaults(session, {account}, None)
    row = next(r for r in stores.list().items if r.store_id == order.store_id)
    assert row.level == "default" and row.ship_date_offset == 15 and row.store_name == "测试店铺"
    saved = stores.update(
        order.store_id,
        StoreDefaultsUpdate(
            transport="SMALL_PARCEL",
            ship_date_offset=9,
            pallet_boxes=10,
            mixed_boxes=1,
            carrier_opt="wm",
            its=True,
            return_address=dict(
                address_line1="Store st", city="Katy", state_code="TX", postal_code="77449"
            ),
        ),
        "rocky",
    )
    assert saved.level == "store" and saved.updated_by == "rocky" and saved.its
    defaults = svc.defaults(account, order.store_id)
    assert defaults.level == "store" and defaults.ship_date_offset == 9
    assert defaults.return_address.address_line1 == "Store st"
    assert svc.defaults(account).level == "default"
    # 弹窗里改了这一次的值，不回写默认值
    cmd = command(svc, account, order, (10,)).model_copy(update={"expected_delivery_at": None})
    op = svc.submit(cmd, "fixture")
    snapshot = session.get(WfsCreation, op.id).snapshot
    assert snapshot["creation_defaults"]["ship_date_offset"] == 9
    assert snapshot["return_address"]["address_line1"] == "Test street"
    assert svc.defaults(account, order.store_id).return_address.address_line1 == "Store st"
    changes = session.scalars(
        select(WfsSettingsChange).where(WfsSettingsChange.entity == "creation_defaults")
    ).all()
    assert any(c.entity_key == f"{account}:{order.store_id}" for c in changes)
    with pytest.raises(ApiError) as err:
        StoreDefaults(session, {"other"}, None).update(order.store_id, cmd_defaults(), "x")
    assert err.value.code == "DATA_SCOPE_DENIED"


def test_common_row_for_all_stores_sits_between_store_and_system_defaults(case):
    """Rocky 2026-11-04: one place for defaults. 「全部店铺通用」 (store_id "*") applies to every
    store without its own row; a store row still wins; the old account row is only a fallback."""
    from app.modules.pmc_wfs.creation_board import StoreDefaults, StoreDefaultsUpdate
    from app.modules.pmc_wfs.settings_models import COMMON_STORE, WfsCreationDefaults

    session, svc, gateway, account, order, *_ = case
    _store(session, account)
    stores = StoreDefaults(session, {account}, None)
    listed = stores.list()
    (common,) = listed.common
    assert common.store_id == COMMON_STORE and common.store_name == "全部店铺通用"
    assert common.level == "default" and common.source_account_ref == account
    assert all(r.store_id != COMMON_STORE for r in listed.items)
    session.merge(
        WfsCreationDefaults(
            source_account_ref=account,
            transport="LTL",
            ship_date_offset=20,
            pallet_boxes=16,
            mixed_boxes=0,
            carrier_opt="own",
            updated_by="fixture",
        )
    )
    session.commit()
    assert svc.defaults(account, order.store_id).level == "account"  # legacy fallback kept
    address = dict(
        address_line1="14125 TELEPHONE AVE", city="CHINO", state_code="CA", postal_code="91710"
    )
    saved = stores.update(
        COMMON_STORE,
        StoreDefaultsUpdate(
            **cmd_defaults().model_dump(exclude={"its", "return_address"}),
            its=True,
            return_address=address,
        ),
        "rocky",
    )
    assert saved.level == "common" and saved.updated_by == "rocky"
    got = svc.defaults(account, order.store_id)
    assert got.level == "common" and got.its and got.ship_date_offset == 15
    assert got.return_address.address_line1 == "14125 TELEPHONE AVE"
    row = next(r for r in stores.list().items if r.store_id == order.store_id)
    assert row.level == "common"  # 沿用通用
    stores.update(order.store_id, cmd_defaults().model_copy(update={"ship_date_offset": 3}), "x")
    assert svc.defaults(account, order.store_id).level == "store"
    assert svc.defaults(account, "another-store").level == "common"
    with pytest.raises(ApiError) as err:
        StoreDefaults(session, {account, "acct-2"}, None).update(COMMON_STORE, cmd_defaults(), "x")
    assert err.value.code == "WFS_SETTINGS_ACCOUNT_REQUIRED"
    with pytest.raises(ApiError) as err:
        stores.update(
            COMMON_STORE, cmd_defaults().model_copy(update={"source_account_ref": "nope"}), "x"
        )
    assert err.value.code == "DATA_SCOPE_DENIED"


def cmd_defaults():
    from app.modules.pmc_wfs.creation_board import StoreDefaultsUpdate

    return StoreDefaultsUpdate(
        transport="LTL", ship_date_offset=15, pallet_boxes=16, mixed_boxes=0, carrier_opt="own"
    )


def test_http_board_and_store_defaults(case, engine):
    session, svc, gateway, account, order, *_ = case
    _store(session, account)
    app = app_for(engine, account, gateway)
    prefix = "/api/pmc/wfs/pending-packing"
    with TestClient(app) as client:
        body = command(svc, account, order, (10,)).model_dump(mode="json")
        assert client.post(prefix + "/creation-operations", json=body).status_code == 200
        listed = client.get(prefix + "/creation-tickets", params={"tab": "created"})
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"]["total"] == 1
        counts = client.get(prefix + "/creation-ticket-counts").json()["data"]
        assert counts == {"submitting": 0, "failed": 0, "created": 1}
        assert client.get(prefix + "/creation-tickets", params={"tab": "x"}).status_code == 422
        stores = client.get(prefix + "/store-creation-defaults").json()["data"]["items"]
        assert any(s["store_id"] == order.store_id for s in stores)
        put = client.put(
            prefix + f"/store-creation-defaults/{order.store_id}",
            json=cmd_defaults().model_dump(mode="json") | {"ship_date_offset": 7},
        )
        assert put.status_code == 200, put.text
        assert put.json()["data"]["level"] == "store"
        got = client.get(
            prefix + "/creation-defaults",
            params={"source_account_ref": account, "store_id": order.store_id},
        ).json()["data"]
        assert got["ship_date_offset"] == 7 and got["level"] == "store"
        common = client.put(
            prefix + "/store-creation-defaults/*", json=cmd_defaults().model_dump(mode="json")
        )
        assert common.status_code == 200, common.text
        assert common.json()["data"]["level"] == "common"
        listed = client.get(prefix + "/store-creation-defaults").json()["data"]
        assert listed["common"][0]["store_name"] == "全部店铺通用"
        bad = client.put(prefix + "/store-creation-defaults/nope", json=cmd_defaults().model_dump())
        assert bad.status_code == 403
        open_rows = client.get(
            "/api/pmc/wfs/pending-packing/orders", params={"arrangement": "open"}
        )
        assert open_rows.status_code == 200, open_rows.text


# ----- 任务中心「WFS 创建结果拉取」 ---------------------------------------------------------


@pytest.fixture
def task_center(case, engine, monkeypatch):
    """Registered task + captured dispatches; runs are executed explicitly by the test."""
    from app.modules.integration_sync import tasks as sync_tasks
    from app.modules.pmc_wfs import creation_task

    session, svc, gateway, account, *_ = case
    assert creation_task.bootstrap(session, account)[1] == "created"  # interface: shared schema
    assert creation_task.bootstrap(session, account) == ("existing", "existing")
    queued = []
    monkeypatch.setattr(sync_tasks, "dispatch_sync_run", queued.append)
    factory = factory_for(engine)
    svc.dispatch = lambda ident, action: creation_task.dispatch_creation(ident, action, factory)

    def run_next():
        from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncRun

        run = session.get(IntegrationSyncRun, queued.pop(0))
        interface = session.get(IntegrationInterface, run.interface_id)
        handler = creation_task.WfsCreationResultPollHandler(
            session, gateway=gateway, factory=factory
        )
        handler.execute(run, interface)
        session.refresh(run)
        return run

    def queue(reason="tick"):
        run_id = creation_task.request_run(session, account, "fixture", reason)
        queued.append(run_id) if run_id and run_id not in queued else None
        return run_id

    return creation_task, queued, run_next, queue, factory


def test_task_center_registration_is_off_until_switched_on(case, task_center):
    from app.modules.integration_sync.models import IntegrationSyncConfig

    session, svc, gateway, account, *_ = case
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.source_account_ref == account)
    ).one()
    assert config.is_enabled and not config.schedule_enabled
    assert config.schedule_cron == "*/3 * * * *" and config.schedule_timezone == "UTC"


def test_task_center_submits_polls_ten_times_then_fails(case, engine, task_center):
    from app.modules.integration_sync.models import IntegrationSyncRunWorkItem

    session, svc, gateway, account, order, *_ = case
    creation_task, queued, run_next, queue, factory = task_center
    gateway.unknown, gateway.applied = True, False
    op = approved(svc, svc.submit(command(svc, account, order), "fixture"))
    assert len(queued) == 1  # approval runs the task now, no 3-minute wait
    run = run_next()
    assert run.status == "succeeded" and run.work_items_total == 1
    work = session.scalars(
        select(IntegrationSyncRunWorkItem).where(IntegrationSyncRunWorkItem.run_id == run.id)
    ).one()
    assert work.request_safe_params == {"operation_id": str(op.id), "actions": ["execute"]}
    assert work.status == "succeeded" and work.response_count == 2
    session.expire_all()
    assert svc.read(op.id).state == "RUNNING" and len(gateway.creates) == 2
    queue()
    assert run_next().work_items_total == 0  # not due: nothing done this tick
    for count in range(1, 11):
        make_due(factory, op.id)
        queue()
        assert run_next().status == "succeeded"
        session.expire_all()
        current = svc.read(op.id)
        if count < 10:
            assert current.state == "RUNNING" and current.tickets[0].polls == count
    assert current.state == "FAILED"
    assert {t.error_code for t in current.tickets} == {"WFS_RESULT_TIMEOUT"}
    assert len(gateway.creates) == 2 and len(gateway.reads) == 20
    assert svc.base.detail(order.id).available_boxes == 30


def test_task_center_retry_reconcile_and_labels(case, engine, task_center):
    session, svc, gateway, account, order, *_ = case
    creation_task, queued, run_next, queue, factory = task_center
    gateway.reject = True
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    run_next()
    session.expire_all()
    assert svc.read(op.id).state == "FAILED"
    gateway.reject, gateway.fail_label = False, True
    svc.recover(op.id, "approver-1", "retry")
    assert run_next().status == "succeeded"
    session.expire_all()
    current = svc.read(op.id)
    # read back before resending + read back right after creating (FC)
    assert current.state == "SUCCEEDED" and len(gateway.reads) == 2
    assert current.tickets[0].shipments[0].label_state == "FAILED"
    gateway.fail_label = False
    svc.recover(op.id, "approver-1", "labels")
    run = run_next()
    assert run.work_items_total == 1
    session.expire_all()
    assert svc.read(op.id).tickets[0].shipments[0].label_state == "READY"
    queue()
    assert run_next().work_items_total == 0  # a label request is handled once


def test_task_center_disabled_switch_and_creation_mode(case, engine, task_center):
    from app.modules.integration_sync.models import IntegrationSyncConfig
    from app.modules.pmc_wfs.creation_models import WfsCreationEvent

    session, svc, gateway, account, order, *_ = case
    creation_task, queued, run_next, queue, factory = task_center
    queue()
    assert run_next().status == "succeeded"  # nothing pending: an empty successful run
    gateway.unknown = True
    op = approved(svc, svc.submit(command(svc, account, order, (10,)), "fixture"))
    gateway.enabled = False
    gateway.reason = "Walmart 创建尚未启用"
    run = run_next()
    assert run.status == "failed" and run.error_code == "WFS_CREATION_DISABLED"
    assert run.error_message == "Walmart 创建尚未启用"
    gateway.enabled = True
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.source_account_ref == account)
    ).one()
    config.is_enabled = False
    session.commit()
    assert queue() is None
    svc.recover(op.id, "approver-1", "reconcile")
    kinds = session.scalars(
        select(WfsCreationEvent.kind).where(WfsCreationEvent.operation_id == op.id)
    ).all()
    assert "waiting_task_center" in kinds


def test_execution_routes_the_task_to_the_wfs_handler(case, task_center, monkeypatch):
    from app.modules.integration_sync.execution import SyncRunExecutionService
    from app.modules.pmc_wfs import creation_task as module

    session, *_ = case
    creation_task, queued, run_next, queue, factory = task_center
    seen = []

    class Fake:
        def __init__(self, s):
            pass

        def execute(self, run, interface):
            seen.append((run.interface_key, interface.handler_key))

    monkeypatch.setattr(module, "WfsCreationResultPollHandler", Fake)
    SyncRunExecutionService(session).execute(queue())
    assert seen == [(module.INTERFACE_KEY, module.HANDLER_KEY)]


@pytest.mark.parametrize(
    ("postal", "first_state", "final_state"),
    [
        ("77449", "SUCCEEDED", "SUCCEEDED"),
        ("00000", "FAILED", "FAILED"),
        ("99999", "RUNNING", "SUCCEEDED"),
    ],
)
def test_local_simulator_runs_the_real_worker_path(
    case, engine, tmp_path, monkeypatch, postal, first_state, final_state
):
    """The simulated channel goes through the same worker as Walmart: order id, look-up,
    create, read-back FC, label. The postcode picks the outcome (Rocky's demo)."""
    from app.modules.pmc_wfs import local_simulator

    monkeypatch.setenv(local_simulator.STATE_ENV, str(tmp_path / "sim.json"))
    monkeypatch.setattr(local_simulator, "simulator_active", lambda: True)
    sim = local_simulator.LocalSimulatorGateway()
    session, svc, _, account, order, *_ = case
    op = approved(svc, svc.submit(command(svc, account, order, (20,), postal), "fixture"))
    run_operation(factory_for(engine), sim, op.id)
    (ticket,) = _tickets(session, op.id)
    assert ticket.state == first_state
    assert ticket.inbound_order_id and ticket.inbound_order_id.startswith("PMC-")
    if first_state == "RUNNING":  # 提交中: the next pull finds it by order id
        run_operation(factory_for(engine), sim, op.id, "reconcile")
        (ticket,) = _tickets(session, op.id)
    assert ticket.state == final_state
    current = svc.read(op.id)
    if final_state == "SUCCEEDED":
        (shipment,) = current.tickets[0].shipments
        assert shipment.shipment_id.startswith("SIM") and shipment.fc == "LAX2T"
        assert b"SIMULATED" in svc.label(op.id, shipment.shipment_id)
    else:
        assert "00000" in str(ticket.result) or "postalCode" in str(ticket.result)


def _publish_shipping_list(session, account, code, cargo_codes):
    """A current board publication whose SP shipping-list batch holds ``code``."""
    from datetime import date

    from app.modules.pmc_wfs.lingxing_models import (
        LingxingWfsShippingListOds,
        WfsBoardPublication,
    )

    run_id = uuid4()
    session.add(
        WfsBoardPublication(
            source_account_ref=account,
            is_current=True,
            cargo_run_id=uuid4(),
            shipping_run_id=run_id,
            coverage_start=date(2026, 10, 1),
            coverage_end=date(2026, 11, 4),
            source_observed_at=datetime.now(UTC),
            builder_version="test",
            quality_report={},
        )
    )
    session.add(
        LingxingWfsShippingListOds(
            run_id=run_id,
            raw_request_ref_id=uuid4(),
            source_account_ref=account,
            source_item_ordinal=1,
            payload_json={},
            observed_at=datetime.now(UTC),
            shipping_code=code,
            cargo_codes=list(cargo_codes),
            logistics_numbers=[],
            tracking_numbers=[],
        )
    )
    session.commit()


def test_single_list_rows_status_split_sp_number_and_print_count(case, engine):
    """Rocky 12–16 + split: one list, a status on every row; one row per ticket × shipment;
    the PK repeats; shipped (has an SP number) hidden unless asked; prints are counted."""
    from app.modules.pmc_wfs.creation_board import CreationRows, RowQuery

    session, svc, gateway, account, order, *_ = case
    rows = CreationRows(svc.base)
    first = rows.list(RowQuery())
    assert [(r.kind, r.status) for r in first.items] == [("pending", "pending")]
    assert first.items[0].pending.available_boxes == 30

    op = svc.submit(command(svc, account, order, (12, 8)), "fixture")
    awaiting = rows.list(RowQuery())  # an old record still waiting for approval: 提交中
    assert sorted(r.status for r in awaiting.items) == ["pending", "submitting", "submitting"]
    assert awaiting.counts.submitting == 2 and awaiting.counts.pending == 1
    assert {r.pk for r in awaiting.items} == {order.pk}  # the PK repeats on every row
    pending = next(r for r in awaiting.items if r.kind == "pending")
    assert pending.pending.available_boxes == 10  # the rest of the boxes stay 待创建

    approved(svc, op)
    run_operation(factory_for(engine), gateway, op.id)
    session.expire_all()
    created = [r for r in rows.list(RowQuery()).items if r.kind == "shipment"]
    assert [r.status for r in created] == ["created", "created"]
    assert all(r.shipment_id and r.fc == "LAX2T-TEST" and r.label_state == "READY" for r in created)
    assert len({r.ticket.inbound_order_id for r in created}) == 2

    sid = created[0].shipment_id
    _publish_shipping_list(session, account, "SP-TEST-0001", [sid, "UNRELATED"])
    default = rows.list(RowQuery())
    assert sid not in {r.shipment_id for r in default.items}  # 已发货默认隐藏
    assert default.counts.shipped == 1 and default.counts.created == 1
    shown = rows.list(RowQuery(show_shipped=True))
    shipped = next(r for r in shown.items if r.shipment_id == sid)
    assert shipped.status == "shipped" and shipped.shipping_code == "SP-TEST-0001"
    assert rows.list(RowQuery(keyword="SP-TEST-0001", show_shipped=True)).total == 1
    assert rows.list(RowQuery(statuses=["pending"])).total == 1
    assert CreationRows(type(svc.base)(session, {"other"}, None)).list(RowQuery()).total == 0

    other = created[1].shipment_id
    for _ in range(2):
        assert svc.print_label(op.id, other, "rocky").startswith(b"%PDF")
    session.expire_all()
    row = next(r for r in rows.list(RowQuery()).items if r.shipment_id == other)
    assert row.print_count == 2 and row.printed_by == "rocky" and row.printed_at is not None
    with pytest.raises(ApiError):
        svc.print_label(op.id, "NOT-A-SHIPMENT", "rocky")


def test_demo_sp_number_counts_only_for_demo_operations(case, engine):
    from app.modules.pmc_wfs.creation_board import CreationRows, RowQuery
    from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket

    session, svc, gateway, account, order, *_ = case
    op = approved(svc, svc.submit(command(svc, account, order, (20,)), "fixture"))
    run_operation(factory_for(engine), gateway, op.id)
    session.expire_all()
    ticket = session.scalar(
        select(WfsCreationTicket).where(WfsCreationTicket.operation_id == op.id)
    )
    sid = next(iter(ticket.result["labels"]))
    ticket.result = {**ticket.result, "simulated_shipping": {sid: "DEMO-SP-0001"}}
    session.commit()
    rows = CreationRows(svc.base)
    assert rows.list(RowQuery(show_shipped=True)).counts.shipped == 0  # real op: ignored
    row = session.get(WfsCreation, op.id)
    row.snapshot = {**row.snapshot, "demo_seed": "wfs-sim-20261104"}
    session.commit()
    assert rows.list(RowQuery(show_shipped=True)).counts.shipped == 1


def test_local_demo_seed_covers_every_state_and_clear_removes_only_demo(
    case, engine, tmp_path, monkeypatch
):
    """seed: DEMO-01 … 07 through the real CreationService + worker (simulated Walmart);
    clear: every DEMO row gone, the real packing order untouched."""
    from app.modules.pmc_domestic.packing_models import PackingOrder
    from app.modules.pmc_wfs import local_demo, local_simulator
    from app.modules.pmc_wfs.creation_board import CreationRows, RowQuery

    if get_settings().app_env.value != "local":
        pytest.skip("the demo seed runs only on APP_ENV=local (that refusal is tested below)")
    monkeypatch.setenv(local_simulator.STATE_ENV, str(tmp_path / "sim.json"))
    session, svc, _, account, order, *_ = case
    factory = factory_for(engine)
    result = local_demo.seed(factory, account)
    assert result["orders"] == [f"DEMO-0{n}" for n in range(1, 8)]
    with pytest.raises(local_simulator.SimulatorRefused, match="clear"):
        local_demo.seed(factory, account)  # never twice

    session.expire_all()
    rows = CreationRows(svc.base).list(RowQuery(only_test=True, show_shipped=True, page_size=200))
    demo = [r for r in rows.items if r.pk.startswith("DEMO-")]
    by_pk = {}
    for r in demo:
        by_pk.setdefault(r.pk, []).append(r.status)
    assert sorted(by_pk["DEMO-01"]) == ["pending"]
    assert sorted(by_pk["DEMO-02"]) == ["created", "pending", "submitting"]
    assert sorted(by_pk["DEMO-03"]) == ["failed", "pending"]  # boxes released back
    assert sorted(by_pk["DEMO-04"]) == ["pending", "submitting"]  # 99999: until the next pull
    assert by_pk["DEMO-05"] == ["shipped"]
    assert by_pk["DEMO-06"] == ["shipped", "shipped"]
    assert "created" in by_pk["DEMO-07"]
    printed = next(r for r in demo if r.pk == "DEMO-02" and r.status == "created")
    assert printed.print_count == 2 and printed.fc == "LAX2T"
    polling = next(r for r in demo if r.pk == "DEMO-02" and r.status == "submitting")
    assert "3/10" in (polling.detail or "")
    shared = {r.shipping_code for r in demo if r.pk == "DEMO-06"}
    assert len(shared) == 1 and shared.pop().startswith("DEMO-SP")
    failed = next(r for r in demo if r.status == "failed")
    assert "postalCode" in (failed.detail or "")
    no_label = next(r for r in demo if r.pk == "DEMO-07" and r.kind == "shipment")
    assert no_label.label_state == "FAILED"
    pending = next(r for r in demo if r.pk == "DEMO-02" and r.kind == "pending")
    assert pending.pending.available_boxes == 4
    default = CreationRows(svc.base).list(RowQuery(only_test=True, page_size=200))
    assert not {"DEMO-05", "DEMO-06"} & {r.pk for r in default.items}  # 已发货默认隐藏

    # Rocky's steps on the simulated channel: 重试 DEMO-03, 补取 DEMO-07, 立即拉取
    # (DEMO-02, DEMO-04), 确认创建 on DEMO-01 — all end as 已创建未发货 with FC LAX2T.
    monkeypatch.setattr(local_simulator, "simulator_active", lambda: True)
    sim = local_simulator.LocalSimulatorGateway()
    ops = {k: UUID(v) for k, v in result["operations"].items()}
    live = CreationService(
        svc.base, sim, lambda ident, action: run_operation(factory, sim, UUID(ident), action)
    )
    live.recover(ops["DEMO-03"], "rocky", "retry")
    live.recover(ops["DEMO-07"], "rocky", "labels")
    live.recover(ops["DEMO-02"], "rocky", "reconcile")
    live.recover(ops["DEMO-04"], "rocky", "reconcile")
    demo1 = next(r for r in demo if r.pk == "DEMO-01").pending
    cmd = AllocationCommand(
        order_id=demo1.order.id,
        expected_version=demo1.order.version,
        expected_box_version=demo1.order.box_set.version,
        shipping_boxes=10,
        shipment_count=1,
        shipment_boxes=[10],
    )
    confirmed = live.submit_and_send(
        CreationCommand(
            **cmd.model_dump(),
            source_account_ref=account,
            preview_hash=live.preview(cmd).preview_hash,
            idempotency_key=uuid4(),
            return_address=dict(local_demo.RETURN_ADDRESS),
        ),
        "rocky",
    )
    assert confirmed.state == "SUCCEEDED" and confirmed.approved_by == "rocky"
    session.expire_all()
    after = CreationRows(svc.base).list(RowQuery(only_test=True, page_size=200)).items
    for pk in ("DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-07"):
        shipped_rows = [r for r in after if r.pk == pk and r.kind == "shipment"]
        assert shipped_rows and all(r.status == "created" for r in shipped_rows), pk
        assert all(r.fc == "LAX2T" and r.label_state == "READY" for r in shipped_rows), pk

    cleared = local_demo.clear(factory)
    # 6 seeded + DEMO-01 made above (+ any op another test in this schema marked demo_seed)
    assert cleared["orders"] == 7 and cleared["operations"] >= 7
    session.expire_all()
    assert session.scalar(select(func.count()).where(PackingOrder.pk.like("DEMO-%"))) == 0
    assert session.get(PackingOrder, order.id) is not None
    assert CreationRows(svc.base).list(RowQuery(show_shipped=True)).total == 1
    assert local_demo.clear(factory)["orders"] == 0


@pytest.mark.parametrize("env", ["production", "staging", "test"])
def test_local_demo_seed_and_clear_refuse_outside_local(monkeypatch, env):
    from types import SimpleNamespace

    from sqlalchemy.engine import make_url

    from app.core import config
    from app.modules.pmc_wfs import local_demo
    from app.modules.pmc_wfs.local_simulator import SimulatorRefused

    url = "postgresql+psycopg://dev@127.0.0.1:55432/szzsbj_dev"
    settings = SimpleNamespace(
        app_env=SimpleNamespace(value=env), sqlalchemy_url=lambda: make_url(url)
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    def factory():
        raise AssertionError("must refuse before opening a database session")

    for call in (local_demo.seed, local_demo.clear):
        with pytest.raises(SimulatorRefused, match="APP_ENV=local"):
            call(factory)


def test_local_demo_refuses_a_session_on_another_database(monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy.engine import make_url

    from app.core import config
    from app.modules.pmc_wfs import local_demo
    from app.modules.pmc_wfs.local_simulator import SimulatorRefused

    local = make_url("postgresql+psycopg://dev@127.0.0.1:55432/szzsbj_dev")
    settings = SimpleNamespace(app_env=SimpleNamespace(value="local"), sqlalchemy_url=lambda: local)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    remote = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            url=make_url("postgresql+psycopg://a@10.1.1.1:5432/szzsbj")
        )
    )
    with pytest.raises(SimulatorRefused):
        local_demo.guard(remote)
