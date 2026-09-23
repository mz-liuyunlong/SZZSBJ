"""Service layer for the PMC purchase board read API (Gate 3, G3-E).

Turns DWS rows into response schemas and computes the request-time aggregates the
summary cards need (Demo v1.4: 待到货 / 逾期未到货 / 待采购超时 / 平均采购交期 90 天 /
本月采购金额 / 交期不稳定 SKU / ItemID 待处理). No provider calls, no writes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchasePlan,
    DwsPurchaseBoard,
    DwsPurchaseSkuCycle,
)
from app.modules.pmc_purchase.repository import PmcPurchaseReadRepository
from app.modules.pmc_purchase.schemas import (
    BoardFilterQuery,
    BoardListData,
    BoardListQuery,
    BoardRowRead,
    BoardSummaryData,
    ItemIdRef,
    MoneyByCurrency,
    OrderDetailData,
    OrderPlanRef,
    OrderReceiptRef,
    OwnerRef,
    PendingPlanListData,
    PendingPlanQuery,
    PendingPlanRead,
    SkuCycleBrief,
    SkuCycleListData,
    SkuCycleQuery,
    SkuCycleRead,
    SkuCycleSample,
    StageRef,
    StoreRef,
)

FOUR_PLACES = Decimal("0.0001")
DEFAULT_S2_PENDING_DAYS = 7
AVERAGE_CYCLE_WINDOW_DAYS = 90


class PmcPurchaseReadService:
    def __init__(self, session: Session, *, today: date | None = None) -> None:
        self.repository = PmcPurchaseReadRepository(session)
        self.today = today or date.today()

    # -- 7.1 board list --

    def list_board(
        self, query: BoardListQuery, accounts: frozenset[str]
    ) -> tuple[BoardListData, int, datetime | None, int | None]:
        rows, total = self.repository.list_board(query, accounts, self.today)
        items = [_board_row(r) for r in rows]
        return BoardListData(items=items, total=total), total, _freshness(rows), _rule_of(rows)

    # -- 7.2 summary --

    def summary(
        self, query: BoardFilterQuery, accounts: frozenset[str]
    ) -> tuple[BoardSummaryData, datetime | None, int | None]:
        rows = self.repository.board_rows_for_summary(query, accounts, self.today)
        awaiting = {r.order_sn for r in rows if r.stage_code in ("S3", "S4")}
        arrival_overdue = {
            r.order_sn for r in rows if r.stage_code in ("S3", "S4") and r.overdue_days > 0
        }
        purchase_overdue = {r.order_sn for r in rows if r.stage_code == "S2" and r.overdue_days > 0}

        window_start = self.today - timedelta(days=AVERAGE_CYCLE_WINDOW_DAYS)
        cycles: dict[str, int] = {}
        for r in rows:
            if (
                r.arrival_date is not None
                and r.purchase_cycle_days is not None
                and r.arrival_date >= window_start
            ):
                cycles.setdefault(r.order_sn, r.purchase_cycle_days)
        average = (
            (Decimal(sum(cycles.values())) / Decimal(len(cycles))).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            if cycles
            else None
        )

        month_start = self.today.replace(day=1)
        by_currency: dict[str | None, Decimal] = defaultdict(lambda: Decimal(0))
        for r in rows:
            if r.order_date is not None and r.order_date >= month_start and r.amount_allocated:
                by_currency[r.currency_code] += r.amount_allocated

        pending_plans = self._pending_plan_rows(
            PendingPlanQuery(store_id=query.store_id, overdue_only=True), accounts
        )

        data = BoardSummaryData(
            awaiting_arrival_orders=len(awaiting),
            arrival_overdue_orders=len(arrival_overdue),
            purchase_overdue_orders=len(purchase_overdue),
            purchase_overdue_plans=len(pending_plans[0]),
            average_purchase_cycle_days_90d=average,
            month_purchase_amount=[
                MoneyByCurrency(currency_code=code, amount=amount)
                for code, amount in sorted(by_currency.items(), key=lambda kv: kv[0] or "")
            ],
            unstable_sku_count=self.repository.unstable_sku_count(accounts),
            itemid_pending_lines=sum(1 for r in rows if r.item_id is None and r.stage_code != "S0"),
            wfs_not_ready_lines=sum(1 for r in rows if r.wfs_not_ready is True),
            unattributed_store_lines=sum(1 for r in rows if not r.store_attributed),
            as_of=self.today,
        )
        return data, _freshness(rows), _rule_of(rows)

    # -- 7.3 order detail --

    def order_detail(
        self, order_sn: str, accounts: frozenset[str]
    ) -> tuple[OrderDetailData, datetime | None, int | None]:
        rows = self.repository.board_rows_for_order(order_sn, accounts)
        if not rows:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        head = rows[0]
        receipt_sns: list[str] = []
        for r in rows:
            listed = r.source_lineage_json.get("receipt_order_sns")
            if not isinstance(listed, list):
                continue
            for sn in listed:
                if isinstance(sn, str) and sn and sn not in receipt_sns:
                    receipt_sns.append(sn)
        plan_sns = sorted({r.plan_sn for r in rows if r.plan_sn})
        plans = self.repository.plans_by_sn(plan_sns, accounts)
        skus = sorted({r.sku for r in rows if r.sku})
        cycles = self.repository.sku_cycles(skus, accounts)
        data = OrderDetailData(
            purchase_order_sn=head.order_sn,
            order_status=head.order_status,
            order_date=head.order_date,
            order_create_date=head.order_create_date,
            quantity_total=head.quantity_total,
            quantity_received=head.quantity_received,
            progress_ratio=head.progress_ratio,
            arrival_date=head.arrival_date,
            amount_total=head.amount_total,
            currency_code=head.currency_code,
            stage=_stage(head),
            lines=[_board_row(r) for r in rows],
            receipts=[
                OrderReceiptRef(
                    receipt_order_sn=sn, is_arrival_receipt=sn == head.arrival_receipt_order_sn
                )
                for sn in receipt_sns
            ],
            plans=[_plan_ref(p) for p in plans],
            sku_cycles=[_sku_cycle(c) for c in cycles],
        )
        return data, _freshness(rows), _rule_of(rows)

    # -- 7.4 SKU cycles --

    def sku_cycles(
        self, query: SkuCycleQuery, accounts: frozenset[str]
    ) -> tuple[SkuCycleListData, datetime | None, int | None]:
        requested = list(dict.fromkeys(s.strip() for s in query.sku if s.strip()))
        rows = self.repository.sku_cycles(requested, accounts)
        found = {r.sku for r in rows}
        data = SkuCycleListData(
            items=[_sku_cycle(r) for r in rows],
            missing=[s for s in requested if s not in found],
        )
        freshness = max((r.calculated_at for r in rows), default=None)
        rule = rows[0].rule_version if rows else None
        return data, freshness, rule

    # -- S2 card drill-down: plans approved but not yet ordered --

    def pending_plans(
        self, query: PendingPlanQuery, accounts: frozenset[str]
    ) -> tuple[PendingPlanListData, int, int | None]:
        items, threshold, rule_version = self._pending_plan_rows(query, accounts)
        total = len(items)
        start = (query.page - 1) * query.page_size
        page = items[start : start + query.page_size]
        return (
            PendingPlanListData(items=page, total=total, threshold_days=threshold),
            total,
            rule_version,
        )

    def _pending_plan_rows(
        self, query: PendingPlanQuery, accounts: frozenset[str]
    ) -> tuple[list[PendingPlanRead], int, int | None]:
        rule = self.repository.active_rule(self.today)
        threshold = rule.s2_pending_days if rule else DEFAULT_S2_PENDING_DAYS
        stores = self.repository.store_names(accounts)
        items: list[PendingPlanRead] = []
        for plan in self.repository.pending_plans(query, accounts):
            item = _pending_plan(plan, stores, threshold, self.today)
            if query.overdue_only and item.overdue_days <= 0:
                continue
            items.append(item)
        items.sort(key=lambda i: (-(i.pending_days or 0), i.plan_sn))
        return items, threshold, rule.version if rule else None


# --- mappers -------------------------------------------------------------------------------------


def _freshness(rows: list[DwsPurchaseBoard]) -> datetime | None:
    return max((r.calculated_at for r in rows), default=None)


def _rule_of(rows: list[DwsPurchaseBoard]) -> int | None:
    return rows[0].rule_version if rows else None


def _overdue_kind(row: DwsPurchaseBoard) -> Any:
    if row.overdue_days <= 0:
        return None
    return "purchase" if row.stage_code == "S2" else "arrival"


def _stage(row: DwsPurchaseBoard) -> StageRef:
    return StageRef(
        stage_code=row.stage_code,  # type: ignore[arg-type]
        stage_start=row.stage_start,
        stage_start_estimated=row.stage_start_estimated,
        threshold_days=row.threshold_days,
        due_date=row.due_date,
        overdue_days=row.overdue_days,
        overdue_kind=_overdue_kind(row),
        alert_due_since=row.alert_due_since,
    )


def _board_row(row: DwsPurchaseBoard) -> BoardRowRead:
    return BoardRowRead(
        purchase_order_sn=row.order_sn,
        order_item_id=row.order_item_id,
        plan_sn=row.plan_sn,
        plan_sns=list(row.plan_sns_json or []),
        order_status=row.order_status,
        stage=_stage(row),
        store=StoreRef(id=row.store_id, name=row.store_name, attributed=row.store_attributed),
        sku=row.sku,
        product_name=row.product_name,
        item_id=ItemIdRef(
            item_id=row.item_id,
            source=row.item_id_source,  # type: ignore[arg-type]
            source_ref=row.item_id_source_ref,
            matched_at=row.item_id_matched_at,
            match_status=row.item_id_match_status,  # type: ignore[arg-type]
            msku=row.msku,
            gtin=row.gtin,
            fulfillment_type=row.fulfillment_type,
            wfs_not_ready=row.wfs_not_ready,
        ),
        owner=OwnerRef(uid=row.owner_uid, name=row.owner_name),
        quantity_total=row.quantity_total,
        quantity_allocated=row.quantity_allocated,
        quantity_received=row.quantity_received,
        progress_ratio=row.progress_ratio,
        remaining_quantity=row.remaining_quantity,
        order_date=row.order_date,
        order_create_date=row.order_create_date,
        plan_create_date=row.plan_create_date,
        arrival_date=row.arrival_date,
        arrival_receipt_order_sn=row.arrival_receipt_order_sn,
        purchase_cycle_days=row.purchase_cycle_days,
        approval_cycle_days=row.approval_cycle_days,
        sku_cycle=SkuCycleBrief(
            value_days=row.sku_cycle_days,
            source=row.sku_cycle_source,  # type: ignore[arg-type]
            sample_count=row.sku_cycle_sample_count,
            unstable=row.sku_cycle_unstable,
        ),
        unit_price=row.unit_price,
        amount_allocated=row.amount_allocated,
        amount_total=row.amount_total,
        currency_code=row.currency_code,
        calculated_at=row.calculated_at,
    )


def _sku_cycle(row: DwsPurchaseSkuCycle) -> SkuCycleRead:
    return SkuCycleRead(
        sku=row.sku,
        value_days=row.value_days,
        source=row.source,  # type: ignore[arg-type]
        sample_count=row.sample_count,
        baseline_days=row.baseline_days,
        baseline_set_on=row.baseline_set_on,
        lingxing_default_days=row.lingxing_default_days,
        unstable=row.unstable,
        range_days=row.range_days,
        samples=[SkuCycleSample.model_validate(s) for s in row.samples_json or []],
        rule_version=row.rule_version,
        calculated_at=row.calculated_at,
    )


def _plan_ref(plan: DwdPurchasePlan) -> OrderPlanRef:
    return OrderPlanRef(
        plan_sn=plan.plan_sn,
        plan_status=plan.status,
        plan_create_date=plan.create_date,
        quantity_plan=plan.quantity_plan,
        remark_item_id=plan.remark_item_id,
        store_id=plan.store_id,
    )


def _pending_plan(
    plan: DwdPurchasePlan, stores: dict[str, str | None], threshold: int, today: date
) -> PendingPlanRead:
    since = plan.first_seen_pending_date or plan.create_date
    pending_days = (today - since).days if since else None
    overdue = max(pending_days - threshold, 0) if pending_days is not None else 0
    if not plan.store_attributed:
        overdue = 0  # rules §1.3: no overdue for unattributed-store documents
    return PendingPlanRead(
        plan_sn=plan.plan_sn,
        plan_status=plan.status,
        plan_create_date=plan.create_date,
        pending_since=since,
        pending_since_estimated=plan.first_seen_pending_date is None,
        pending_days=pending_days,
        overdue_days=overdue,
        store=StoreRef(
            id=plan.store_id,
            name=stores.get(plan.store_id) if plan.store_id else None,
            attributed=plan.store_attributed,
        ),
        sku=plan.sku,
        product_name=plan.product_name,
        quantity_plan=plan.quantity_plan,
        remark_item_id=plan.remark_item_id,
    )
