"""Month recalculation: every store of a bill month, then 纯利 across stores (PRP §8.1, §8.7).

Sources are read through ``SettlementProfitLoader`` so the calculation runs on synthetic
fixtures until ``fact_walmart_settlement_lines`` (#290 implementation) and
``ods_lingxing_wfs_cost_valuation_flow`` (inventory-claim PR 1) are on main.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..settlement_profit_models import NetProfitAllocationConfig
from .engine import StoreMonthResult, calculate_store_month, unmapped_store_rows
from .inputs import Adjustment, FlowMovement, StoreMonthInput
from .keys import UNMAPPED_STORE_ID
from .money import ZERO, allocate, q4
from .persistence import PersistOutcome, persist_store_month, persist_unmapped
from .rules import NetProfitResult, OwnerItem, allocate_net_profit

DEFAULT_FIXED_CNY = Decimal("15000")


class SettlementProfitLoader(Protocol):
    def store_ids(self, bill_month: date) -> list[str]: ...

    def fx_rate(self, bill_month: date) -> Decimal | None: ...

    def unmapped_movements(self, bill_month: date) -> list[FlowMovement]: ...

    def adjustments(self, store_id: str, bill_month: date) -> list[Adjustment]: ...

    def load_store_month(
        self, store_id: str, bill_month: date, assigned_movements: list[FlowMovement]
    ) -> StoreMonthInput: ...

    def company_cost_cny(self, bill_month: date) -> Decimal | None:
        """管理 + 财务 + 税费 (资金流水分类); None until the funds-flow import is live."""
        ...


@dataclass(frozen=True)
class MonthOutcome:
    bill_month: date
    stores: list[PersistOutcome]
    unmapped_pending: int
    net_profit: NetProfitResult
    results: dict[str, StoreMonthResult]


def net_profit_config(session: Session, bill_month: date) -> tuple[Decimal, list[str]]:
    row = session.execute(
        select(NetProfitAllocationConfig)
        .where(NetProfitAllocationConfig.effective_month <= bill_month)
        .order_by(NetProfitAllocationConfig.effective_month.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_FIXED_CNY, []
    return Decimal(row.fixed_cny), list(row.excluded_owner_ids)


def apply_net_profit(results: dict[str, StoreMonthResult], net: NetProfitResult) -> None:
    for result in results.values():
        for it in result.items.values():
            share = (
                None
                if net.share_by_item is None
                else net.share_by_item.get((result.store_id, it.item_id), ZERO)
            )
            it.net_profit_share_cny = share
            it.net_profit_cny = (
                None
                if share is None or it.gross_profit_cny is None
                else q4(it.gross_profit_cny - share)
            )
            rows = [r for r in result.order_lines if r.item_id == it.item_id]
            if share is None or not rows:
                for r in rows:
                    r.net_profit_share_cny = None
                continue
            weights = {r.line_key: max(r.amounts.get("sales_amount_usd"), ZERO) for r in rows}
            if sum(weights.values(), ZERO) == 0:
                weights = {r.line_key: Decimal(1) for r in rows}
            parts = allocate(share, weights)
            for r in rows:
                r.net_profit_share_cny = parts[r.line_key]
        if net.blockers:
            result.blockers.extend(b for b in net.blockers if b not in result.blockers)


def recalculate_month(
    session: Session, loader: SettlementProfitLoader, bill_month: date, *, now: datetime
) -> MonthOutcome:
    rate = loader.fx_rate(bill_month)
    unmapped = loader.unmapped_movements(bill_month)
    unmapped_rows = unmapped_store_rows(
        bill_month, unmapped, rate, loader.adjustments(UNMAPPED_STORE_ID, bill_month)
    )
    pending_unmapped = sum(1 for r in unmapped_rows if r.status == "pending")
    by_hash = {m.row_hash: m for m in unmapped}
    assigned: dict[str, list[FlowMovement]] = {}
    for row in unmapped_rows:
        if row.status == "assigned" and row.assigned_store_id:
            m = by_hash[row.source_ref]
            assigned.setdefault(row.assigned_store_id, []).append(m)

    results: dict[str, StoreMonthResult] = {}
    for store_id in sorted(set(loader.store_ids(bill_month)) | set(assigned)):
        inp = loader.load_store_month(store_id, bill_month, assigned.get(store_id, []))
        results[store_id] = calculate_store_month(
            inp, month_has_unmapped_pending=pending_unmapped > 0
        )

    company_cost = loader.company_cost_cny(bill_month)
    fixed, excluded = net_profit_config(session, bill_month)
    owner_items = [
        OwnerItem(
            key=(r.store_id, it.item_id),
            owner_ref=it.owner_ref,
            sales_usd=it.amounts.get("sales_amount_usd"),
            sales_quantity=it.sales_quantity,
        )
        for r in results.values()
        for it in r.items.values()
    ]
    net = allocate_net_profit(
        owner_items,
        company_cost if rate is not None else None,  # FX_MISSING: 纯利不算 (§8.7)
        fixed,
        excluded,
    )
    apply_net_profit(results, net)

    outcomes = [persist_store_month(session, r, now=now) for r in results.values()]
    version = max((o.calc_version for o in outcomes), default=1)
    persist_unmapped(session, bill_month, unmapped_rows, version)
    return MonthOutcome(bill_month, outcomes, pending_unmapped, net, results)
