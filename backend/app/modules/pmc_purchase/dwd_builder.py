"""ODS → DWD transformation for the PMC purchase board (Gate 3, PR G3-B, part 1).

This module turns raw ODS rows (one row per document *per sync run*) into the
single current version of each document the DWD layer keeps:

* de-duplication — with update-time windows (decision D-PP-2026-09-21) the same
  document is delivered again whenever it changes, so the newest version wins,
  ordered by provider ``update_time`` and then by the ODS ``observed_at``;
* normalisation — Beijing dates, string store ids, ``ITEMID:`` remark parsing;
* exclusions — auxiliary / combo plans (§1.2) and deleted order lines never reach
  the board, but are counted in the report;
* merged purchase orders — one purchase-order line is split into one DWD line
  per plan it references (``plan_sn`` ∪ ``relation_purchase_plan``) by the plans'
  ``quantity_plan`` ratio (§5.2).

Everything here is pure: it takes ODS ORM instances (or anything with the same
attributes) and returns frozen dataclasses. Writing them into the ``dwd_*``
tables, ``gov_parse_jobs`` and ``gov_data_lineage`` is the second half of G3-B
and depends on the G3-A migration.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.pmc_purchase.calculations import (
    PlanShare,
    ReceiptEvent,
    allocate_by_plan_quantity,
    normalize_store_id,
    parse_itemid_remark,
    parse_provider_date,
)

DWD_BUILDER_VERSION = "pmc_purchase.dwd_builder.v1"


# --- input shapes (structural, so tests can use plain objects) ------------------------


class OdsRowLike(Protocol):
    id: UUID
    run_id: UUID
    raw_request_ref_id: UUID
    source_account_ref: str
    payload_json: Mapping[str, object]
    observed_at: datetime


class OdsPlanLike(OdsRowLike, Protocol):
    plan_sn: str
    status: int | None
    create_time: str | None
    expect_arrive_time: str | None
    sid: str | None
    sku: str | None
    product_name: str | None
    quantity_plan: int | None
    remark: str | None
    plan_remark: str | None
    is_aux: int | None
    is_combo: int | None


class OdsOrderLike(OdsRowLike, Protocol):
    order_sn: str
    status: int | None
    order_time: str | None
    create_time: str | None
    quantity_total: int | None
    quantity_receive: int | None
    quantity_real: int | None
    amount_total: Decimal | None
    purchase_currency: str | None
    purchase_rate: Decimal | None
    shipping_price: Decimal | None
    other_fee: Decimal | None


class OdsOrderItemLike(OdsRowLike, Protocol):
    order_sn: str
    item_id: str
    line_ordinal: int
    plan_sn: str | None
    sid: str | None
    sku: str | None
    product_name: str | None
    quantity_plan: int | None
    quantity_real: int | None
    quantity_receive: int | None
    price: Decimal | None
    amount: Decimal | None
    expect_arrive_time: str | None
    is_delete: int | None
    remark: str | None


class OdsReceiptLike(OdsRowLike, Protocol):
    order_sn: str
    business_order_sn: str | None
    status: int | None
    receive_time: str | None
    update_time: str | None


class OdsReceiptItemLike(OdsRowLike, Protocol):
    receipt_order_sn: str
    line_ordinal: int
    order_item_id: str | None
    sku: str | None
    product_receive_num: int | None


# --- output shapes ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where the chosen version of a document came from (for lineage)."""

    ods_id: UUID
    run_id: UUID
    raw_request_ref_id: UUID
    observed_at: datetime
    provider_update_time: str | None


@dataclass(frozen=True, slots=True)
class DwdPlanRow:
    source_account_ref: str
    plan_sn: str
    status: int | None
    create_date: date | None
    expect_arrive_date: date | None
    store_id: str | None
    store_attributed: bool
    sku: str | None
    product_name: str | None
    quantity_plan: int | None
    remark: str | None
    remark_item_id: str | None
    source: SourceRef


