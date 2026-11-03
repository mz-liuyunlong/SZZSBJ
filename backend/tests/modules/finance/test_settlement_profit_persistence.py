"""calc_version / content hash / month-close freeze on PostgreSQL (opt-in, synthetic)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.modules.finance.settlement_profit.inputs import (
    Adjustment,
    FlowMovement,
    SettlementKind,
    StoreMonthInput,
)
from app.modules.finance.settlement_profit.keys import UNMAPPED_STORE_ID
from app.modules.finance.settlement_profit.service import recalculate_month
from app.modules.finance.settlement_profit_models import (
    InventoryMovementLine,
    SettlementMonthClose,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementPostCloseDiff,
    SettlementReconcileStoreMonth,
    SettlementUnassignedAmount,
)
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic

from .settlement_fixtures import MONTH, RATE, STORE, base_input, line, movement

NOW = datetime(2030, 2, 10, tzinfo=UTC)


@dataclass
class FakeLoader:
    inputs: dict[str, StoreMonthInput]
    unmapped: list[FlowMovement] = field(default_factory=list)
    unmapped_adjustments: list[Adjustment] = field(default_factory=list)
    rate: D | None = RATE

    def store_ids(self, bill_month: date) -> list[str]:
        return sorted(self.inputs)

    def fx_rate(self, bill_month: date) -> D | None:
        return self.rate

    def unmapped_movements(self, bill_month: date) -> list[FlowMovement]:
        return list(self.unmapped)

    def adjustments(self, store_id: str, bill_month: date) -> list[Adjustment]:
        return list(self.unmapped_adjustments) if store_id == UNMAPPED_STORE_ID else []

    def load_store_month(
        self, store_id: str, bill_month: date, assigned_movements: list[FlowMovement]
    ) -> StoreMonthInput:
        inp = self.inputs.get(store_id) or base_input(store_id=store_id, settlement_lines=[])
        inp.movements = [m for m in inp.movements if m.store_id == store_id]
        inp.movements += assigned_movements
        return inp

    def company_cost_cny(self, bill_month: date) -> D | None:
        return None


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    database = create_database(url, "finsettlecalc")
    try:
        up = _alembic(url, database, "head")
        assert up.returncode == 0, up.stderr
        eng = sa.create_engine(url.set(database=database), hide_parameters=True)
        yield eng
        eng.dispose()
    finally:
        drop_database(url, database)


@pytest.fixture
def session(engine: sa.Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s
        s.rollback()


def count(session: Session, model: type, **where: object) -> int:
    stmt = sa.select(sa.func.count()).select_from(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return int(session.execute(stmt).scalar_one())


def test_identical_input_writes_no_new_version(session: Session) -> None:
    loader = FakeLoader({STORE: base_input(movements=[movement("LIQ")])})
    first = recalculate_month(session, loader, MONTH, now=NOW).stores[0]
    assert (first.action, first.calc_version) == ("written", 1)
    assert count(session, SettlementOrderLine, calc_version=1) == 3
    assert count(session, InventoryMovementLine, calc_version=1) == 1
    loader.inputs[STORE] = base_input(movements=[movement("LIQ")])
    again = recalculate_month(session, loader, MONTH, now=NOW).stores[0]
    assert (again.action, again.calc_version) == ("unchanged", 1)
    # re-synced flow row: new flow id, same row_hash → still unchanged (§8.1)
    other_id = "00000000-0000-0000-0000-0000000000aa"
    loader.inputs[STORE] = base_input(movements=[movement("LIQ", flow_id=other_id)])
    assert recalculate_month(session, loader, MONTH, now=NOW).stores[0].action == "unchanged"
    # real change → version 2, version 1 kept
    changed = base_input(movements=[movement("LIQ")])
    changed.settlement_lines.append(line(SettlementKind.SALE, "1.00", "SYN-O1", n=2))
    loader.inputs[STORE] = changed
    second = recalculate_month(session, loader, MONTH, now=NOW).stores[0]
    assert (second.action, second.calc_version) == ("written", 2)
    assert count(session, SettlementOrderLine, calc_version=1) == 3
    recon = session.execute(sa.select(SettlementReconcileStoreMonth)).scalar_one()
    assert recon.calc_version == 2 and recon.status == "ok"


def test_closed_month_only_writes_post_close_diffs(session: Session) -> None:
    loader = FakeLoader({STORE: base_input()})
    recalculate_month(session, loader, MONTH, now=NOW)
    session.add(
        SettlementMonthClose(
            store_scope="ALL",
            bill_month=MONTH,
            status="closed",
            frozen_calc_version=1,
            actor_id="fixture",
            actor_role="finance_lead",
            request_id="req-1",
            idempotency_key=str(uuid4()),
        )
    )
    session.flush()
    changed = base_input()
    changed.settlement_lines.append(line(SettlementKind.SALE, "1.00", "SYN-O1", n=2))
    loader.inputs[STORE] = changed
    out = recalculate_month(session, loader, MONTH, now=NOW).stores[0]
    assert out.action == "frozen" and out.post_close_diffs == 1
    assert count(session, SettlementOrderLine, calc_version=2) == 0  # frozen numbers kept
    diff = session.execute(sa.select(SettlementPostCloseDiff)).scalar_one()
    assert diff.diff_amount_usd == D("1.0000") and diff.frozen_calc_version == 1
    # the same change again does not duplicate the open diff
    loader.inputs[STORE] = changed
    again = recalculate_month(session, loader, MONTH, now=NOW).stores[0]
    assert again.post_close_diffs == 0


def test_unmapped_store_movement_todo_and_assignment(session: Session) -> None:
    loss = movement("LIQ", store_id=None, row_hash="u-1")
    loader = FakeLoader({STORE: base_input()}, unmapped=[loss])
    out = recalculate_month(session, loader, MONTH, now=NOW)
    assert out.unmapped_pending == 1
    todo = session.execute(
        sa.select(SettlementUnassignedAmount).where(
            SettlementUnassignedAmount.store_id == UNMAPPED_STORE_ID
        )
    ).scalar_one()
    assert (todo.reason, todo.status, todo.amount_cny) == ("unmapped_store", "pending", D("70"))
    review = session.execute(
        sa.select(SettlementOrderReview).where(SettlementOrderReview.store_id == UNMAPPED_STORE_ID)
    ).scalar_one()
    assert review.row_kind == "unassigned" and review.reasons == ["unmapped_store"]
    recon = session.execute(sa.select(SettlementReconcileStoreMonth)).scalar_one()
    assert recon.status == "unassigned_pending"

    loader.unmapped_adjustments = [
        Adjustment(str(uuid4()), todo.line_key, "assign_store", {"store_id": STORE}, NOW)
    ]
    loader.inputs[STORE] = base_input()
    out = recalculate_month(session, loader, MONTH, now=NOW)
    assert out.unmapped_pending == 0
    session.refresh(todo)
    assert (todo.status, todo.assigned_store_id) == ("assigned", STORE)
    moved = session.execute(
        sa.select(InventoryMovementLine).where(InventoryMovementLine.calc_version == 2)
    ).scalar_one()
    assert (moved.store_id, moved.store_mapping_status) == (STORE, "manual_assigned")
    session.refresh(recon)
    assert recon.status == "ok"

    # flow row changed upstream (new row_hash): old to-do void, new pending to-do
    loader.unmapped = [movement("LIQ", store_id=None, row_hash="u-2")]
    loader.inputs[STORE] = base_input()
    recalculate_month(session, loader, MONTH, now=NOW)
    session.refresh(todo)
    assert todo.status == "void"
    assert count(session, SettlementUnassignedAmount, status="pending") == 1
