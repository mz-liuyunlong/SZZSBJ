"""Real PostgreSQL transactions with synthetic sources; fixture writes always roll back.

Enable PACKING_LOCAL_INTEGRATION=1 against the guarded local dev DB only. No live
session is created and no production connection or provider call is possible.
"""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import WalmartListingDimension as Listing
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
)
from app.modules.pmc_domestic.packing_rules import available_good_stock
from app.modules.pmc_domestic.packing_schemas import (
    ApproveCommand,
    PackingQuery,
    RejectCommand,
)
from app.modules.pmc_domestic.packing_service import PackingService

PREFIX = "/api/pmc/domestic/packing-approval"
READ = "page:pmc:domestic-warehouse-board:view"
APPROVE = "action:pmc:domestic-warehouse-board:packing-approve"
REJECT = "action:pmc:domestic-warehouse-board:packing-reject"


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([], (None, None, None)),
        ([{"good_num": 10, "storage_used_lock_num": "2"}], (10, 2, 8)),
        ([{"good_num": 10}], (None, None, None)),
        ([{"good_num": True, "storage_used_lock_num": 0}], (None, None, None)),
        ([{"good_num": 1, "storage_used_lock_num": 2}], (None, None, None)),
    ],
)
def test_stock_proof(rows, expected):
    assert available_good_stock(rows) == expected


@pytest.mark.parametrize("qty", [True, 1.5, 0, -1, "2", 1000001])
def test_quantity_strict(qty):
    with pytest.raises(ValidationError):
        ApproveCommand(
            source_account_ref="x",
            candidate_version="a" * 64,
            idempotency_key=uuid4(),
            qty=qty,
        )


@pytest.fixture
def db():
    if os.environ.get("PACKING_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required")
    u = make_url(os.environ["DATABASE_URL"])
    assert u.host == "127.0.0.1" and u.port == 55432 and u.database == "szzsbj_dev"
    engine = create_engine(u, hide_parameters=True)
    with engine.connect() as c:
        outer = c.begin()
        s = Session(bind=c, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            s.close()
            outer.rollback()
    engine.dispose()


@pytest.fixture
def seeded(db):
    account = "packing-fixture-" + str(uuid4())
    now = datetime.now(UTC)
    pub = Pub(
        source_account_ref=account,
        source_warehouse_id="16168",
        status="published",
        is_current=True,
        batch_run_id=uuid4(),
        statement_run_ids=[str(uuid4())],
        coverage_start=date(2026, 10, 1),
        coverage_end=date(2026, 10, 21),
        source_observed_at=now,
        builder_version="domestic.inbound.v2",
        quality_report={"fixture": True},
    )
    db.add(pub)
    db.flush()
    board = Board(
        id=uuid4(),
        publication_id=pub.id,
        source_account_ref=account,
        source_warehouse_id="16168",
        inbound_order_sn="IB261020999",
        sku="FIXTURE-SKU",
        store_id="fixture-store",
        attribution_key="fixture-store",
        arrival_business_date=date(2026, 10, 19),
        balance_num=10,
        payload_json={"available_good_num": 10, "purchase_order_sns": []},
    )
    db.add(board)
    for i in range(2):
        db.add(
            Listing(
                source_system="lingxing",
                source_account_ref=account,
                platform_code="walmart",
                store_id="fixture-store",
                item_id=str(100000 + i),
                msku="fixture-msku-" + str(i),
                local_sku=board.sku,
                gtin="00000000000000",
                standard_status="PUBLISHED",
                raw_status="PUBLISHED",
                fulfillment_type="0",
                business_hash=str(i) * 64,
                source_observed_at=now,
                synced_at=now,
            )
        )
    db.flush()
    return account, board, pub


def command(row, **kw):
    return ApproveCommand(
        source_account_ref=row.source_account_ref,
        candidate_version=row.candidate_version,
        idempotency_key=uuid4(),
        qty=1,
        **kw,
    )


def test_shared_stock_idempotency_and_rollback(db, seeded):
    account, _board, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    rows = svc.pending(PackingQuery(), scope).items
    assert len(rows) == 2 and all(r.default_quantity is None for r in rows)
    cmd = command(rows[0])
    cmd.qty = 7
    order = svc.decide(rows[0].id, cmd, "approve", "synthetic-test", scope)
    assert (
        svc.decide(rows[0].id, cmd, "approve", "synthetic-test", scope).id == order.id
    )
    assert (
        db.scalar(
            select(PackingAllocation.qty).where(PackingAllocation.order_id == order.id)
        )
        == 7
    )
    remaining = svc.pending(PackingQuery(), scope).items
    assert len(remaining) == 1 and remaining[0].available_quantity == 3
    with pytest.raises(ApiError) as err:
        svc.decide(rows[1].id, command(rows[1]), "approve", "synthetic-test", scope)
    assert err.value.details["reason"] == "SOURCE_CHANGED"
    new = svc.pending(PackingQuery(), scope).items[0]
    excess = command(new)
    excess.qty = 4
    with pytest.raises(ApiError) as err:
        svc.decide(new.id, excess, "approve", "synthetic-test", scope)
    assert err.value.details["reason"] == "INSUFFICIENT_STOCK"
    assert len(svc.repo.orders(scope)) == 1


def test_idempotency_payload_and_actor_bound(db, seeded):
    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    cmd = command(row)
    svc.decide(row.id, cmd, "approve", "actor-a", scope)
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, cmd, "approve", "actor-b", scope)
    assert err.value.details["reason"] == "IDEMPOTENCY_KEY_REUSED"