@dataclass(frozen=True, slots=True)
class DwdOrderRow:
    source_account_ref: str
    order_sn: str
    status: int | None
    order_date: date | None
    create_date: date | None
    quantity_total: int | None
    quantity_receive: int | None
    quantity_real: int | None
    amount_total: Decimal | None
    currency_code: str | None
    purchase_rate: Decimal | None
    shipping_price: Decimal | None
    other_fee: Decimal | None
    line_count: int
    source: SourceRef


@dataclass(frozen=True, slots=True)
class DwdOrderLineRow:
    """One purchase-order line × one plan (merged lines are split, §5.2)."""

    source_account_ref: str
    order_sn: str
    order_item_id: str
    line_ordinal: int
    plan_sn: str | None
    plan_count: int
    allocation_ratio: Decimal
    is_merged: bool
    store_id: str | None
    store_attributed: bool
    sku: str | None
    product_name: str | None
    quantity_plan: int | None
    quantity_real: int | None
    quantity_allocated: int
    amount_allocated: Decimal | None
    unit_price: Decimal | None
    expect_arrive_date: date | None
    remark_item_id: str | None
    plan_found: bool
    source: SourceRef


@dataclass(frozen=True, slots=True)
class ReceiptLineRow:
    """Deduplicated receipt line, keyed by purchase-order line id (in memory, for DWS)."""

    source_account_ref: str
    receipt_order_sn: str
    business_order_sn: str | None
    order_item_id: str
    receive_date: date | None
    quantity: int
    source: SourceRef


@dataclass(frozen=True, slots=True)
class DwdBuildReport:
    plans_seen: int = 0
    plans_kept: int = 0
    plans_excluded_aux_combo: int = 0
    plans_superseded: int = 0
    orders_seen: int = 0
    orders_kept: int = 0
    orders_superseded: int = 0
    lines_seen: int = 0
    lines_kept: int = 0
    lines_deleted: int = 0
    lines_superseded: int = 0
    lines_split_from_merged: int = 0
    lines_without_plan: int = 0
    lines_plan_missing: int = 0
    receipts_seen: int = 0
    receipts_kept: int = 0
    receipts_superseded: int = 0
    receipt_lines_kept: int = 0
    receipt_lines_unlinked: int = 0
    store_unattributed_lines: int = 0

    def as_message(self) -> str:
        return " ".join(f"{f.name}={getattr(self, f.name)}" for f in fields(self))


@dataclass(frozen=True, slots=True)
class DwdBuildResult:
    plans: list[DwdPlanRow]
    orders: list[DwdOrderRow]
    lines: list[DwdOrderLineRow]
    receipt_lines: list[ReceiptLineRow]
    report: DwdBuildReport
    builder_version: str = DWD_BUILDER_VERSION
    notes: list[str] = field(default_factory=list)


# --- de-duplication ---------------------------------------------------------------------


def _version_key(row: OdsRowLike) -> tuple[str, datetime, str]:
    """Newest provider ``update_time`` wins; ties resolved by ODS observation time.

    ``update_time`` is read from ``payload_json`` because not every ODS table
    extracted it as a column (plans do not). Missing values sort first, so a
    version that does carry an update time beats one that does not.
    """

    raw = row.payload_json.get("update_time") if row.payload_json else None
    update_time = str(raw).strip() if isinstance(raw, str | int) else ""
    return (update_time, row.observed_at, str(row.id))


def latest_versions[T: OdsRowLike](
    rows: Iterable[T], key: Callable[[T], object]
) -> tuple[dict[tuple[str, object], T], int]:
    """Keep the newest version per business key. Returns ``(chosen, superseded_count)``."""

    chosen: dict[tuple[str, object], T] = {}
    superseded = 0
    for row in rows:
        k = (row.source_account_ref, key(row))
        current = chosen.get(k)
        if current is None:
            chosen[k] = row
            continue
        superseded += 1
        if _version_key(row) > _version_key(current):
            chosen[k] = row
    return chosen, superseded


def _source(row: OdsRowLike) -> SourceRef:
    raw = row.payload_json.get("update_time") if row.payload_json else None
    return SourceRef(
        ods_id=row.id,
        run_id=row.run_id,
        raw_request_ref_id=row.raw_request_ref_id,
        observed_at=row.observed_at,
        provider_update_time=str(raw) if isinstance(raw, str | int) else None,
    )


