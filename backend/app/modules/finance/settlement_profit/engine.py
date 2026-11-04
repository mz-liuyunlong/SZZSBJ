"""Pure (store, bill month) calculation: PRP §8.2–§8.8.

Sign convention: settlement-sourced columns keep the settlement sign (income +, fee −);
``goods_cost_usd``, ``ad_cost_usd`` and ``disposal_loss_usd`` are positive costs and are
subtracted in gross profit.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .inputs import (
    ORDER_KINDS,
    OTHER_INCOME_KINDS,
    Adjustment,
    FlowMovement,
    ReviewAction,
    SettlementKind,
    StoreMonthInput,
)
from .keys import (
    UNMAPPED_STORE_ID,
    order_line_key,
    unassigned_line_key,
)
from .money import ZERO, allocate, month_start, q4, to_cny, to_usd
from .rules import (
    ALERT_CATEGORIES,
    DISPOSAL_FEE_TYPES,
    inventory_category,
    review_accelerator_weights,
)

RECONCILE_TOLERANCE_USD = Decimal("0.01")

ORDER_COLUMN = {
    SettlementKind.SALE: "sales_amount_usd",
    SettlementKind.PLATFORM_SUBSIDY: "platform_subsidy_usd",
    SettlementKind.REFUND: "refund_amount_usd",
    SettlementKind.COMMISSION: "commission_usd",
    SettlementKind.WFS_FULFILLMENT: "wfs_fulfillment_fee_usd",
    SettlementKind.RETURN_FEE: "return_fee_usd",
    SettlementKind.TAX_WITHHELD: "tax_withheld_usd",
}
ITEM_COLUMN = {
    SettlementKind.WFS_SERVICE: "wfs_service_fee_usd",
    SettlementKind.STORAGE_FEE: "storage_fee_usd",
    SettlementKind.REVIEW_ACCELERATOR: "review_accelerator_usd",
    # disposal operation fee lands in 弃置损耗 (positive loss), tracked signed separately
    SettlementKind.DISPOSAL_FEE: "disposal_fee_signed_usd",
}
# signed settlement columns (reconcile + gross profit)
SETTLEMENT_COLUMNS = (*ORDER_COLUMN.values(), *ITEM_COLUMN.values())
# §8.5: item → order weight
BY_SALES_KINDS = frozenset({SettlementKind.REVIEW_ACCELERATOR})


@dataclass
class Amounts:
    values: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))

    def add(self, column: str, amount: Decimal) -> None:
        self.values[column] = self.values[column] + amount

    def get(self, column: str) -> Decimal:
        return self.values.get(column, ZERO)


@dataclass
class OrderLineResult:
    line_key: str
    report_key: str
    platform_order_no: str
    order_item_no: str
    item_id: str
    gtin: str | None
    quantity: Decimal = ZERO
    amounts: Amounts = field(default_factory=Amounts)
    ad_cost_usd: Decimal = ZERO
    purchase_cost_cny: Decimal | None = None
    head_cost_cny: Decimal | None = None
    other_cost_cny: Decimal | None = None
    goods_cost_usd: Decimal | None = None
    gross_profit_usd: Decimal | None = None
    gross_profit_cny: Decimal | None = None
    net_profit_share_cny: Decimal | None = None
    cost_match_status: str = "matched"
    reasons: list[str] = field(default_factory=list)
    review_status: str = "auto"
    owner_ref: str | None = None
    msku: str | None = None
    serial_number: str | None = None
    ordered_at: object = None
    shipped_at: object = None
    settled_at: object = None


@dataclass
class ItemMonthResult:
    item_id: str
    owner_ref: str | None
    msku: str | None = None
    sales_quantity: Decimal = ZERO
    amounts: Amounts = field(default_factory=Amounts)
    ad_cost_usd: Decimal = ZERO
    disposal_goods_usd: Decimal = ZERO
    purchase_cost_cny: Decimal = ZERO
    head_cost_cny: Decimal = ZERO
    goods_cost_usd: Decimal | None = None
    gross_profit_usd: Decimal | None = None
    gross_profit_cny: Decimal | None = None
    net_profit_share_cny: Decimal | None = None
    net_profit_cny: Decimal | None = None

    @property
    def disposal_loss_usd(self) -> Decimal:
        return -self.amounts.get("disposal_fee_signed_usd") + self.disposal_goods_usd


@dataclass
class UnassignedResult:
    line_key: str
    store_id: str
    source_kind: str
    source_ref: str
    reason: str
    amount_usd: Decimal | None
    amount_cny: Decimal | None = None
    settlement_kind: SettlementKind | None = None  # None: not settlement money
    status: str = "pending"
    assigned_item_id: str | None = None
    assigned_store_id: str | None = None
    adjustment_id: str | None = None
    detail: dict[str, object] = field(default_factory=dict)


@dataclass
class MovementResult:
    movement: FlowMovement
    category: str
    store_id: str | None
    store_mapping_status: str  # mapped / unmapped / manual_assigned
    item_id: str | None
    goods_value_usd: Decimal | None


@dataclass
class ReconcileResult:
    settlement_total_usd: Decimal
    order_level_total_usd: Decimal
    unassigned_pending_usd: Decimal
    diff_usd: Decimal
    ad_daily_vs_settlement_diff_usd: Decimal
    inbound_freight_lx_vs_settlement_diff_usd: Decimal | None
    cross_month_disposal_fee_usd: Decimal
    status: str


@dataclass
class StoreMonthResult:
    store_id: str
    bill_month: date
    fx_rate: Decimal | None
    fx_status: str
    order_lines: list[OrderLineResult]
    items: dict[str, ItemMonthResult]
    unassigned: list[UnassignedResult]
    movements: list[MovementResult]
    reconcile: ReconcileResult
    other_income_usd: Decimal
    alerts: list[tuple[str, str]]
    blockers: list[str]
    ad_scope_note: str | None


# ------------------------------------------------------------------ helpers


def _latest(rows: Iterable[Adjustment | ReviewAction]) -> dict[str, Adjustment | ReviewAction]:
    out: dict[str, Adjustment | ReviewAction] = {}
    for r in sorted(rows, key=lambda r: r.acted_at):
        out[r.line_key] = r
    return out


def current_review_actions(
    actions: Iterable[ReviewAction], last_change_at: Mapping[str, datetime]
) -> list[ReviewAction]:
    """Drop reviews made before the line's last adjustment change (§8.9).

    ``last_change_at``: per line_key the latest ``acted_at`` / ``revoked_at`` of any of its
    adjustments, revoked ones included, so revoking an adjustment on a final-passed line
    sends it back to first review instead of reviving the old review.
    """
    return [
        a
        for a in actions
        if a.line_key not in last_change_at or a.acted_at > last_change_at[a.line_key]
    ]


def review_status(
    line_key: str,
    reasons: list[str],
    adjustments: Mapping[str, Adjustment],
    reviews: Mapping[str, ReviewAction],
    *,
    revised: bool = False,
) -> str:
    """§8.9: a change after a review sends the line back to first review.

    ``revised``: the line had an adjustment that was revoked; with no active adjustment and
    no later review it waits for first review (pending) instead of passing automatically.
    """
    adj = adjustments.get(line_key)
    rev = reviews.get(line_key)
    if rev is not None and (adj is None or adj.acted_at <= rev.acted_at):
        if rev.decision == "reject":
            return "rejected"
        return "final_passed" if rev.stage == "final" else "first_passed"
    if adj is not None:
        return "adjusted"
    return "pending" if reasons or revised else "auto"


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


# ------------------------------------------------------------------ engine


def calculate_store_month(
    inp: StoreMonthInput, *, month_has_unmapped_pending: bool = False
) -> StoreMonthResult:
    month = inp.bill_month
    store = inp.store_id
    rate = inp.fx_rate
    fx_status = "final" if rate is not None else "missing"
    alerts: list[tuple[str, str]] = []
    adjustments_by_key: dict[str, list[Adjustment]] = defaultdict(list)
    for a in inp.adjustments:
        adjustments_by_key[a.line_key].append(a)
    latest_adj = {k: v for k, v in _latest(inp.adjustments).items() if isinstance(v, Adjustment)}
    reviews = current_review_actions(inp.review_actions, inp.adjustment_changed_at)
    latest_rev = {k: v for k, v in _latest(reviews).items() if isinstance(v, ReviewAction)}
    unassigned: dict[str, UnassignedResult] = {}

    def to_unassigned(
        source_kind: str,
        source_ref: str,
        amount_usd: Decimal,
        kind: SettlementKind | None,
        reason: str = "unassigned",
        detail: dict[str, object] | None = None,
    ) -> None:
        key = unassigned_line_key(store, month, source_kind, source_ref)
        if key in unassigned:
            unassigned[key].amount_usd = (unassigned[key].amount_usd or ZERO) + amount_usd
            return
        unassigned[key] = UnassignedResult(
            line_key=key,
            store_id=store,
            source_kind=source_kind,
            source_ref=source_ref,
            reason=reason,
            amount_usd=amount_usd,
            settlement_kind=kind,
            detail=detail or {},
        )

    # ---- order lines (§0.1 / §0.2)
    orders: dict[str, OrderLineResult] = {}
    other_income = ZERO
    item_level: dict[SettlementKind, Decimal] = defaultdict(lambda: ZERO)
    settlement_total = ZERO
    ad_charges = ZERO
    wpc_charges = ZERO
    for line in inp.settlement_lines:
        if line.kind in OTHER_INCOME_KINDS:
            other_income += line.amount_usd
            continue
        if line.kind is SettlementKind.AD_CHARGE:
            ad_charges += line.amount_usd
            continue
        if line.kind is SettlementKind.INBOUND_WPC:
            wpc_charges += line.amount_usd
            continue
        settlement_total += line.amount_usd
        if line.kind in ORDER_KINDS and line.platform_order_no and line.order_item_no:
            item_id = line.item_id or (inp.gtin_to_item.get(line.gtin) if line.gtin else None)
            key = order_line_key(
                store, line.report_key, line.platform_order_no, line.order_item_no, line.gtin
            )
            if item_id is None:
                to_unassigned("order_line_no_item", key, line.amount_usd, line.kind)
                continue
            row = orders.get(key)
            if row is None:
                row = orders[key] = OrderLineResult(
                    line_key=key,
                    report_key=line.report_key,
                    platform_order_no=line.platform_order_no,
                    order_item_no=line.order_item_no,
                    item_id=item_id,
                    gtin=line.gtin,
                )
            row.amounts.add(ORDER_COLUMN[line.kind], line.amount_usd)
            if line.kind is SettlementKind.SALE:
                row.quantity += line.quantity
            if line.posted_at and (row.settled_at is None or line.posted_at > row.settled_at):
                row.settled_at = line.posted_at
        elif line.kind in ITEM_COLUMN:
            item_level[line.kind] += line.amount_usd
        else:
            to_unassigned("settlement_line", line.source_row_hash, line.amount_usd, line.kind)

    # ---- items
    items: dict[str, ItemMonthResult] = {}

    def item(item_id: str) -> ItemMonthResult:
        if item_id not in items:
            items[item_id] = ItemMonthResult(item_id, inp.owner_by_item.get(item_id))
        return items[item_id]

    orders_by_item: dict[str, list[OrderLineResult]] = defaultdict(list)
    for row in orders.values():
        orders_by_item[row.item_id].append(row)
        it = item(row.item_id)
        it.sales_quantity += row.quantity
        for col, amount in row.amounts.values.items():
            it.amounts.add(col, amount)

    sales_by_item = {i: it.amounts.get("sales_amount_usd") for i, it in items.items()}

    def push_to_item(kind: SettlementKind, item_id: str, amount: Decimal) -> None:
        """Item amount → item month, then → its orders (§8.5)."""
        column = ITEM_COLUMN[kind]
        rows = orders_by_item.get(item_id, [])
        if kind in BY_SALES_KINDS:
            weights = {r.line_key: max(r.amounts.get("sales_amount_usd"), ZERO) for r in rows}
        else:
            weights = {r.line_key: max(r.quantity, ZERO) for r in rows}
        if not rows or sum(weights.values(), ZERO) == 0:
            to_unassigned("item_without_orders", f"{kind.value}:{item_id}", amount, kind)
            return
        item(item_id).amounts.add(column, amount)
        for line_key, part in allocate(amount, weights).items():
            orders[line_key].amounts.add(column, part)

    def spread(kind: SettlementKind, total: Decimal, weights: dict[str | None, Decimal]) -> None:
        """Settlement total → items by weights; unmapped weight share → 待指定."""
        if total == 0:
            return
        weights = {k: v for k, v in weights.items() if v > 0}
        if not weights:
            to_unassigned("item_fee_no_weights", kind.value, total, kind)
            return
        for item_id, part in allocate(total, weights).items():
            if part == 0:
                continue
            if item_id is None:
                to_unassigned("item_fee_no_item", kind.value, part, kind)
            else:
                push_to_item(kind, item_id, part)

    # WFS service fee and disposal operation fee: GTIN weights from the fee detail report
    service_w: dict[str | None, Decimal] = defaultdict(lambda: ZERO)
    disposal_w: dict[str | None, Decimal] = defaultdict(lambda: ZERO)
    cross_month_disposal = ZERO
    for d in inp.fee_details:
        target = inp.gtin_to_item.get(d.gtin) if d.gtin else None
        if d.fee_type in DISPOSAL_FEE_TYPES:
            disposal_w[target] += abs(d.amount_usd)
            if month_start(d.transaction_date) != month:
                cross_month_disposal += d.amount_usd
        else:
            service_w[target] += abs(d.amount_usd)
    spread(SettlementKind.WFS_SERVICE, item_level[SettlementKind.WFS_SERVICE], dict(service_w))
    spread(SettlementKind.DISPOSAL_FEE, item_level[SettlementKind.DISPOSAL_FEE], dict(disposal_w))

    # storage fee: settlement amount, report gives the item share (§0.3 / §8.4)
    storage_total = item_level[SettlementKind.STORAGE_FEE]
    if storage_total:
        report = inp.storage_report
        if report is None:
            to_unassigned(
                "storage_no_report", "storage_fee", storage_total, SettlementKind.STORAGE_FEE
            )
        else:
            if report.is_latest_fallback:
                alerts.append(("STORAGE_REPORT_LATEST_PERIOD", report.period_start.isoformat()))
            sw: dict[str | None, Decimal] = defaultdict(lambda: ZERO)
            for s in report.shares:
                sw[s.item_id] += abs(s.amount_usd)
            spread(SettlementKind.STORAGE_FEE, storage_total, dict(sw))

    # review accelerator (§8.6)
    ra_total = item_level[SettlementKind.REVIEW_ACCELERATOR]
    if ra_total:
        rw = review_accelerator_weights(inp.review_accelerator, sales_by_item)
        if rw.weights is None:
            to_unassigned(
                "review_accelerator",
                rw.unassigned_reason or "unassigned",
                ra_total,
                SettlementKind.REVIEW_ACCELERATOR,
                reason=rw.unassigned_reason or "unassigned",
            )
        else:
            if rw.mode != "delta_price":
                alerts.append(("REVIEW_ACCELERATOR_BY_SALES", rw.mode))
            spread(SettlementKind.REVIEW_ACCELERATOR, ra_total, dict(rw.weights))

    # ---- inventory movements (§0.4)
    movements: list[MovementResult] = []
    for m in inp.movements:
        category = inventory_category(m.business_type)
        if category in ALERT_CATEGORIES:
            alerts.append((f"INVENTORY_{category.upper()}", m.business_type))
        item_id = None
        if m.gtin:
            item_id = inp.gtin_to_item.get(m.gtin)
        if item_id is None and m.msku:
            item_id = inp.msku_to_item.get(m.msku)
        mapping = "mapped" if m.store_id == store else "manual_assigned"
        goods_usd = to_usd(m.goods_value_cny, rate)
        movements.append(MovementResult(m, category, store, mapping, item_id, goods_usd))
        if category != "loss":
            continue
        if item_id is None:
            unassigned_key = unassigned_line_key(
                store, month, "inventory_unmapped_item", m.row_hash
            )
            unassigned[unassigned_key] = UnassignedResult(
                line_key=unassigned_key,
                store_id=store,
                source_kind="inventory_unmapped_item",
                source_ref=m.row_hash,
                reason="unassigned",
                amount_usd=goods_usd,
                amount_cny=m.goods_value_cny,
                detail={"business_type": m.business_type, "msku": m.msku, "gtin": m.gtin},
            )
            continue
        it = item(item_id)
        if goods_usd is not None:
            it.disposal_goods_usd += goods_usd

    # ---- manual adjustments on 待指定 rows (assign_item)
    for key, row in unassigned.items():
        adj = latest_adj.get(key)
        if adj is None or adj.kind != "assign_item":
            continue
        target = str(adj.payload.get("item_id") or "")
        if not target:
            continue
        row.status = "assigned"
        row.assigned_item_id = target
        row.adjustment_id = adj.id
        if row.settlement_kind in ITEM_COLUMN:
            # route through §8.5 again; if the item has no orders it stays on the item month
            kind = row.settlement_kind
            rows = orders_by_item.get(target, [])
            weights = (
                {r.line_key: max(r.amounts.get("sales_amount_usd"), ZERO) for r in rows}
                if kind in BY_SALES_KINDS
                else {r.line_key: max(r.quantity, ZERO) for r in rows}
            )
            item(target).amounts.add(ITEM_COLUMN[kind], row.amount_usd or ZERO)
            if rows and sum(weights.values(), ZERO) > 0:
                for lk, part in allocate(row.amount_usd or ZERO, weights).items():
                    orders[lk].amounts.add(ITEM_COLUMN[kind], part)
        elif row.settlement_kind in ORDER_KINDS:
            item(target).amounts.add(ORDER_COLUMN[row.settlement_kind], row.amount_usd or ZERO)
        elif row.settlement_kind is not None:
            # other settlement lines: kept on the item as WFS service-type fee
            item(target).amounts.add("wfs_service_fee_usd", row.amount_usd or ZERO)
        elif row.amount_usd is not None:
            item(target).disposal_goods_usd += row.amount_usd

    # ---- goods cost (§8.3) and order-line adjustments
    for row in orders.values():
        fifo = inp.fifo.get((row.platform_order_no, row.gtin or ""))
        if fifo is None:
            row.cost_match_status = "unmatched"
            row.reasons = ["missing_purchase", "missing_head"]
        else:
            row.purchase_cost_cny = fifo.purchase_cny
            row.head_cost_cny = fifo.head_cny
            row.other_cost_cny = fifo.other_cny
        for adj in sorted(adjustments_by_key.get(row.line_key, []), key=lambda a: a.acted_at):
            if adj.kind == "cost":
                if "purchase_cny" in adj.payload:
                    row.purchase_cost_cny = _to_decimal(adj.payload["purchase_cny"])
                if "head_cny" in adj.payload:
                    row.head_cost_cny = _to_decimal(adj.payload["head_cny"])
            elif adj.kind == "amount":
                # PRP §7: amount adjustments carry a USD delta on one order-level column
                column = str(adj.payload.get("column"))
                delta = _to_decimal(adj.payload.get("delta_usd"))
                if column in ORDER_COLUMN.values() and delta is not None:
                    row.amounts.add(column, delta)
                    item(row.item_id).amounts.add(column, delta)
        reasons = []
        if not row.purchase_cost_cny:
            reasons.append("missing_purchase")
        if not row.head_cost_cny:
            reasons.append("missing_head")
        if len(reasons) == 2 and fifo is None:
            row.cost_match_status = "unmatched"
        else:
            row.cost_match_status = "partial" if reasons else "matched"
        row.reasons = reasons
        cost_cny = (row.purchase_cost_cny or ZERO) + (row.head_cost_cny or ZERO)
        cost_cny += row.other_cost_cny or ZERO
        row.goods_cost_usd = to_usd(cost_cny, rate)
        it = item(row.item_id)
        it.purchase_cost_cny += row.purchase_cost_cny or ZERO
        it.head_cost_cny += row.head_cost_cny or ZERO
        it.goods_cost_usd = (
            None if rate is None else (it.goods_cost_usd or ZERO) + (row.goods_cost_usd or ZERO)
        )

    # ---- ads (§2.4): item month; → orders by quantity (not settlement money)
    for item_id, cost in inp.ad_cost_by_item.items():
        it = item(item_id)
        it.ad_cost_usd += cost
        rows = orders_by_item.get(item_id, [])
        weights = {r.line_key: max(r.quantity, ZERO) for r in rows}
        if rows and sum(weights.values(), ZERO) > 0:
            for lk, part in allocate(cost, weights).items():
                orders[lk].ad_cost_usd += part

    # ---- gross profit
    for row in orders.values():
        signed = sum((row.amounts.get(c) for c in SETTLEMENT_COLUMNS), ZERO)
        if row.goods_cost_usd is None:
            row.gross_profit_usd = None  # 汇率缺失: not treated as missing cost (§8.2)
        else:
            row.gross_profit_usd = q4(signed - row.goods_cost_usd - row.ad_cost_usd)
        row.gross_profit_cny = to_cny(row.gross_profit_usd, rate)
        row.owner_ref = inp.owner_by_item.get(row.item_id)
        times = inp.order_times.get((row.platform_order_no, row.order_item_no))
        if times is not None:
            row.ordered_at, row.shipped_at = times.ordered_at, times.shipped_at
            row.msku, row.serial_number = times.msku, times.serial_number
        if rate is None and "fx_missing" not in row.reasons:
            row.reasons.append("fx_missing")
    for it in items.values():
        signed = sum((it.amounts.get(c) for c in SETTLEMENT_COLUMNS), ZERO)
        if rate is None:
            it.gross_profit_usd = None
        else:
            # disposal fee is already inside ``signed``; goods value is extra loss
            it.gross_profit_usd = q4(
                signed - (it.goods_cost_usd or ZERO) - it.ad_cost_usd - it.disposal_goods_usd
            )
        it.gross_profit_cny = to_cny(it.gross_profit_usd, rate)

    # ---- review status for order rows
    for row in orders.values():
        row.review_status = review_status(
            row.line_key,
            row.reasons,
            latest_adj,
            latest_rev,
            revised=row.line_key in inp.adjustment_changed_at,
        )

    # ---- reconcile (§8.8)
    pending = [u for u in unassigned.values() if u.status == "pending"]
    pending_settlement = sum(
        (u.amount_usd or ZERO for u in pending if u.settlement_kind is not None), ZERO
    )
    # assigned 待指定 amounts are already inside the item months
    item_settlement = sum(
        (it.amounts.get(c) for it in items.values() for c in SETTLEMENT_COLUMNS), ZERO
    )
    order_level = item_settlement + pending_settlement
    diff = q4(settlement_total - order_level)
    ad_daily = sum(inp.ad_cost_by_item.values(), ZERO)
    head_cny = sum((r.head_cost_cny or ZERO for r in orders.values()), ZERO)
    head_usd = to_usd(head_cny, rate)
    if abs(diff) > RECONCILE_TOLERANCE_USD:
        status = "reconcile_failed"
    elif pending or month_has_unmapped_pending:
        status = "unassigned_pending"
    else:
        status = "ok"
    reconcile = ReconcileResult(
        settlement_total_usd=q4(settlement_total),
        order_level_total_usd=q4(order_level),
        unassigned_pending_usd=q4(pending_settlement),
        diff_usd=diff,
        ad_daily_vs_settlement_diff_usd=q4(ad_daily + ad_charges),
        inbound_freight_lx_vs_settlement_diff_usd=(
            None if head_usd is None else q4(head_usd + wpc_charges)
        ),
        cross_month_disposal_fee_usd=q4(cross_month_disposal),
        status=status,
    )

    blockers: list[str] = []
    if rate is None:
        blockers.append("FX_MISSING")
    if status == "reconcile_failed":
        blockers.append("RECONCILE_FAILED")
    if pending or month_has_unmapped_pending:
        blockers.append("UNASSIGNED_PENDING")

    return StoreMonthResult(
        store_id=store,
        bill_month=month,
        fx_rate=rate,
        fx_status=fx_status,
        order_lines=sorted(orders.values(), key=lambda r: r.line_key),
        items=items,
        unassigned=sorted(unassigned.values(), key=lambda u: u.line_key),
        movements=movements,
        reconcile=reconcile,
        other_income_usd=q4(other_income),
        alerts=alerts,
        blockers=blockers,
        ad_scope_note=inp.ad_scope_note,
    )


# ------------------------------------------------------------ unmapped store (§8.4)


def unmapped_store_rows(
    month: date,
    movements: list[FlowMovement],
    fx_rate: Decimal | None,
    adjustments: list[Adjustment],
) -> list[UnassignedResult]:
    """Loss movements without a store → 待指定 under ``__unmapped__``.

    Only loss-category rows affect profit, so only those become to-dos.  An active
    assign_store adjustment marks the row assigned; the loader then feeds the movement
    into that store's calculation (store_mapping_status = manual_assigned).
    """
    latest = {k: v for k, v in _latest(adjustments).items() if isinstance(v, Adjustment)}
    rows: list[UnassignedResult] = []
    for m in movements:
        if m.store_id is not None or inventory_category(m.business_type) != "loss":
            continue
        key = unassigned_line_key(UNMAPPED_STORE_ID, month, "inventory_unmapped_store", m.row_hash)
        row = UnassignedResult(
            line_key=key,
            store_id=UNMAPPED_STORE_ID,
            source_kind="inventory_unmapped_store",
            source_ref=m.row_hash,
            reason="unmapped_store",
            amount_usd=to_usd(m.goods_value_cny, fx_rate),
            amount_cny=m.goods_value_cny,
            detail={
                "store_code": m.store_code,
                "serial_number": m.serial_number,
                "msku": m.msku,
                "business_type": m.business_type,
            },
        )
        adj = latest.get(key)
        if adj is not None and adj.kind == "assign_store" and adj.payload.get("store_id"):
            row.status = "assigned"
            row.assigned_store_id = str(adj.payload["store_id"])
            row.adjustment_id = adj.id
        rows.append(row)
    return sorted(rows, key=lambda r: r.line_key)