def test_reject_terminal_and_audit_immutable(db, seeded):
    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    cmd = RejectCommand(
        source_account_ref=account,
        candidate_version=row.candidate_version,
        idempotency_key=uuid4(),
        note="本地合成事务测试",
    )
    order = svc.decide(row.id, cmd, "reject", "synthetic-test", scope)
    assert order.pk is None and order.qty is None
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row), "approve", "synthetic-test", scope)
    assert err.value.details["reason"] == "ALREADY_DECIDED"
    event = db.scalar(select(PackingEvent).where(PackingEvent.order_id == order.id))
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(
            text(
                "UPDATE evt_domestic_packing_events SET actor_uid=actor_uid WHERE id=:id"
            ),
            {"id": event.id},
        )


def test_source_switch_and_scope(db, seeded):
    account, board, _pub = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    assert svc.pending(PackingQuery(), frozenset({"other"})).total == 0
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row), "approve", "actor", frozenset({"other"}))
    assert err.value.status_code == 403
    board.payload_json = {**board.payload_json, "available_good_num": 5}
    db.flush()
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row), "approve", "actor", scope)
    assert err.value.details["reason"] == "SOURCE_CHANGED"


def test_page_only_cannot_approve_and_reject(db, seeded):
    account, _, _ = seeded
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset(
        {account}
    )
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-test", permissions=frozenset({READ})
    )
    client = TestClient(app)
    rows = client.get(PREFIX + "/pending").json()["data"]["items"]
    assert len(rows) == 2
    row = rows[0]
    body = {
        "source_account_ref": account,
        "candidate_version": row["candidate_version"],
        "idempotency_key": str(uuid4()),
        "qty": 1,
    }
    assert (
        client.post(
            PREFIX + "/pending/" + row["id"] + "/approve", json=body
        ).status_code
        == 403
    )
    body.pop("qty")
    body["note"] = "test"
    assert (
        client.post(PREFIX + "/pending/" + row["id"] + "/reject", json=body).status_code
        == 403
    )
    app.dependency_overrides[get_optional_principal] = lambda: None
    assert client.get(PREFIX + "/pending").status_code == 401


def test_daily_cap_is_atomic(db, seeded):
    from zoneinfo import ZoneInfo

    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    db.execute(
        text(
                "INSERT INTO ops_domestic_pk_sequences (business_date,last_value) "
                "VALUES (:day,999) ON CONFLICT(business_date) DO UPDATE SET last_value=999"
        ),
        {"day": day},
    )
    db.commit()
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row), "approve", "actor", scope)
    assert err.value.details["reason"] == "PK_DAILY_LIMIT"
    assert len(svc.repo.orders(scope)) == 0


def test_event_failure_rolls_back_order_allocation_and_counter(db, seeded, monkeypatch):
    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    db.commit()
    before = db.scalar(
        text("SELECT COALESCE(sum(last_value),0) FROM ops_domestic_pk_sequences")
    )
    db.commit()
    original = db.add

    def fail_event(value):
        if isinstance(value, PackingEvent):
            raise RuntimeError("synthetic event write failure")  # noqa: TRY004
        original(value)

    monkeypatch.setattr(db, "add", fail_event)
    with pytest.raises(RuntimeError, match="synthetic event"):
        svc.decide(row.id, command(row), "approve", "actor", scope)
    assert len(svc.repo.orders(scope)) == 0
    assert (
        db.scalar(
            select(PackingAllocation.id).where(
                PackingAllocation.source_account_ref == account
            )
        )
        is None
    )
    assert (
        db.scalar(
            text("SELECT COALESCE(sum(last_value),0) FROM ops_domestic_pk_sequences")
        )
        == before
    )


def test_publication_switch_invalidates_candidate(db, seeded):
    account, board, pub = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    pub.is_current = False
    db.flush()
    replacement = Pub(
        source_account_ref=account,
        source_warehouse_id="16168",
        status="published",
        is_current=True,
        batch_run_id=uuid4(),
        statement_run_ids=[str(uuid4())],
        coverage_start=pub.coverage_start,
        coverage_end=pub.coverage_end,
        source_observed_at=pub.source_observed_at,
        builder_version=pub.builder_version,
        quality_report={},
    )
    db.add(replacement)
    db.flush()
    db.add(
        Board(
            id=board.id,
            publication_id=replacement.id,
            source_account_ref=account,
            source_warehouse_id="16168",
            inbound_order_sn=board.inbound_order_sn,
            sku=board.sku,
            store_id=board.store_id,
            attribution_key=board.attribution_key,
            arrival_business_date=board.arrival_business_date,
            balance_num=board.balance_num,
            payload_json=board.payload_json,
        )
    )
    db.flush()
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row), "approve", "actor", scope)
    assert err.value.details["reason"] == "SOURCE_CHANGED"