# --- plans --------------------------------------------------------------------------------


def build_plans(ods_plans: Sequence[OdsPlanLike]) -> tuple[list[DwdPlanRow], dict[str, int]]:
    chosen, superseded = latest_versions(ods_plans, lambda r: r.plan_sn)
    rows: list[DwdPlanRow] = []
    excluded = 0
    for plan in sorted(chosen.values(), key=lambda p: (p.source_account_ref, p.plan_sn)):
        if plan.is_aux == 1 or plan.is_combo == 1:
            excluded += 1
            continue
        store_id = normalize_store_id(plan.sid)
        remark_item = parse_itemid_remark(plan.remark) or parse_itemid_remark(plan.plan_remark)
        rows.append(
            DwdPlanRow(
                source_account_ref=plan.source_account_ref,
                plan_sn=plan.plan_sn,
                status=plan.status,
                create_date=parse_provider_date(plan.create_time),
                expect_arrive_date=parse_provider_date(plan.expect_arrive_time),
                store_id=store_id,
                store_attributed=store_id is not None,
                sku=_clean(plan.sku),
                product_name=_clean(plan.product_name),
                quantity_plan=plan.quantity_plan,
                remark=_clean(plan.remark),
                remark_item_id=remark_item,
                source=_source(plan),
            )
        )
    return rows, {
        "seen": len(ods_plans),
        "kept": len(rows),
        "excluded": excluded,
        "superseded": superseded,
    }


# --- orders and lines ---------------------------------------------------------------------


def _line_plan_sns(item: OdsOrderItemLike) -> list[str]:
    """``plan_sn`` ∪ ``relation_purchase_plan`` (§5.2), order preserved, blanks dropped."""

    found: list[str] = []
    primary = _clean(item.plan_sn)
    if primary:
        found.append(primary)
    related = item.payload_json.get("relation_purchase_plan") if item.payload_json else None
    if isinstance(related, list):
        for entry in related:
            sn: object = entry
            if isinstance(entry, Mapping):
                sn = entry.get("plan_sn") or entry.get("sn")
            text = _clean(sn if isinstance(sn, str) else None)
            if text and text not in found:
                found.append(text)
    return found


def _line(
    item: OdsOrderItemLike,
    store_id: str | None,
    *,
    plan_sn: str | None,
    plan_count: int,
    ratio: Decimal,
    quantity: int,
    amount: Decimal | None,
    remark_item_id: str | None,
    plan_found: bool,
) -> DwdOrderLineRow:
    return DwdOrderLineRow(
        source_account_ref=item.source_account_ref,
        order_sn=item.order_sn,
        order_item_id=item.item_id,
        line_ordinal=item.line_ordinal,
        plan_sn=plan_sn,
        plan_count=plan_count,
        allocation_ratio=ratio,
        is_merged=plan_count > 1,
        store_id=store_id,
        store_attributed=store_id is not None,
        sku=_clean(item.sku),
        product_name=_clean(item.product_name),
        quantity_plan=item.quantity_plan,
        quantity_real=item.quantity_real,
        quantity_allocated=quantity,
        amount_allocated=amount,
        unit_price=item.price,
        expect_arrive_date=parse_provider_date(item.expect_arrive_time),
        remark_item_id=remark_item_id,
        plan_found=plan_found,
        source=_source(item),
    )


