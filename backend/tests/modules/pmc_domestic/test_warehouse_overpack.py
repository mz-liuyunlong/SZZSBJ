"""Local rollback integration of stock budgets, exception closure and permissions."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import test_packing_warehouse as warehouse_base
from sqlalchemy import func, select
from test_packing_warehouse import boxes, done

from app.core.api import ApiError
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation as Extra
from app.modules.pmc_domestic.packing_stock_repository import PackingStockRepository
from app.modules.pmc_domestic.warehouse_models import PackingNotificationOutbox as Notice
from app.modules.pmc_domestic.warehouse_schemas import (
    PackageInput,
    SupplementalInboundCommand,
    SupplementalSyncCommand,
    WarehouseFilter,
)
from app.modules.pmc_domestic.warehouse_service import WarehouseService

db = warehouse_base.db
seeded = warehouse_base.seeded
order = warehouse_base.order


def finish(row, reason=None):
    cmd = done(row)
    cmd.reason = reason
    cmd.confirm_extra = True
    cmd.package = PackageInput(length_cm=10, width_cm=8, height_cm=3, gross_weight_g=100)
    return cmd


def save(svc, ident, scope, qty):
    row = svc.detail(ident, scope)
    return svc.command(ident, "boxes", boxes(row, qty), "warehouse", scope)


def base(row):
    return dict(
        source_account_ref=row.source_account_ref,
        expected_version=row.version,
        idempotency_key=uuid4(),
    )


def add_source(db, pub, qty, ib="IBSUPPLEMENT", sku="FIXTURE-SKU", parent=None):
    board = Board(
        id=uuid4(),
        publication_id=pub.id,
        source_account_ref=pub.source_account_ref,
        source_warehouse_id=pub.source_warehouse_id,
        inbound_order_sn=ib,
        sku=sku,
        store_id="fixture-store",
        attribution_key="fixture-store",
        arrival_business_date=pub.coverage_end,
        balance_num=qty,
        payload_json={
            "available_good_num": qty,
            "parent_inbound_qty": qty if parent is None else parent,
            "purchase_order_sns": [],
        },
    )
    db.add(board)
    db.commit()
    return board


def fresh_publication(db, old):
    previous = list(db.scalars(select(Board).where(Board.publication_id == old.id)))
    old.is_current = False
    db.flush()
    pub = Pub(
        source_account_ref=old.source_account_ref,
        source_warehouse_id=old.source_warehouse_id,
        is_current=True,
        status="published",
        batch_run_id=uuid4(),
        statement_run_ids=[str(uuid4())],
        coverage_start=old.coverage_start,
        coverage_end=old.coverage_end,
        source_observed_at=datetime.now(UTC),
        builder_version=old.builder_version,
        quality_report={"fixture": True},
    )
    db.add(pub)
    db.flush()
    for b in previous:
        db.add(
            Board(
                publication_id=pub.id,
                id=b.id,
                source_account_ref=b.source_account_ref,
                source_warehouse_id=b.source_warehouse_id,
                inbound_order_sn=b.inbound_order_sn,
                sku=b.sku,
                store_id=b.store_id,
                attribution_key=b.attribution_key,
                arrival_business_date=b.arrival_business_date,
                balance_num=b.balance_num,
                payload_json=dict(b.payload_json),
            )
        )
    db.commit()
    return pub


def blocked_case(db, order):
    approved, account, pub = order
    scope = frozenset({account})
    svc = WarehouseService(db)
    saved = save(svc, approved.id, scope, 13)
    cmd = finish(saved, "实物多于账面库存")
    result = svc.command(saved.id, "done", cmd, "warehouse", scope)
    assert result.status == "todo" and result.command_outcome == "blocked"
    assert result.variance_case.quantity == 8 and result.variance_case.gap_qty == 3
    assert result.box_set.completed_at is None
    return svc, result, scope, pub, cmd


def test_current_q_deduction_and_cross_inbound_extra_holds(db, order):
    approved, account, pub = order
    scope = frozenset({account})
    svc = WarehouseService(db)
    assert svc.detail(approved.id, scope).extra_available == 5
    add_source(db, pub, 3)
    saved = save(svc, approved.id, scope, 12)
    result = svc.command(saved.id, "done", finish(saved), "warehouse", scope)
    assert result.status == "packed" and result.approved_quantity == 5
    rows = list(db.scalars(select(Extra).where(Extra.order_id == saved.id)))
    assert sorted(r.qty for r in rows) == [2, 5]
    candidates = svc.base.repo.candidates(scope, include_decided=True)
    assert max(c.available_quantity for c in candidates) == 1
    budget = PackingStockRepository(db).budget(account, "16168", "FIXTURE-SKU")
    assert budget.available == 1 and budget.held == 12


def test_shortage_requires_reason_and_creates_one_atomic_local_notice(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    saved = save(svc, approved.id, scope, 13)
    with pytest.raises(ApiError) as error:
        svc.command(saved.id, "done", finish(saved), "warehouse", scope)
    assert error.value.details["reason"] == "OVERPACK_REASON_REQUIRED"
    assert (
        db.scalar(select(func.count()).select_from(Notice).where(Notice.order_id == saved.id)) == 0
    )
    cmd = finish(saved, "实物多于账面库存")
    result = svc.command(saved.id, "done", cmd, "warehouse", scope)
    replay = svc.command(saved.id, "done", cmd, "warehouse", scope)
    assert replay.version == result.version and replay.command_outcome == "blocked"
    notices = list(db.scalars(select(Notice).where(Notice.order_id == saved.id)))
    assert len(notices) == 1 and notices[0].state == "pending_configuration"
    assert notices[0].payload["gap_qty"] == 3 and notices[0].payload["actor_uid"] == "warehouse"
    assert svc.summary(WarehouseFilter(), scope).overpack_blocked == 1


def test_warehouse_correcting_boxes_clears_case_and_cancels_pending_notice(db, order):
    svc, row, scope, _, _ = blocked_case(db, order)
    corrected = save(svc, row.id, scope, 10)
    assert corrected.variance_case.state == "ready" and corrected.variance_case.gap_qty == 0
    result = svc.command(row.id, "done", finish(corrected), "warehouse", scope)
    assert result.status == "packed" and result.variance_case.state == "resolved"
    notice = db.scalar(select(Notice).where(Notice.order_id == row.id))
    assert notice.state == "cancelled"


def test_unconfigured_sync_is_audited_and_never_claims_success(db, order):
    svc, row, scope, _, _ = blocked_case(db, order)
    registered = svc.command(
        row.id,
        "ib",
        SupplementalInboundCommand(**base(row), inbound_order_sn="IBSUPPLEMENT"),
        "mid",
        scope,
    )
    result = svc.command(row.id, "sync", SupplementalSyncCommand(**base(registered)), "mid", scope)
    assert result.command_outcome == "blocked" and result.variance_case.state == "blocked"
    assert result.variance_case.last_sync_code == "LINGXING_SYNC_NOT_CONFIGURED"
    assert svc.events(row.id, scope, 1, 20).items[0].kind == "sync"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("wrong_sku", "IB_SKU_WAREHOUSE_MISMATCH"),
        ("short_qty", "IB_QUANTITY_INSUFFICIENT"),
        ("old_pub", "SYNC_EVIDENCE_STALE"),
        ("enough", "MATCHED"),
    ],
)
def test_supplement_sync_verifies_governed_new_publication_and_requires_manual_completion(
    db, order, kind, expected
):
    svc, row, scope, pub, _ = blocked_case(db, order)
    registered = svc.command(
        row.id,
        "ib",
        SupplementalInboundCommand(**base(row), inbound_order_sn="IBSUPPLEMENT"),
        "mid",
        scope,
    )
    new = pub if kind == "old_pub" else fresh_publication(db, pub)
    if kind != "old_pub":
        add_source(
            db,
            new,
            3,
            sku="OTHER-SKU" if kind == "wrong_sku" else "FIXTURE-SKU",
            parent=2 if kind == "short_qty" else 3,
        )
    svc = WarehouseService(db, lambda *args: new.id)
    checked = svc.command(row.id, "sync", SupplementalSyncCommand(**base(registered)), "mid", scope)
    assert checked.variance_case.last_sync_code == expected
    assert checked.status == "todo" and checked.box_set.completed_at is None
    if kind == "enough":
        assert checked.variance_case.state == "ready"
        completed = svc.command(row.id, "done", finish(checked), "warehouse", scope)
        assert completed.status == "packed"
    else:
        assert checked.variance_case.state == "blocked"


def test_event_failure_rolls_back_extra_holds_and_completion(db, order, monkeypatch):
    from app.modules.pmc_domestic.packing_models import PackingEvent

    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    saved = save(svc, approved.id, scope, 8)
    original = db.flush

    def fail(*args, **kwargs):
        if any(isinstance(o, PackingEvent) for o in db.new):
            raise RuntimeError("synthetic audit failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail)
    with pytest.raises(RuntimeError):
        svc.command(saved.id, "done", finish(saved), "warehouse", scope)
    monkeypatch.setattr(db, "flush", original)
    assert db.scalar(select(func.count()).select_from(Extra).where(Extra.order_id == saved.id)) == 0
    assert svc.detail(saved.id, scope).box_set.completed_at is None


def test_completed_rebox_shortage_records_proposal_without_changing_actual_boxes(db, order):
    from app.modules.pmc_domestic.warehouse_schemas import ReboxCommand

    approved, account, _ = order
    scope = frozenset({account})
    svc = WarehouseService(db)
    saved = save(svc, approved.id, scope, 8)
    completed = svc.command(saved.id, "done", finish(saved), "warehouse", scope)
    proposal = ReboxCommand(
        **boxes(completed, 13, reason="实物重新清点有差异").model_dump(),
        expected_box_version=completed.box_set.version,
        confirm_extra=True,
    )
    blocked = svc.command(saved.id, "rebox", proposal, "warehouse", scope)
    assert blocked.command_outcome == "blocked" and blocked.box_set.total_qty == 8
    assert blocked.box_set.completed_at == completed.box_set.completed_at
    assert blocked.variance_case.proposed_lines[0].units_per_box == 13
    corrected = ReboxCommand(
        **boxes(blocked, 9, reason="重新核对实际箱行").model_dump(),
        expected_box_version=blocked.box_set.version,
        confirm_extra=True,
    )
    result = svc.command(saved.id, "rebox", corrected, "warehouse", scope)
    assert (
        result.box_set.total_qty == 9
        and result.box_set.completed_at == completed.box_set.completed_at
    )
    assert result.variance_case.state == "resolved" and result.variance_case.proposed_lines is None
    assert sum(r.quantity for r in result.extra_allocations) == 4
    event = svc.events(saved.id, scope, 1, 20).items[0]
    assert sum(r["quantity"] for r in event.before["extra_allocations"]) == 3


def test_stock_unknown_and_other_sku_never_provide_extra_capacity(db, order):
    approved, account, pub = order
    scope = frozenset({account})
    svc = WarehouseService(db)
    add_source(db, pub, 999, sku="OTHER-SKU")
    assert svc.detail(approved.id, scope).extra_available == 5
    source = db.scalar(
        select(Board).where(Board.publication_id == pub.id, Board.sku == "FIXTURE-SKU")
    )
    source.payload_json = {"available_good_num": None}
    db.commit()
    saved = save(svc, approved.id, scope, 13)
    with pytest.raises(ApiError) as error:
        svc.command(saved.id, "done", finish(saved, "实物差异"), "warehouse", scope)
    assert error.value.details["reason"] == "STOCK_PROOF_UNKNOWN"
    assert svc.detail(saved.id, scope).variance_case is None


def test_warehouse_role_cannot_register_or_sync_supplemental_ib(db, order):
    from fastapi.testclient import TestClient

    from app.core.auth import Principal, get_optional_principal
    from app.db.session import get_db_session
    from app.main import create_app
    from app.modules.integration_sync.dependencies import require_source_account_scope

    approved, account, _ = order
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="warehouse",
        permissions=frozenset(
            {
                "page:pmc:domestic-warehouse-board:view",
                "action:pmc:domestic-warehouse-board:packing-done",
            }
        ),
    )
    with TestClient(app) as client:
        for path in ("supplemental-inbound", "supplemental-sync"):
            body = base(WarehouseService(db).detail(approved.id, frozenset({account})))
            body = {**body, "idempotency_key": str(body["idempotency_key"])}
            if path == "supplemental-inbound":
                body["inbound_order_sn"] = "IBSUPPLEMENT"
            assert (
                client.post(
                    f"/api/pmc/domestic/packing-warehouse/orders/{approved.id}/{path}", json=body
                ).status_code
                == 403
            )


def test_two_concurrent_pks_cannot_claim_the_same_extra_stock():
    # All committed race fixtures live in a temporary schema, never public business tables.
    import os
    import re
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import test_packing_approval as approval_fixture
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from app.modules.pmc_domestic.packing_schemas import PackingQuery
    from app.modules.pmc_domestic.packing_service import PackingService

    if os.environ.get("PACKING_LOCAL_INTEGRATION") != "1":
        pytest.skip("local opt-in required")
    url = make_url(os.environ["DATABASE_URL"])
    assert url.host == "127.0.0.1" and url.port == 55432 and url.database == "szzsbj_dev"
    schema = "test_packing_race_" + uuid4().hex[:16]
    assert re.fullmatch(r"test_packing_race_[0-9a-f]{16}", schema)
    engine = create_engine(url, hide_parameters=True)
    test_engine = None
    tables = [
        "gov_domestic_board_publications",
        "mart_domestic_inbound_batch_board",
        "ops_domestic_pk_sequences",
        "ops_domestic_packing_orders",
        "ops_domestic_packing_allocations",
        "evt_domestic_packing_events",
        "ops_domestic_packing_box_sets",
        "ops_domestic_packing_box_lines",
        "ops_domestic_packing_notes",
        "ops_domestic_packing_variance_cases",
        "ops_domestic_packing_notification_outbox",
        "ops_domestic_packing_extra_allocations",
        "dim_walmart_listings",
        "dim_lingxing_stores",
    ]
    try:
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in tables:
                c.execute(
                    text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)')
                )
        test_engine = create_engine(
            url, hide_parameters=True, connect_args={"options": f"-csearch_path={schema},public"}
        )
        with Session(test_engine) as s:
            account, _, _ = approval_fixture.seeded.__wrapped__(s)
            service = PackingService(s)
            scope = frozenset({account})
            candidate = service.pending(PackingQuery(), scope).items[0]
            command = approval_fixture.command(candidate)
            command.qty = 5
            first = service.decide(candidate.id, command, "approve", "fixture", scope)
            candidate = service.pending(PackingQuery(), scope).items[0]
            command = approval_fixture.command(candidate)
            command.qty = 3
            second = service.decide(candidate.id, command, "approve", "fixture", scope)
            svc = WarehouseService(s)
            a = save(svc, first.id, scope, 7)
            b = save(svc, second.id, scope, 5)
            ids = [a.id, b.id]
        barrier = threading.Barrier(2)

        def compete(ident):
            with Session(test_engine) as s:
                svc = WarehouseService(s)
                row = svc.detail(ident, scope)
                command = finish(row, "并发核对实物多装")
                barrier.wait(timeout=10)
                return svc.command(ident, "done", command, "warehouse", scope).command_outcome

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(compete, ids))
        assert sorted(outcomes) == ["blocked", "completed"]
        with Session(test_engine) as s:
            assert s.scalar(select(func.sum(Extra.qty))) == 2
            assert PackingStockRepository(s).budget(account, "16168", "FIXTURE-SKU").available == 0
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
