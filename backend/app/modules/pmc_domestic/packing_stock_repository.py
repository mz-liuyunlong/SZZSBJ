"""Shared bounded stock reads. Mutating callers own the publication advisory lock.

The global headroom also subtracts orphaned/oversubscribed source holds; a source
disappearing from the newest snapshot must never silently free its allocation.
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete, select, tuple_

from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation as Extra


@dataclass
class StockBudget:
    available: int | None
    publication_id: UUID | None
    sources: list = field(default_factory=list)
    held: int = 0


class PackingStockRepository:
    def __init__(self, session):
        self.session = session

    def budget(self, account, warehouse, sku, *, excluding_extra_order=None):
        key = (account, warehouse, sku)
        return self.budgets({key}, excluding_extra_order=excluding_extra_order)[key]

    def budgets(self, keys, *, excluding_extra_order=None):
        if not keys:
            return {}
        s = self.session
        groups = {key: [] for key in keys}
        for board in s.scalars(
            select(Board)
            .join(Pub, Pub.id == Board.publication_id)
            .where(
                Pub.is_current.is_(True),
                tuple_(Board.source_account_ref, Board.source_warehouse_id, Board.sku).in_(keys),
            )
            .order_by(Board.arrival_business_date.asc().nulls_last(), Board.id)
        ):
            groups[(board.source_account_ref, board.source_warehouse_id, board.sku)].append(board)
        holds = {key: {} for key in keys}
        for allocation, sku in s.execute(
            select(PackingAllocation, PackingOrder.sku)
            .join(PackingOrder, PackingOrder.id == PackingAllocation.order_id)
            .where(
                PackingOrder.status == "approved",
                PackingAllocation.released_at.is_(None),
                tuple_(
                    PackingAllocation.source_account_ref,
                    PackingAllocation.warehouse_id,
                    PackingOrder.sku,
                ).in_(keys),
            )
        ):
            group = holds[(allocation.source_account_ref, allocation.warehouse_id, sku)]
            group[allocation.source_board_id] = (
                group.get(allocation.source_board_id, 0) + allocation.qty
            )
        stmt = (
            select(Extra)
            .join(PackingOrder, PackingOrder.id == Extra.order_id)
            .where(
                PackingOrder.status == "approved",
                tuple_(Extra.source_account_ref, Extra.warehouse_id, Extra.sku).in_(keys),
            )
        )
        if excluding_extra_order is not None:
            stmt = stmt.where(Extra.order_id != excluding_extra_order)
        for allocation in s.scalars(stmt):
            group = holds[(allocation.source_account_ref, allocation.warehouse_id, allocation.sku)]
            group[allocation.source_board_id] = (
                group.get(allocation.source_board_id, 0) + allocation.qty
            )
        result = {}
        for key, boards in groups.items():
            pubs = {b.publication_id for b in boards}
            quantities = [b.payload_json.get("available_good_num") for b in boards]
            if len(pubs) != 1 or any(
                isinstance(q, bool) or not isinstance(q, int) or q < 0 for q in quantities
            ):
                result[key] = StockBudget(None, None)
                continue
            group = holds[key]
            held = sum(group.values())
            sources = [
                (b, max(0, q - group.get(b.id, 0))) for b, q in zip(boards, quantities, strict=True)
            ]
            result[key] = StockBudget(max(0, sum(quantities) - held), pubs.pop(), sources, held)
        return result

    def replace_extra(self, order, quantity, budget):
        if quantity == 0:
            self.session.execute(delete(Extra).where(Extra.order_id == order.id))
            return
        if budget.available is None or quantity > budget.available:
            raise ValueError("locked stock budget insufficient")
        self.session.execute(delete(Extra).where(Extra.order_id == order.id))
        left = quantity
        for board, available in budget.sources:
            take = min(left, available)
            if take:
                self.session.add(
                    Extra(
                        order_id=order.id,
                        source_account_ref=order.source_account_ref,
                        warehouse_id=order.warehouse_id,
                        sku=order.sku,
                        source_publication_id=board.publication_id,
                        source_board_id=board.id,
                        qty=take,
                    )
                )
                left -= take
            if left == 0:
                break
        if left:
            raise ValueError("extra source distribution inconsistent")