def build_orders(
    ods_orders: Sequence[OdsOrderLike],
    ods_items: Sequence[OdsOrderItemLike],
    plans_by_sn: Mapping[str, DwdPlanRow],
) -> tuple[list[DwdOrderRow], list[DwdOrderLineRow], dict[str, int]]:
    chosen_orders, orders_superseded = latest_versions(ods_orders, lambda r: r.order_sn)
    # Lines belong to the header version they were delivered with: keep the lines of
    # the chosen header's run only, so a shrunken item_list does not leave ghosts.
    chosen_runs = {k: o.run_id for k, o in chosen_orders.items()}
    same_version_items = [
        it for it in ods_items if chosen_runs.get((it.source_account_ref, it.order_sn)) == it.run_id
    ]
    chosen_items, items_superseded = latest_versions(
        same_version_items, lambda r: (r.order_sn, r.item_id)
    )
    items_superseded += len(ods_items) - len(same_version_items)

    lines: list[DwdOrderLineRow] = []
    counts: dict[str, int] = defaultdict(int)
    line_count_by_order: dict[tuple[str, str], int] = defaultdict(int)

    for item in sorted(
        chosen_items.values(), key=lambda i: (i.source_account_ref, i.order_sn, i.line_ordinal)
    ):
        if item.is_delete == 1:
            counts["deleted"] += 1
            continue
        store_id = normalize_store_id(item.sid)
        if store_id is None:
            counts["store_unattributed"] += 1
        plan_sns = _line_plan_sns(item)
        quantity = (
            item.quantity_real if item.quantity_real is not None else (item.quantity_plan or 0)
        )
        line_count_by_order[(item.source_account_ref, item.order_sn)] += 1

        if not plan_sns:
            counts["without_plan"] += 1
            lines.append(
                _line(
                    item,
                    store_id,
                    plan_sn=None,
                    plan_count=0,
                    ratio=Decimal("1.0000"),
                    quantity=quantity,
                    amount=item.amount,
                    remark_item_id=parse_itemid_remark(item.remark),
                    plan_found=False,
                )
            )
            continue

        shares = [
            PlanShare(sn, plans_by_sn[sn].quantity_plan if sn in plans_by_sn else None)
            for sn in plan_sns
        ]
        allocations = allocate_by_plan_quantity(quantity=quantity, amount=item.amount, plans=shares)
        merged = len(plan_sns) > 1
        if merged:
            counts["split"] += len(plan_sns)
        for allocation in allocations:
            plan = plans_by_sn.get(allocation.plan_sn)
            if plan is None:
                counts["plan_missing"] += 1
            lines.append(
                _line(
                    item,
                    store_id,
                    plan_sn=allocation.plan_sn,
                    plan_count=len(plan_sns),
                    ratio=allocation.ratio,
                    quantity=allocation.quantity,
                    amount=allocation.amount,
                    remark_item_id=(
                        plan.remark_item_id
                        if plan is not None
                        else parse_itemid_remark(item.remark)
                    ),
                    plan_found=plan is not None,
                )
            )

    orders: list[DwdOrderRow] = []
    for order in sorted(chosen_orders.values(), key=lambda o: (o.source_account_ref, o.order_sn)):
        orders.append(
            DwdOrderRow(
                source_account_ref=order.source_account_ref,
                order_sn=order.order_sn,
                status=order.status,
                order_date=parse_provider_date(order.order_time),
                create_date=parse_provider_date(order.create_time),
                quantity_total=order.quantity_total,
                quantity_receive=order.quantity_receive,
                quantity_real=order.quantity_real,
                amount_total=order.amount_total,
                currency_code=_clean(order.purchase_currency),
                purchase_rate=order.purchase_rate,
                shipping_price=order.shipping_price,
                other_fee=order.other_fee,
                line_count=line_count_by_order.get((order.source_account_ref, order.order_sn), 0),
                source=_source(order),
            )
        )

    return (
        orders,
        lines,
        {
            "orders_seen": len(ods_orders),
            "orders_kept": len(orders),
            "orders_superseded": orders_superseded,
            "lines_seen": len(ods_items),
            "lines_kept": len(lines),
            "lines_deleted": counts["deleted"],
            "lines_superseded": items_superseded,
            "lines_split_from_merged": counts["split"],
            "lines_without_plan": counts["without_plan"],
            "lines_plan_missing": counts["plan_missing"],
            "store_unattributed_lines": counts["store_unattributed"],
        },
    )


# --- receipts -------------------------------------------------------------------------------


