"""DWD → DWS refresh for the PMC purchase board (Gate 3, PR G3-D).

Reads the three ``dwd_purchase_*`` tables, the current ``rule_purchase_thresholds``
version, the active ``manual_purchase_cycle_override`` records, the store / listing /
product-info dimensions and the receipt lines of succeeded runs, applies the pure rules
in ``calculations`` and rewrites the three DWS tables for one account
(delete + insert, ``calc_version`` + ``rule_version`` + ``source_lineage_json``, the
DATA-PAGES mart convention).

Scope (rules v4, PRP §7, gate3-plan G3-D, Rocky 2026-09-23 "按之前的来"):

* Board rows are purchase-order lines (order × line × plan). Purchase plans that have
  not become an order are **not** board rows; their S2 list is read from
  ``dwd_purchase_plan`` directly by the API.
* Merged lines were already split by plan quantity in DWD (§5.2); this module only
  consumes ``quantity_allocated`` / ``amount_allocated``.
* Arrival = first receipt at which cumulative received quantity reaches
  ``quantity_total × arrival_ratio`` (§3.2, ratio from the rule table, default 0.5).
* Two overdue notions stay apart through ``stage_code``: ``S2`` = purchase overdue
  (order still 待下单), ``S3``/``S4`` = arrival overdue (ordered, not arrived).
* ItemID: ``from_system_plan`` > ``from_plan_remark`` > ``from_packing_slip`` >
  ``pending_packing_slip`` (#144). The packing-slip source is an injection point
  (``PackingSlipSource``); the default source has no data, so every row without a
  plan-remark ItemID is ``pending_packing_slip``. No manual ItemID exists.
* ``sid = 0`` rows keep ``store_attributed = False``: no overdue, no cycle sample.
* Manual layer is read, never written; DWD is never written.

The refresher commits after a successful run and rolls back on any error. It never
calls a provider and never schedules itself.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Protocol
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import LingxingStoreDimension, WalmartListingDimension
from app.modules.integration_sync.models import IntegrationSyncRun
from app.modules.pmc_purchase.calculations import (
    ORDER_STATUS_VOID,
    ArrivalResult,
    CycleSample,
    ItemIdAttribution,
    ManualBaseline,
    PurchaseThresholds,
    ReceiptEvent,
    SkuCycleResult,
    StageResult,
    classify_order_stage,
    compute_arrival,
    compute_sku_cycle,
    cycle_threshold_days,
    days_between,
    resolve_item_id,
    wfs_not_ready,
)
from app.modules.pmc_purchase.dwd_builder import build_receipt_lines
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrder,
    DwdPurchaseOrderLineItem,
    DwdPurchasePlan,
    DwsPurchaseBoard,
    DwsPurchasePending,
    DwsPurchaseSkuCycle,
    ManualPurchaseCycleOverride,
    RulePurchaseThresholds,
)
from app.modules.pmc_purchase.models import (
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent

DWS_CALC_VERSION: Final = "pmc_purchase.dws.v1"
RULE_KEY: Final = "pmc_purchase_thresholds"

MATCH_STATUS_MATCHED: Final = "matched"
MATCH_STATUS_PENDING: Final = "pending"
MATCH_STATUS_UNRESOLVED: Final = "unresolved"

PENDING_ITEMID: Final = "itemid_pending"
PENDING_WFS: Final = "wfs_not_ready"
PENDING_OVERDUE: Final = "overdue"


class PmcPurchaseDwsRefreshError(RuntimeError):
    """Stable error codes; the message is the code."""


# --- packing-slip injection point (rules §5.3) -------------------------------------------


@dataclass(frozen=True, slots=True)
class PackingSlipMatch:
    item_id: str
    packing_slip_no: str
    matched_at: datetime


class PackingSlipSource(Protocol):
    """Where ``from_packing_slip`` attributions come from once the domestic-warehouse
    packing-slip table exists. ``None`` = no slip for this line yet (→ pending)."""

    def lookup(
        self, *, order_sn: str, order_item_id: str, sku: str | None, store_id: str | None
    ) -> PackingSlipMatch | None: ...


class NoPackingSlipSource:
    """Default until the packing-slip table is defined: every line stays pending."""

    def lookup(
        self, *, order_sn: str, order_item_id: str, sku: str | None, store_id: str | None
    ) -> PackingSlipMatch | None:
        return None


# --- result ----------------------------------------------------------------------------------


@dataclass(slots=True)
class DwsRefreshResult:
    source_account_ref: str
    calc_version: str
    rule_version: int
    today: date
    board_rows: int = 0
    sku_cycle_rows: int = 0
    pending_rows: int = 0
    orders_seen: int = 0
    lines_seen: int = 0
    plans_seen: int = 0
    receipt_lines: int = 0
    overrides_active: int = 0
    stage_counts: dict[str, int] = field(default_factory=dict)
    item_id_source_counts: dict[str, int] = field(default_factory=dict)
    pending_counts: dict[str, int] = field(default_factory=dict)

    def as_message(self) -> str:
        stages = ",".join(f"{k}={v}" for k, v in sorted(self.stage_counts.items()))
        sources = ",".join(f"{k}={v}" for k, v in sorted(self.item_id_source_counts.items()))
        pending = ",".join(f"{k}={v}" for k, v in sorted(self.pending_counts.items()))
        return (
            f"account={self.source_account_ref} calc_version={self.calc_version} "
            f"rule_version={self.rule_version} today={self.today.isoformat()} "
            f"board={self.board_rows} sku_cycles={self.sku_cycle_rows} "
            f"pending={self.pending_rows} orders={self.orders_seen} lines={self.lines_seen} "
            f"plans={self.plans_seen} receipt_lines={self.receipt_lines} "
            f"overrides={self.overrides_active} stages[{stages}] "
            f"item_id_sources[{sources}] pending_types[{pending}]"
        )


# --- internal lookups ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Listing:
    msku: str | None
    gtin: str | None
    fulfillment_type: str | None


@dataclass(frozen=True, slots=True)
class _Product:
    owner_uid: str | None
    owner_name: str | None
    delivery_days: int | None


@dataclass(slots=True)
class _SkuOverrides:
    excluded: dict[str, tuple[datetime, bool, UUID]] = field(default_factory=dict)
    arrival: dict[str, tuple[datetime, date, UUID]] = field(default_factory=dict)
    baseline: tuple[datetime, ManualBaseline, UUID] | None = None

    def ids(self) -> list[str]:
        out = [str(v[2]) for v in self.excluded.values()]
        out += [str(v[2]) for v in self.arrival.values()]
        if self.baseline is not None:
            out.append(str(self.baseline[2]))
        return sorted(out)


@dataclass(frozen=True, slots=True)
class _OrderFacts:
    order: DwdPurchaseOrder
    arrival: ArrivalResult
    receipts: list[ReceiptEvent]


# --- refresher -------------------------------------------------------------------------------


class PmcPurchaseDwsRefresher:
    def __init__(
        self,
        session: Session,
        *,
        packing_slips: PackingSlipSource | None = None,
        now: datetime | None = None,
        calc_version: str = DWS_CALC_VERSION,
    ) -> None:
        self.session = session
        self.packing_slips: PackingSlipSource = packing_slips or NoPackingSlipSource()
        self.now = now or datetime.now(UTC)
        self.calc_version = calc_version

    def refresh(self, *, source_account_ref: str, today: date | None = None) -> DwsRefreshResult:
        account = (source_account_ref or "").strip()
        if not account:
            raise PmcPurchaseDwsRefreshError("PMC_PURCHASE_DWS_SOURCE_ACCOUNT_REF_INVALID")
        try:
            result = self._refresh(account, today or self.now.date())
            self.session.commit()
        except PmcPurchaseDwsRefreshError:
            self.session.rollback()
            raise
        except Exception as error:
            self.session.rollback()
            raise PmcPurchaseDwsRefreshError("PMC_PURCHASE_DWS_REFRESH_FAILED") from error
        return result

    # -- orchestration --

    def _refresh(self, account: str, today: date) -> DwsRefreshResult:
        rule_row = self._active_rule(today)
        thresholds = _thresholds_from_rule(rule_row)
        result = DwsRefreshResult(
            source_account_ref=account,
            calc_version=self.calc_version,
            rule_version=rule_row.version,
            today=today,
        )

        plans = {
            p.plan_sn: p
            for p in self.session.scalars(
                select(DwdPurchasePlan).where(DwdPurchasePlan.source_account_ref == account)
            )
        }
        orders = {
            o.order_sn: o
            for o in self.session.scalars(
                select(DwdPurchaseOrder).where(DwdPurchaseOrder.source_account_ref == account)
            )
        }
        lines = list(
            self.session.scalars(
                select(DwdPurchaseOrderLineItem)
                .where(DwdPurchaseOrderLineItem.source_account_ref == account)
                .order_by(
                    DwdPurchaseOrderLineItem.order_sn,
                    DwdPurchaseOrderLineItem.line_ordinal,
                    DwdPurchaseOrderLineItem.plan_key,
                )
            )
        )
        result.plans_seen, result.orders_seen, result.lines_seen = (
            len(plans),
            len(orders),
            len(lines),
        )

        stores = self._stores(account)
        listings = self._listings(account)
        products = self._products(account)
        overrides, override_count = self._overrides(account)
        result.overrides_active = override_count

        receipts_by_order, receipt_line_count = self._receipts_by_order(account, lines)
        result.receipt_lines = receipt_line_count

        facts: dict[str, _OrderFacts] = {}
        for order_sn, order in orders.items():
            receipts = receipts_by_order.get(order_sn, [])
            quantity_total = order.quantity_total
            if quantity_total is None:
                quantity_total = sum(
                    ln.quantity_allocated for ln in lines if ln.order_sn == order_sn
                )
            facts[order_sn] = _OrderFacts(
                order=order,
                arrival=compute_arrival(
                    quantity_total=max(quantity_total, 0),
                    receipts=receipts,
                    thresholds=thresholds,
                ),
                receipts=receipts,
            )

        cycles = self._sku_cycles(lines, facts, overrides, products, thresholds)
        thresholds_by_sku = {sku: cycle_threshold_days(c) for sku, c in cycles.items()}

        board_rows: list[DwsPurchaseBoard] = []
        pending_rows: list[DwsPurchasePending] = []
        for line in lines:
            fact = facts.get(line.order_sn)
            if fact is None:
                # A line without its order header cannot be staged; DWD keeps them
                # consistent, so this only happens on partial publishes.
                continue
            plan = plans.get(line.plan_sn) if line.plan_sn else None
            cycle = cycles.get(line.sku or "")
            row, pendings = self._board_row(
                line=line,
                fact=fact,
                plan=plan,
                cycle=cycle,
                sku_threshold=thresholds_by_sku.get(line.sku or ""),
                stores=stores,
                listings=listings,
                products=products,
                overrides=overrides.get(line.sku or ""),
                thresholds=thresholds,
                rule_version=rule_row.version,
                today=today,
                account=account,
            )
            board_rows.append(row)
            pending_rows.extend(pendings)
            result.stage_counts[row.stage_code] = result.stage_counts.get(row.stage_code, 0) + 1
            result.item_id_source_counts[row.item_id_source] = (
                result.item_id_source_counts.get(row.item_id_source, 0) + 1
            )
        for pending in pending_rows:
            result.pending_counts[pending.pending_type] = (
                result.pending_counts.get(pending.pending_type, 0) + 1
            )

        cycle_rows = [
            self._cycle_row(
                sku, cycle, overrides.get(sku), products.get(sku), rule_row.version, account
            )
            for sku, cycle in sorted(cycles.items())
        ]

        # delete + insert per account (mart convention); DWD / manual / rule untouched.
        for model in (DwsPurchaseBoard, DwsPurchaseSkuCycle, DwsPurchasePending):
            self.session.execute(delete(model).where(model.source_account_ref == account))
        self.session.add_all(board_rows)
        self.session.add_all(cycle_rows)
        self.session.add_all(pending_rows)
        self.session.flush()

        result.board_rows = len(board_rows)
        result.sku_cycle_rows = len(cycle_rows)
        result.pending_rows = len(pending_rows)
        return result

    # -- inputs --

    def _active_rule(self, today: date) -> RulePurchaseThresholds:
        row = self.session.scalars(
            select(RulePurchaseThresholds)
            .where(
                RulePurchaseThresholds.rule_key == RULE_KEY,
                RulePurchaseThresholds.is_active.is_(True),
                RulePurchaseThresholds.effective_from <= today,
            )
            .order_by(
                RulePurchaseThresholds.effective_from.desc(),
                RulePurchaseThresholds.version.desc(),
            )
        ).first()
        if row is None:
            raise PmcPurchaseDwsRefreshError("PMC_PURCHASE_DWS_RULE_VERSION_MISSING")
        if row.effective_to is not None and row.effective_to <= today:
            raise PmcPurchaseDwsRefreshError("PMC_PURCHASE_DWS_RULE_VERSION_EXPIRED")
        return row

    def _stores(self, account: str) -> dict[str, str | None]:
        return {
            s.store_id: s.store_name
            for s in self.session.scalars(
                select(LingxingStoreDimension).where(
                    LingxingStoreDimension.source_account_ref == account
                )
            )
        }

    def _listings(self, account: str) -> dict[tuple[str, str], _Listing]:
        return {
            (row.store_id, row.item_id): _Listing(row.msku, row.gtin, row.fulfillment_type)
            for row in self.session.scalars(
                select(WalmartListingDimension).where(
                    WalmartListingDimension.source_account_ref == account
                )
            )
        }

    def _products(self, account: str) -> dict[str, _Product]:
        out: dict[str, _Product] = {}
        for row in self.session.scalars(
            select(LingxingSkuProductInfoCurrent).where(
                LingxingSkuProductInfoCurrent.source_account_ref == account
            )
        ):
            if row.lingxing_sku_code:
                out[row.lingxing_sku_code] = _Product(
                    row.owner_uid, row.owner_name, row.purchase_delivery_days
                )
        return out

    def _overrides(self, account: str) -> tuple[dict[str, _SkuOverrides], int]:
        """Active manual corrections per SKU; the newest record per target wins."""

        by_sku: dict[str, _SkuOverrides] = defaultdict(_SkuOverrides)
        count = 0
        rows = self.session.scalars(
            select(ManualPurchaseCycleOverride)
            .where(
                ManualPurchaseCycleOverride.source_account_ref == account,
                ManualPurchaseCycleOverride.is_active.is_(True),
                ManualPurchaseCycleOverride.effective_from <= self.now,
            )
            .order_by(
                ManualPurchaseCycleOverride.effective_from, ManualPurchaseCycleOverride.created_at
            )
        )
        for row in rows:
            if row.effective_to is not None and row.effective_to <= self.now:
                continue
            count += 1
            bucket = by_sku[row.sku]
            if row.kind in ("exclude", "restore") and row.purchase_order_sn:
                bucket.excluded[row.purchase_order_sn] = (
                    row.effective_from,
                    row.kind == "exclude",
                    row.id,
                )
            elif row.kind == "arrival_date" and row.purchase_order_sn and row.value_date:
                bucket.arrival[row.purchase_order_sn] = (row.effective_from, row.value_date, row.id)
            elif row.kind == "baseline" and row.value_days is not None:
                bucket.baseline = (
                    row.effective_from,
                    ManualBaseline(value_days=row.value_days, set_on=row.effective_from.date()),
                    row.id,
                )
        return dict(by_sku), count

    def _receipts_by_order(
        self, account: str, lines: Sequence[DwdPurchaseOrderLineItem]
    ) -> tuple[dict[str, list[ReceiptEvent]], int]:
        """Receipt quantities per purchase order from succeeded-run ODS receipt lines,
        linked through ``order_item_id`` ↔ line ``order_item_id`` (§3.2)."""

        succeeded = select(IntegrationSyncRun.id).where(IntegrationSyncRun.status == "succeeded")
        # ``Any``: the ODS ORM rows satisfy the builder protocols structurally, but mypy
        # cannot prove it through ``Mapped[...]`` (same workaround as ``publisher``).
        receipts: list[Any] = list(
            self.session.scalars(
                select(LingxingReceiptOrderOds).where(
                    LingxingReceiptOrderOds.source_account_ref == account,
                    LingxingReceiptOrderOds.run_id.in_(succeeded),
                )
            )
        )
        items: list[Any] = list(
            self.session.scalars(
                select(LingxingReceiptOrderItemOds).where(
                    LingxingReceiptOrderItemOds.source_account_ref == account,
                    LingxingReceiptOrderItemOds.run_id.in_(succeeded),
                )
            )
        )
        order_of_item = {ln.order_item_id: ln.order_sn for ln in lines}
        receipt_lines, _counts = build_receipt_lines(receipts, items, set(order_of_item))
        events: dict[str, list[ReceiptEvent]] = defaultdict(list)
        for rl in receipt_lines:
            order_sn = order_of_item.get(rl.order_item_id)
            if order_sn is None or rl.receive_date is None:
                continue
            events[order_sn].append(
                ReceiptEvent(
                    receive_date=rl.receive_date,
                    quantity=rl.quantity,
                    receipt_order_sn=rl.receipt_order_sn,
                )
            )
        return events, len(receipt_lines)

    # -- calculations --

    def _sku_cycles(
        self,
        lines: Sequence[DwdPurchaseOrderLineItem],
        facts: dict[str, _OrderFacts],
        overrides: dict[str, _SkuOverrides],
        products: dict[str, _Product],
        thresholds: PurchaseThresholds,
    ) -> dict[str, SkuCycleResult]:
        """§4.2 candidates: arrived, non-void, store-attributed orders, one sample per
        (sku, order). Manual arrival-date and exclude/restore corrections applied first."""

        samples: dict[str, dict[str, CycleSample]] = defaultdict(dict)
        skus: set[str] = set()
        for line in lines:
            sku = line.sku
            if not sku:
                continue
            skus.add(sku)
            fact = facts.get(line.order_sn)
            if fact is None or not line.store_attributed:
                continue
            order = fact.order
            if order.status == ORDER_STATUS_VOID or order.order_date is None:
                continue
            arrival = fact.arrival.arrival_date
            sku_overrides = overrides.get(sku)
            if sku_overrides is not None and line.order_sn in sku_overrides.arrival:
                arrival = sku_overrides.arrival[line.order_sn][1]
            if arrival is None or line.order_sn in samples[sku]:
                continue
            excluded = bool(
                sku_overrides is not None
                and line.order_sn in sku_overrides.excluded
                and sku_overrides.excluded[line.order_sn][1]
            )
            samples[sku][line.order_sn] = CycleSample(
                purchase_order_sn=line.order_sn,
                order_date=order.order_date,
                arrival_date=arrival,
                manually_excluded=excluded,
            )
        cycles: dict[str, SkuCycleResult] = {}
        for sku in skus:
            sku_overrides = overrides.get(sku)
            baseline = (
                sku_overrides.baseline[1] if sku_overrides and sku_overrides.baseline else None
            )
            product = products.get(sku)
            cycles[sku] = compute_sku_cycle(
                samples=list(samples.get(sku, {}).values()),
                baseline=baseline,
                lingxing_default_days=product.delivery_days if product else None,
                thresholds=thresholds,
            )
        return cycles

    def _board_row(
        self,
        *,
        line: DwdPurchaseOrderLineItem,
        fact: _OrderFacts,
        plan: DwdPurchasePlan | None,
        cycle: SkuCycleResult | None,
        sku_threshold: int | None,
        stores: dict[str, str | None],
        listings: dict[tuple[str, str], _Listing],
        products: dict[str, _Product],
        overrides: _SkuOverrides | None,
        thresholds: PurchaseThresholds,
        rule_version: int,
        today: date,
        account: str,
    ) -> tuple[DwsPurchaseBoard, list[DwsPurchasePending]]:
        order = fact.order
        stage: StageResult = classify_order_stage(
            order_status=order.status,
            order_create_date=order.create_date,
            order_date=order.order_date,
            arrival=fact.arrival,
            sku_cycle_days=sku_threshold,
            store_attributed=line.store_attributed,
            today=today,
            thresholds=thresholds,
        )
        attribution, source_ref, matched_at = self._attribute_item_id(line, plan)
        listing = (
            listings.get((line.store_id, attribution.item_id))
            if line.store_id and attribution.item_id
            else None
        )
        product = products.get(line.sku or "")
        wfs_flag = wfs_not_ready(attribution.source, listing.fulfillment_type if listing else None)
        if attribution.item_id is not None:
            match_status = MATCH_STATUS_MATCHED
        elif attribution.source == "pending_packing_slip":
            match_status = MATCH_STATUS_PENDING
        else:
            match_status = MATCH_STATUS_UNRESOLVED

        lineage: dict[str, object] = {
            "dwd_line_id": str(line.id),
            "dwd_order_id": str(order.id),
            "dwd_plan_id": str(plan.id) if plan else None,
            "receipt_order_sns": sorted({r.receipt_order_sn or "" for r in fact.receipts}),
            "rule_version": rule_version,
            "override_ids": overrides.ids() if overrides else [],
            "listing_matched": listing is not None,
            "product_matched": product is not None,
        }
        row = DwsPurchaseBoard(
            id=uuid4(),
            source_account_ref=account,
            calc_version=self.calc_version,
            rule_version=rule_version,
            calculated_at=self.now,
            source_lineage_json=lineage,
            order_sn=line.order_sn,
            order_item_id=line.order_item_id,
            plan_key=line.plan_key,
            plan_sn=line.plan_sn,
            plan_sns_json=[line.plan_sn] if line.plan_sn else [],
            order_status=order.status,
            plan_status=plan.status if plan else None,
            stage_code=stage.stage_code,
            stage_start=stage.stage_start,
            threshold_days=stage.threshold_days,
            due_date=stage.due_date,
            overdue_days=stage.overdue_days,
            alert_due_since=stage.alert_due_since,
            stage_start_estimated=stage.start_estimated,
            store_id=line.store_id,
            store_name=stores.get(line.store_id) if line.store_id else None,
            store_attributed=line.store_attributed,
            sku=line.sku,
            product_name=line.product_name or (plan.product_name if plan else None),
            msku=listing.msku if listing else None,
            gtin=listing.gtin if listing else None,
            item_id=attribution.item_id,
            item_id_source=attribution.source,
            item_id_source_ref=source_ref,
            item_id_matched_at=matched_at,
            item_id_match_status=match_status,
            owner_uid=product.owner_uid if product else None,
            owner_name=product.owner_name if product else None,
            fulfillment_type=listing.fulfillment_type if listing else None,
            wfs_not_ready=wfs_flag,
            quantity_total=order.quantity_total,
            quantity_allocated=line.quantity_allocated,
            quantity_received=fact.arrival.quantity_received,
            progress_ratio=fact.arrival.progress_ratio,
            remaining_quantity=fact.arrival.remaining_quantity,
            order_date=order.order_date,
            order_create_date=order.create_date,
            plan_create_date=plan.create_date if plan else None,
            arrival_date=fact.arrival.arrival_date,
            arrival_receipt_order_sn=fact.arrival.arrival_receipt_order_sn,
            purchase_cycle_days=days_between(order.order_date, fact.arrival.arrival_date),
            approval_cycle_days=days_between(plan.create_date, order.create_date) if plan else None,
            sku_cycle_days=cycle.value_days if cycle else None,
            sku_cycle_source=cycle.source if cycle else None,
            sku_cycle_sample_count=cycle.sample_count if cycle else None,
            sku_cycle_unstable=bool(cycle.unstable) if cycle else False,
            unit_price=line.unit_price,
            amount_allocated=line.amount_allocated,
            amount_total=order.amount_total,
            currency_code=order.currency_code,
        )

        pendings: list[DwsPurchasePending] = []

        def _pending(kind: str, detail: dict[str, object]) -> None:
            pendings.append(
                DwsPurchasePending(
                    id=uuid4(),
                    source_account_ref=account,
                    calc_version=self.calc_version,
                    rule_version=rule_version,
                    calculated_at=self.now,
                    source_lineage_json={"dwd_line_id": str(line.id), "rule_version": rule_version},
                    pending_type=kind,
                    order_sn=line.order_sn,
                    order_item_id=line.order_item_id,
                    plan_key=line.plan_key,
                    plan_sn=line.plan_sn,
                    sku=line.sku,
                    store_id=line.store_id,
                    item_id=attribution.item_id,
                    item_id_source=attribution.source,
                    stage_code=stage.stage_code,
                    overdue_days=stage.overdue_days,
                    owner_uid=product.owner_uid if product else None,
                    owner_name=product.owner_name if product else None,
                    detail_json=detail,
                )
            )

        if attribution.item_id is None and stage.stage_code not in ("S0",):
            _pending(
                PENDING_ITEMID,
                {
                    "match_status": match_status,
                    "store_attributed": line.store_attributed,
                    "plan_found": line.plan_found,
                },
            )
        if wfs_flag is True:
            _pending(
                PENDING_WFS,
                {"fulfillment_type": listing.fulfillment_type if listing else None},
            )
        if stage.overdue_days > 0:
            _pending(
                PENDING_OVERDUE,
                {
                    # S2 = purchase overdue (待采购超时); S3/S4 = arrival overdue (到货逾期).
                    "overdue_kind": "purchase" if stage.stage_code == "S2" else "arrival",
                    "due_date": stage.due_date.isoformat() if stage.due_date else None,
                    "threshold_days": stage.threshold_days,
                    "progress_ratio": (
                        str(fact.arrival.progress_ratio)
                        if fact.arrival.progress_ratio is not None
                        else None
                    ),
                },
            )
        return row, pendings

    def _attribute_item_id(
        self, line: DwdPurchaseOrderLineItem, plan: DwdPurchasePlan | None
    ) -> tuple[ItemIdAttribution, str | None, datetime | None]:
        remark_item_id = line.remark_item_id or (plan.remark_item_id if plan else None)
        slip = self.packing_slips.lookup(
            order_sn=line.order_sn,
            order_item_id=line.order_item_id,
            sku=line.sku,
            store_id=line.store_id,
        )
        attribution = resolve_item_id(
            system_plan_item_id=None,  # reserved: plans created by this system (not built yet)
            plan_remark_item_id=remark_item_id,
            packing_slip_item_id=slip.item_id if slip else None,
            packing_slip_pending=slip is None,
        )
        if attribution.source == "from_plan_remark":
            return attribution, line.plan_sn, self.now
        if attribution.source == "from_packing_slip" and slip is not None:
            return attribution, slip.packing_slip_no, slip.matched_at
        return attribution, None, None

    def _cycle_row(
        self,
        sku: str,
        cycle: SkuCycleResult,
        overrides: _SkuOverrides | None,
        product: _Product | None,
        rule_version: int,
        account: str,
    ) -> DwsPurchaseSkuCycle:
        baseline = overrides.baseline[1] if overrides and overrides.baseline else None
        return DwsPurchaseSkuCycle(
            id=uuid4(),
            source_account_ref=account,
            calc_version=self.calc_version,
            rule_version=rule_version,
            calculated_at=self.now,
            source_lineage_json={
                "rule_version": rule_version,
                "override_ids": overrides.ids() if overrides else [],
                "product_matched": product is not None,
                "sample_order_sns": [c.purchase_order_sn for c in cycle.considered],
            },
            sku=sku,
            value_days=cycle.value_days,
            source=cycle.source,
            sample_count=cycle.sample_count,
            baseline_days=baseline.value_days if baseline else None,
            baseline_set_on=baseline.set_on if baseline else None,
            lingxing_default_days=product.delivery_days if product else None,
            unstable=cycle.unstable,
            range_days=cycle.range_days,
            samples_json=[
                {
                    "purchase_order_sn": c.purchase_order_sn,
                    "order_date": c.order_date.isoformat(),
                    "arrival_date": c.arrival_date.isoformat(),
                    "cycle_days": c.cycle_days,
                    "used": c.used,
                    "exclusion": c.exclusion,
                }
                for c in cycle.considered
            ],
        )


# --- helpers --------------------------------------------------------------------------------


def _thresholds_from_rule(row: RulePurchaseThresholds) -> PurchaseThresholds:
    return PurchaseThresholds(
        s1_approval_days=row.s1_approval_days,
        s2_pending_days=row.s2_pending_days,
        default_cycle_days=row.default_cycle_days,
        arrival_ratio=Decimal(row.arrival_ratio),
        auto_exclude_below_days=row.auto_exclude_below_days,
        sample_window=row.sample_window,
        min_samples_for_average=row.min_samples_for_average,
        unstable_min_samples=row.unstable_min_samples,
        unstable_range_days=row.unstable_range_days,
        baseline_evict_at_samples=row.baseline_evict_at_samples,
    )


def summarize(results: Iterable[DwsRefreshResult]) -> str:
    return "\n".join(r.as_message() for r in results)


__all__ = [
    "DWS_CALC_VERSION",
    "DwsRefreshResult",
    "NoPackingSlipSource",
    "PackingSlipMatch",
    "PackingSlipSource",
    "PmcPurchaseDwsRefreshError",
    "PmcPurchaseDwsRefresher",
    "summarize",
]
