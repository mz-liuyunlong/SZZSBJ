"""Read-only queries for the PMC purchase board API (Gate 3, G3-E).

Reads only DWS (``dws_purchase_*``), the DWD plan table (for the S2 plan drill-down),
the rule table and ``dim_lingxing_stores``. Never ODS / RAW, never writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchasePlan,
    DwsPurchaseBoard,
    DwsPurchaseSkuCycle,
    RulePurchaseThresholds,
)
from app.modules.pmc_purchase.schemas import BoardFilterQuery, BoardListQuery, PendingPlanQuery

RULE_KEY = "pmc_purchase_thresholds"
PLAN_STATUS_PENDING_PURCHASE = 2

_SEARCH_COLUMNS = {
    "sku": DwsPurchaseBoard.sku,
    "item_id": DwsPurchaseBoard.item_id,
    "gtin": DwsPurchaseBoard.gtin,
    "msku": DwsPurchaseBoard.msku,
    "order_sn": DwsPurchaseBoard.order_sn,
}

_SORTS: dict[str, tuple[Any, ...]] = {
    "order_date_desc": (
        DwsPurchaseBoard.order_date.desc().nulls_last(),
        DwsPurchaseBoard.order_sn.desc(),
    ),
    "order_date_asc": (DwsPurchaseBoard.order_date.asc().nulls_last(), DwsPurchaseBoard.order_sn),
    "overdue_days_desc": (
        DwsPurchaseBoard.overdue_days.desc(),
        DwsPurchaseBoard.order_date.desc().nulls_last(),
    ),
    "arrival_date_desc": (
        DwsPurchaseBoard.arrival_date.desc().nulls_last(),
        DwsPurchaseBoard.order_sn.desc(),
    ),
    "amount_desc": (
        DwsPurchaseBoard.amount_allocated.desc().nulls_last(),
        DwsPurchaseBoard.order_sn.desc(),
    ),
}


class PmcPurchaseReadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- rules --

    def active_rule(self, today: date) -> RulePurchaseThresholds | None:
        return self.session.scalars(
            select(RulePurchaseThresholds)
            .where(
                RulePurchaseThresholds.rule_key == RULE_KEY,
                RulePurchaseThresholds.is_active.is_(True),
                RulePurchaseThresholds.effective_from <= today,
                or_(
                    RulePurchaseThresholds.effective_to.is_(None),
                    RulePurchaseThresholds.effective_to > today,
                ),
            )
            .order_by(
                RulePurchaseThresholds.effective_from.desc(),
                RulePurchaseThresholds.version.desc(),
            )
        ).first()

    # -- board --

    def _board_filters(
        self, query: BoardFilterQuery, accounts: frozenset[str], today: date
    ) -> list[Any]:
        b = DwsPurchaseBoard
        clauses: list[Any] = [b.source_account_ref.in_(sorted(accounts))]
        if query.owner_uid:
            clauses.append(b.owner_uid.in_(query.owner_uid))
        if query.store_id:
            clauses.append(b.store_id.in_(query.store_id))
        if query.status:
            options: list[Any] = []
            for status in query.status:
                if status == "overdue":
                    options.append(b.overdue_days > 0)
                elif status == "unattributed":
                    options.append(b.store_attributed.is_(False))
                else:
                    options.append(b.stage_code == status.upper())
            clauses.append(or_(*options))
        values = query.normalized_search_values()
        if values and query.search_type:
            clauses.append(_SEARCH_COLUMNS[query.search_type].in_(values))
        if query.item_id_source:
            clauses.append(b.item_id_source.in_(query.item_id_source))
        if query.order_date_from:
            clauses.append(b.order_date >= query.order_date_from)
        if query.order_date_to:
            clauses.append(b.order_date <= query.order_date_to)
        if query.qty_min is not None:
            clauses.append(b.quantity_allocated >= query.qty_min)
        if query.qty_max is not None:
            clauses.append(b.quantity_allocated <= query.qty_max)
        if query.price_min is not None:
            clauses.append(b.unit_price >= query.price_min)
        if query.price_max is not None:
            clauses.append(b.unit_price <= query.price_max)
        if query.wfs_not_ready is not None:
            clauses.append(b.wfs_not_ready.is_(query.wfs_not_ready))
        if query.today_followup:
            clauses.append(or_(b.overdue_days > 0, b.due_date == today))
        return clauses

    def _board_select(
        self, query: BoardFilterQuery, accounts: frozenset[str], today: date
    ) -> Select[tuple[DwsPurchaseBoard]]:
        return select(DwsPurchaseBoard).where(and_(*self._board_filters(query, accounts, today)))

    def list_board(
        self, query: BoardListQuery, accounts: frozenset[str], today: date
    ) -> tuple[list[DwsPurchaseBoard], int]:
        stmt = self._board_select(query, accounts, today)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            self.session.scalars(
                stmt.order_by(*_SORTS[query.sort], DwsPurchaseBoard.order_item_id)
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        )
        return rows, int(total)

    def board_rows_for_summary(
        self, query: BoardFilterQuery, accounts: frozenset[str], today: date
    ) -> list[DwsPurchaseBoard]:
        return list(self.session.scalars(self._board_select(query, accounts, today)))

    def board_rows_for_order(
        self, order_sn: str, accounts: frozenset[str]
    ) -> list[DwsPurchaseBoard]:
        return list(
            self.session.scalars(
                select(DwsPurchaseBoard)
                .where(
                    DwsPurchaseBoard.source_account_ref.in_(sorted(accounts)),
                    DwsPurchaseBoard.order_sn == order_sn,
                )
                .order_by(DwsPurchaseBoard.order_item_id, DwsPurchaseBoard.plan_key)
            )
        )

    def plans_by_sn(
        self, plan_sns: Sequence[str], accounts: frozenset[str]
    ) -> list[DwdPurchasePlan]:
        if not plan_sns:
            return []
        return list(
            self.session.scalars(
                select(DwdPurchasePlan)
                .where(
                    DwdPurchasePlan.source_account_ref.in_(sorted(accounts)),
                    DwdPurchasePlan.plan_sn.in_(list(plan_sns)),
                )
                .order_by(DwdPurchasePlan.plan_sn)
            )
        )

    # -- SKU cycles --

    def sku_cycles(
        self, skus: Sequence[str], accounts: frozenset[str]
    ) -> list[DwsPurchaseSkuCycle]:
        if not skus:
            return []
        return list(
            self.session.scalars(
                select(DwsPurchaseSkuCycle)
                .where(
                    DwsPurchaseSkuCycle.source_account_ref.in_(sorted(accounts)),
                    DwsPurchaseSkuCycle.sku.in_(list(skus)),
                )
                .order_by(DwsPurchaseSkuCycle.sku)
            )
        )

    def unstable_sku_count(self, accounts: frozenset[str]) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(DwsPurchaseSkuCycle)
                .where(
                    DwsPurchaseSkuCycle.source_account_ref.in_(sorted(accounts)),
                    DwsPurchaseSkuCycle.unstable.is_(True),
                )
            )
            or 0
        )

    # -- pending plans (status = 2, not yet on any purchase-order line) --

    def _pending_plan_select(
        self, query: PendingPlanQuery, accounts: frozenset[str]
    ) -> Select[tuple[DwdPurchasePlan]]:
        converted = (
            select(DwsPurchaseBoard.plan_sn)
            .where(
                DwsPurchaseBoard.source_account_ref.in_(sorted(accounts)),
                DwsPurchaseBoard.plan_sn.is_not(None),
            )
            .distinct()
        )
        p = DwdPurchasePlan
        clauses: list[Any] = [
            p.source_account_ref.in_(sorted(accounts)),
            p.status == PLAN_STATUS_PENDING_PURCHASE,
            p.plan_sn.not_in(converted),
        ]
        if query.store_id:
            clauses.append(p.store_id.in_(query.store_id))
        values = [v for raw in query.search_values for v in raw.replace(",", " ").split() if v]
        if values:
            clauses.append(or_(p.sku.in_(values), p.plan_sn.in_(values)))
        return select(p).where(and_(*clauses))

    def pending_plans(
        self, query: PendingPlanQuery, accounts: frozenset[str]
    ) -> list[DwdPurchasePlan]:
        """All matching pending plans; overdue filtering / paging happen in the service
        because the pending start date needs the rule threshold."""

        return list(
            self.session.scalars(
                self._pending_plan_select(query, accounts).order_by(
                    DwdPurchasePlan.create_date.asc().nulls_last(), DwdPurchasePlan.plan_sn
                )
            )
        )

    # -- dimensions --

    def store_names(self, accounts: frozenset[str]) -> dict[str, str | None]:
        return {
            row.store_id: row.store_name
            for row in self.session.scalars(
                select(LingxingStoreDimension).where(
                    LingxingStoreDimension.source_account_ref.in_(sorted(accounts))
                )
            )
        }