def build_receipt_lines(
    ods_receipts: Sequence[OdsReceiptLike],
    ods_receipt_items: Sequence[OdsReceiptItemLike],
    known_order_item_ids: set[str] | None = None,
) -> tuple[list[ReceiptLineRow], dict[str, int]]:
    chosen, superseded = latest_versions(ods_receipts, lambda r: r.order_sn)
    chosen_runs = {k: r.run_id for k, r in chosen.items()}
    rows: list[ReceiptLineRow] = []
    unlinked = 0
    for item in sorted(
        ods_receipt_items, key=lambda r: (r.source_account_ref, r.receipt_order_sn, r.line_ordinal)
    ):
        key = (item.source_account_ref, item.receipt_order_sn)
        if chosen_runs.get(key) != item.run_id:
            continue
        receipt = chosen[key]
        order_item_id = _clean(item.order_item_id)
        if not order_item_id or (
            known_order_item_ids is not None and order_item_id not in known_order_item_ids
        ):
            unlinked += 1
            continue
        rows.append(
            ReceiptLineRow(
                source_account_ref=item.source_account_ref,
                receipt_order_sn=item.receipt_order_sn,
                business_order_sn=_clean(receipt.business_order_sn),
                order_item_id=order_item_id,
                receive_date=parse_provider_date(receipt.receive_time),
                quantity=max(item.product_receive_num or 0, 0),
                source=_source(item),
            )
        )
    return rows, {
        "seen": len(ods_receipts),
        "kept": len(chosen),
        "superseded": superseded,
        "lines_kept": len(rows),
        "lines_unlinked": unlinked,
    }


def receipt_events_by_order(
    receipt_lines: Iterable[ReceiptLineRow],
    lines: Iterable[DwdOrderLineRow],
) -> dict[tuple[str, str], list[ReceiptEvent]]:
    """Group receipt quantities per purchase order via ``order_item_id`` (§3.2)."""

    order_of_item: dict[tuple[str, str], str] = {}
    for line in lines:
        order_of_item[(line.source_account_ref, line.order_item_id)] = line.order_sn
    events: dict[tuple[str, str], list[ReceiptEvent]] = defaultdict(list)
    for rl in receipt_lines:
        order_sn = order_of_item.get((rl.source_account_ref, rl.order_item_id))
        if order_sn is None or rl.receive_date is None:
            continue
        events[(rl.source_account_ref, order_sn)].append(
            ReceiptEvent(rl.receive_date, rl.quantity, rl.receipt_order_sn)
        )
    return dict(events)


# --- orchestration --------------------------------------------------------------------------


def build_dwd(
    *,
    ods_plans: Sequence[OdsPlanLike],
    ods_orders: Sequence[OdsOrderLike],
    ods_items: Sequence[OdsOrderItemLike],
    ods_receipts: Sequence[OdsReceiptLike],
    ods_receipt_items: Sequence[OdsReceiptItemLike],
) -> DwdBuildResult:
    plans, plan_counts = build_plans(ods_plans)
    plans_by_sn = {p.plan_sn: p for p in plans}
    orders, lines, order_counts = build_orders(ods_orders, ods_items, plans_by_sn)
    receipt_lines, receipt_counts = build_receipt_lines(
        ods_receipts, ods_receipt_items, {ln.order_item_id for ln in lines}
    )
    report = DwdBuildReport(
        plans_seen=plan_counts["seen"],
        plans_kept=plan_counts["kept"],
        plans_excluded_aux_combo=plan_counts["excluded"],
        plans_superseded=plan_counts["superseded"],
        orders_seen=order_counts["orders_seen"],
        orders_kept=order_counts["orders_kept"],
        orders_superseded=order_counts["orders_superseded"],
        lines_seen=order_counts["lines_seen"],
        lines_kept=order_counts["lines_kept"],
        lines_deleted=order_counts["lines_deleted"],
        lines_superseded=order_counts["lines_superseded"],
        lines_split_from_merged=order_counts["lines_split_from_merged"],
        lines_without_plan=order_counts["lines_without_plan"],
        lines_plan_missing=order_counts["lines_plan_missing"],
        receipts_seen=receipt_counts["seen"],
        receipts_kept=receipt_counts["kept"],
        receipts_superseded=receipt_counts["superseded"],
        receipt_lines_kept=receipt_counts["lines_kept"],
        receipt_lines_unlinked=receipt_counts["lines_unlinked"],
        store_unattributed_lines=order_counts["store_unattributed_lines"],
    )
    return DwdBuildResult(
        plans=plans, orders=orders, lines=lines, receipt_lines=receipt_lines, report=report
    )


def _clean(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None
