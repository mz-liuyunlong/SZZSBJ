"""Manual submissions use the same local inventory pool and rollback-only fixtures."""

from uuid import uuid4

import pytest
import test_packing_approval as m1
from sqlalchemy import func, select, text

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_manual_service import ManualPackingService
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingManualRequest
from app.modules.pmc_domestic.packing_schemas import ManualCommand, PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService

db = m1.db
seeded = m1.seeded


def request(svc, account, qty=3, **extra):
    scope = frozenset({account})
    source = svc.sources(scope)[0]
    target = svc.options(source.board_id, account, scope).listings[-1]
    return ManualCommand(
        source_account_ref=account,
        board_id=source.board_id,
        source_version=source.candidate_version,
        target_store_id=target.store_id,
        target_item_id=target.item_id,
        listing_version=target.listing_version,
        qty=qty,
        reason="按入库单分批手工申请",
        idempotency_key=uuid4(),
        **extra,
    )


def test_submit_is_pending_without_pk_or_allocation_and_is_idempotent(db, seeded):
    account, _, _ = seeded
    base = PackingService(db)
    svc = ManualPackingService(base)
    before = db.scalar(text("SELECT COALESCE(sum(last_value),0) FROM ops_domestic_pk_sequences"))
    cmd = request(svc, account)
    result = svc.submit(cmd, "fixture", frozenset({account}))
    assert result.status == "pending"
    assert svc.submit(cmd, "fixture", frozenset({account})).id == result.id
    assert (
        db.scalar(
            select(func.count())
            .select_from(PackingManualRequest)
            .where(PackingManualRequest.source_account_ref == account)
        )
        == 1
    )
    assert len(base.repo.orders(frozenset({account}))) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(PackingAllocation)
            .where(PackingAllocation.source_account_ref == account)
        )
        == 0
    )
    assert (
        db.scalar(text("SELECT COALESCE(sum(last_value),0) FROM ops_domestic_pk_sequences"))
        == before
    )
    row = next(
        r for r in base.pending(PackingQuery(), frozenset({account})).items if r.id == result.id
    )
    assert row.origin == "manual" and row.default_quantity == 3


def test_manual_split_approvals_share_stock_and_keep_same_source_sku(db, seeded):
    account, board, _ = seeded
    scope = frozenset({account})
    base = PackingService(db)
    svc = ManualPackingService(base)
    for qty in (3, 2):
        cmd = request(svc, account, qty)
        submitted = svc.submit(cmd, "fixture", scope)
        row = next(r for r in base.pending(PackingQuery(), scope).items if r.id == submitted.id)
        decision = m1.command(row)
        decision.qty = qty
        order = base.decide(row.id, decision, "approve", "fixture", scope)
        assert order.pk and order.snapshot.sku == board.sku
        assert order.snapshot.board_id == board.id and order.source_snapshot.board_id == board.id
    assert (
        db.scalar(
            select(func.sum(PackingAllocation.qty)).where(
                PackingAllocation.source_account_ref == account
            )
        )
        == 5
    )
    assert all(r.available_quantity == 5 for r in svc.sources(scope))
    assert not any(r.origin == "manual" for r in base.pending(PackingQuery(), scope).items)


def test_manual_insufficient_stock_and_changed_source_cannot_submit(db, seeded):
    account, board, _ = seeded
    scope = frozenset({account})
    base = PackingService(db)
    svc = ManualPackingService(base)
    cmd = request(svc, account, 11)
    db.commit()
    with pytest.raises(ApiError) as error:
        svc.submit(cmd, "fixture", scope)
    assert error.value.details["reason"] == "INSUFFICIENT_STOCK"
    cmd = request(svc, account)
    board.payload_json = {**board.payload_json, "available_good_num": 1}
    db.flush()
    with pytest.raises(ApiError) as error:
        svc.submit(cmd, "fixture", scope)
    assert error.value.details["reason"] == "SOURCE_CHANGED"


def test_manual_permission_and_removed_system_routes(db, seeded):
    from fastapi.testclient import TestClient

    from app.core.auth import Principal, get_optional_principal
    from app.db.session import get_db_session
    from app.main import create_app
    from app.modules.integration_sync.dependencies import require_source_account_scope

    account, _, _ = seeded
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="fixture", permissions=frozenset({"page:pmc:domestic-warehouse-board:view"})
    )
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    client = TestClient(app)
    prefix = "/api/pmc/domestic/packing-approval"
    assert client.get(prefix + "/manual/sources").status_code == 200
    cmd = request(ManualPackingService(PackingService(db)), account)
    assert client.post(prefix + "/manual", json=cmd.model_dump(mode="json")).status_code == 403
    assert client.get(prefix + "/packs").status_code == 404
    assert client.post(prefix + "/orders/" + str(uuid4()) + "/void", json={}).status_code == 404
