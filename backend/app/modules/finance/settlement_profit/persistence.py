"""Write a calculated (store, month) to the PR-1 tables (PRP §8.1, §8.9).

- New calc_version only when the whole result hash changed (identical input → no write).
- Closed months are never rewritten: changed rows only go to
  ``fact_settlement_post_close_diffs`` (one open diff per line and content hash).
- Hashes exclude source_flow_id / source_run_ids and other technical fields; flow-sourced
  rows hash the flow ``row_hash`` plus business fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..settlement_profit_models import (
    InventoryMovementLine,
    InventoryMovementMonth,
    SettlementMonthClose,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementPostCloseDiff,
    SettlementProfitItemMonth,
    SettlementReconcileStoreMonth,
    SettlementUnassignedAmount,
)
from .engine import (
    SETTLEMENT_COLUMNS,
    ItemMonthResult,
    MovementResult,
    OrderLineResult,
    StoreMonthResult,
    UnassignedResult,
)
from .keys import UNMAPPED_STORE_ID, content_hash, reconcile_line_key, set_hash
from .money import ZERO, month_start

AMOUNT_COLUMNS = tuple(c for c in SETTLEMENT_COLUMNS if c != "disposal_fee_signed_usd")


@dataclass(frozen=True)
class PersistOutcome:
    store_id: str
    bill_month: date
    action: str  # written / unchanged / frozen
    calc_version: int
    post_close_diffs: int = 0


# ------------------------------------------------------------------ row payloads


def order_line_fields(row: OrderLineResult, result: StoreMonthResult) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "line_key": row.line_key,
        "store_id": result.store_id,
        "bill_month": result.bill_month,
        "report_key": row.report_key,
        "platform_order_no": row.platform_order_no,
        "order_item_no": row.order_item_no,
        "item_id": row.item_id,
        "gtin": row.gtin,
        "msku": row.msku,
        "owner_ref": row.owner_ref,
        "serial_number": row.serial_number,
        "quantity": row.quantity,
        "ordered_at": row.ordered_at,
        "shipped_at": row.shipped_at,
        "settled_at": row.settled_at,
        "cost_match_status": row.cost_match_status,
        "review_status": row.review_status,
        "reasons": list(row.reasons),
        "purchase_cost_cny": row.purchase_cost_cny,
        "head_cost_cny": row.head_cost_cny,
        "goods_cost_usd": row.goods_cost_usd,
        "ad_cost_usd": row.ad_cost_usd,
        "disposal_loss_usd": -row.amounts.get("disposal_fee_signed_usd"),
        "gross_profit_usd": row.gross_profit_usd,
        "gross_profit_cny": row.gross_profit_cny,
        "net_profit_share_cny": row.net_profit_share_cny,
        "fx_rate": result.fx_rate,
        "fx_month": result.bill_month if result.fx_rate is not None else None,
        "fx_status": result.fx_status,
    }
    for column in AMOUNT_COLUMNS:
        fields[column] = row.amounts.get(column)
    return fields


def movement_fields(m: MovementResult, result: StoreMonthResult) -> dict[str, Any]:
    mv = m.movement
    return {
        "source_row_hash": mv.row_hash,  # flow row hash, not the flow id (§8.1)
        "store_code": mv.store_code,
        "store_id": m.store_id,
        "store_mapping_status": m.store_mapping_status,
        "serial_number": mv.serial_number,
        "business_type": mv.business_type,
        "gtin": mv.gtin,
        "item_id": m.item_id,
        "category": m.category,
        "movement_month": month_start(mv.occurred_at.date()),
        "occurred_at": mv.occurred_at,
        "quantity": mv.quantity,
        "goods_value_cny": mv.goods_value_cny,
        "goods_value_usd": m.goods_value_usd,
        "destination": mv.destination,
        "fx_rate": result.fx_rate,
        "fx_status": result.fx_status,
    }


def unassigned_fields(u: UnassignedResult) -> dict[str, Any]:
    return {
        "line_key": u.line_key,
        "store_id": u.store_id,
        "source_kind": u.source_kind,
        "source_ref": u.source_ref,
        "reason": u.reason,
        "amount_usd": u.amount_usd,
        "amount_cny": u.amount_cny,
        "status": u.status,
        "assigned_item_id": u.assigned_item_id,
        "assigned_store_id": u.assigned_store_id,
        "detail": u.detail,
    }


def item_fields(it: ItemMonthResult, result: StoreMonthResult) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "store_id": result.store_id,
        "item_id": it.item_id,
        "bill_month": result.bill_month,
        "owner_ref": it.owner_ref,
        "msku": it.msku,
        "sales_quantity": it.sales_quantity,
        "purchase_cost_cny": it.purchase_cost_cny,
        "head_cost_cny": it.head_cost_cny,
        "goods_cost_usd": it.goods_cost_usd,
        "ad_cost_usd": it.ad_cost_usd,
        "disposal_loss_usd": it.disposal_loss_usd,
        "gross_profit_usd": it.gross_profit_usd,
        "gross_profit_cny": it.gross_profit_cny,
        "net_profit_share_cny": it.net_profit_share_cny,
        "net_profit_cny": it.net_profit_cny,
        "ad_scope_note": result.ad_scope_note,
        "fx_rate": result.fx_rate,
        "fx_month": result.bill_month if result.fx_rate is not None else None,
        "fx_status": result.fx_status,
    }
    for column in AMOUNT_COLUMNS:
        fields[column] = it.amounts.get(column)
    sales = it.amounts.get("sales_amount_usd")
    fields["gross_margin_ratio"] = (
        (it.gross_profit_usd / sales).quantize(Decimal("0.00000001"))
        if it.gross_profit_usd is not None and sales
        else None
    )
    return fields


def reconcile_fields(result: StoreMonthResult) -> dict[str, Any]:
    r = result.reconcile
    return {
        "settlement_total_usd": r.settlement_total_usd,
        "order_level_total_usd": r.order_level_total_usd,
        "unassigned_pending_usd": r.unassigned_pending_usd,
        "diff_usd": r.diff_usd,
        "ad_daily_vs_settlement_diff_usd": r.ad_daily_vs_settlement_diff_usd,
        "inbound_freight_lx_vs_settlement_diff_usd": r.inbound_freight_lx_vs_settlement_diff_usd,
        "cross_month_disposal_fee_usd": r.cross_month_disposal_fee_usd,
        "status": r.status,
        "fx_status": result.fx_status,
    }


def result_hash(result: StoreMonthResult) -> tuple[str, dict[str, str]]:
    """(whole-result hash, line_key → row hash for order and movement rows)."""
    rows: dict[str, str] = {}
    for row in result.order_lines:
        rows[row.line_key] = content_hash(order_line_fields(row, result))
    for m in result.movements:
        rows[f"movement|{m.movement.row_hash}"] = content_hash(movement_fields(m, result))
    extra = [content_hash(unassigned_fields(u)) for u in result.unassigned]
    extra += [content_hash(item_fields(it, result)) for it in result.items.values()]
    extra.append(content_hash(reconcile_fields(result)))
    return set_hash([*rows.values(), *extra]), rows


# ------------------------------------------------------------------ queries


def is_month_closed(session: Session, store_id: str, bill_month: date) -> int | None:
    """Frozen calc_version when the store-month (or ALL) is closed, else None."""
    row = session.execute(
        select(SettlementMonthClose.frozen_calc_version)
        .where(
            SettlementMonthClose.bill_month == bill_month,
            SettlementMonthClose.store_scope.in_((store_id, "ALL")),
            SettlementMonthClose.status == "closed",
        )
        .order_by(SettlementMonthClose.frozen_calc_version.desc().nulls_last())
        .limit(1)
    ).first()
    return None if row is None else int(row[0] or 0)


def _current_reconcile(
    session: Session, store_id: str, bill_month: date
) -> SettlementReconcileStoreMonth | None:
    return session.execute(
        select(SettlementReconcileStoreMonth).where(
            SettlementReconcileStoreMonth.store_id == store_id,
            SettlementReconcileStoreMonth.bill_month == bill_month,
        )
    ).scalar_one_or_none()


def _max_order_version(session: Session, store_id: str, bill_month: date) -> int:
    value = session.execute(
        select(func.max(SettlementOrderLine.calc_version)).where(
            SettlementOrderLine.store_id == store_id,
            SettlementOrderLine.bill_month == bill_month,
        )
    ).scalar()
    return int(value or 0)


# ------------------------------------------------------------------ writers


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _write_post_close_diffs(
    session: Session,
    result: StoreMonthResult,
    frozen_version: int,
    new_rows: dict[str, str],
    now: datetime,
) -> int:
    store, month = result.store_id, result.bill_month
    frozen = {
        r.line_key: r
        for r in session.execute(
            select(SettlementOrderLine).where(
                SettlementOrderLine.store_id == store,
                SettlementOrderLine.bill_month == month,
                SettlementOrderLine.calc_version == frozen_version,
            )
        ).scalars()
    }
    frozen_hashes = {k: r.content_hash for k, r in frozen.items()}
    for mv in session.execute(
        select(InventoryMovementLine).where(
            InventoryMovementLine.store_id == store,
            InventoryMovementLine.movement_month == month,
            InventoryMovementLine.calc_version == frozen_version,
        )
    ).scalars():
        frozen_hashes[f"movement|{mv.source_row_hash}"] = mv.content_hash
    new_by_key = {r.line_key: r for r in result.order_lines}
    open_diffs = {
        (d.line_key, d.new_value.get("content_hash"))
        for d in session.execute(
            select(SettlementPostCloseDiff).where(
                SettlementPostCloseDiff.store_id == store,
                SettlementPostCloseDiff.bill_month == month,
                SettlementPostCloseDiff.status == "open",
            )
        ).scalars()
    }
    written = 0
    for key in sorted(set(frozen_hashes) | set(new_rows)):
        old_hash, new_hash = frozen_hashes.get(key), new_rows.get(key)
        if old_hash == new_hash or (key, new_hash) in open_diffs:
            continue
        old_row = frozen.get(key)
        new_row = new_by_key.get(key)
        old_amount = old_row.gross_profit_usd if old_row is not None else None
        new_amount = new_row.gross_profit_usd if new_row is not None else None
        session.add(
            SettlementPostCloseDiff(
                store_id=store,
                bill_month=month,
                line_key=key,
                detected_at=now,
                old_value={"content_hash": old_hash, "gross_profit_usd": _jsonable(old_amount)},
                new_value={
                    "content_hash": new_hash,
                    "row": _jsonable(order_line_fields(new_row, result)) if new_row else None,
                },
                diff_amount_usd=(
                    (new_amount or ZERO) - (old_amount or ZERO)
                    if old_amount is not None or new_amount is not None
                    else None
                ),
                frozen_calc_version=frozen_version,
            )
        )
        written += 1
    return written


def upsert_unassigned(
    session: Session, store_id: str, bill_month: date, rows: list[UnassignedResult], version: int
) -> None:
    existing = {
        u.line_key: u
        for u in session.execute(
            select(SettlementUnassignedAmount).where(
                SettlementUnassignedAmount.store_id == store_id,
                SettlementUnassignedAmount.bill_month == bill_month,
            )
        ).scalars()
    }
    seen: set[str] = set()
    for u in rows:
        seen.add(u.line_key)
        values = unassigned_fields(u)
        values.pop("line_key")
        values["adjustment_id"] = UUID(u.adjustment_id) if u.adjustment_id else None
        values["calc_version"] = version
        current = existing.get(u.line_key)
        if current is None:
            session.add(
                SettlementUnassignedAmount(line_key=u.line_key, bill_month=bill_month, **values)
            )
        else:
            for k, v in values.items():
                setattr(current, k, v)
    # source disappeared (e.g. flow row_hash changed): the old 待指定 and its assignment void
    for key, current in existing.items():
        if key not in seen and current.status != "void":
            current.status = "void"
            current.calc_version = version


def _upsert_review_rows(
    session: Session,
    store_id: str,
    bill_month: date,
    rows: list[dict[str, Any]],
    version: int,
) -> None:
    existing = {
        r.line_key: r
        for r in session.execute(
            select(SettlementOrderReview).where(
                SettlementOrderReview.store_id == store_id,
                SettlementOrderReview.bill_month == bill_month,
            )
        ).scalars()
    }
    seen: set[str] = set()
    for values in rows:
        key = values["line_key"]
        seen.add(key)
        current = existing.get(key)
        if current is None:
            session.add(
                SettlementOrderReview(
                    store_id=store_id, bill_month=bill_month, calc_version=version, **values
                )
            )
            continue
        changed = any(getattr(current, k) != v for k, v in values.items())
        for k, v in values.items():
            setattr(current, k, v)
        current.calc_version = version
        if changed:
            current.version += 1  # optimistic lock (§8.9)
    for key, current in existing.items():
        if key not in seen:
            session.delete(current)


def _review_rows(result: StoreMonthResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in result.order_lines:
        rows.append(
            {
                "line_key": r.line_key,
                "row_kind": "order",
                "platform_order_no": r.platform_order_no,
                "order_item_no": r.order_item_no,
                "item_id": r.item_id,
                "owner_ref": r.owner_ref,
                "status": r.review_status,
                "reasons": list(r.reasons),
                "amount_usd": r.amounts.get("sales_amount_usd"),
                "profit_usd": r.gross_profit_usd,
            }
        )
    rows.extend(unassigned_review_rows(result.unassigned))
    if result.reconcile.status == "reconcile_failed":
        rows.append(
            {
                "line_key": reconcile_line_key(result.store_id, result.bill_month),
                "row_kind": "reconcile_diff",
                "platform_order_no": None,
                "order_item_no": None,
                "item_id": None,
                "owner_ref": None,
                "status": "pending",
                "reasons": ["reconcile_diff"],
                "amount_usd": result.reconcile.diff_usd,
                "profit_usd": None,
            }
        )
    return rows


def unassigned_review_rows(rows: list[UnassignedResult]) -> list[dict[str, Any]]:
    return [
        {
            "line_key": u.line_key,
            "row_kind": "unassigned",
            "platform_order_no": None,
            "order_item_no": None,
            "item_id": u.assigned_item_id,
            "owner_ref": None,
            "status": "pending" if u.status == "pending" else "adjusted",
            "reasons": [u.reason],
            "amount_usd": u.amount_usd,
            "profit_usd": None,
        }
        for u in rows
        if u.status != "void"
    ]


def persist_store_month(
    session: Session, result: StoreMonthResult, *, now: datetime
) -> PersistOutcome:
    store, month = result.store_id, result.bill_month
    whole_hash, row_hashes = result_hash(result)

    frozen_version = is_month_closed(session, store, month)
    if frozen_version is not None:
        diffs = _write_post_close_diffs(session, result, frozen_version, row_hashes, now)
        return PersistOutcome(store, month, "frozen", frozen_version, diffs)

    reconcile = _current_reconcile(session, store, month)
    if reconcile is not None and reconcile.result_hash == whole_hash:
        return PersistOutcome(store, month, "unchanged", reconcile.calc_version)
    version = (
        max(_max_order_version(session, store, month), reconcile.calc_version if reconcile else 0)
        + 1
    )

    for row in result.order_lines:
        session.add(
            SettlementOrderLine(
                **order_line_fields(row, result),
                calc_version=version,
                content_hash=row_hashes[row.line_key],
                source_run_ids=[],
            )
        )
    for m in result.movements:
        fields = movement_fields(m, result)
        session.add(
            InventoryMovementLine(
                **fields,
                source_flow_id=UUID(m.movement.flow_id),
                source_sync_batch_id=(
                    UUID(m.movement.sync_batch_id) if m.movement.sync_batch_id else None
                ),
                owner_ref=None,
                calc_version=version,
                content_hash=row_hashes[f"movement|{m.movement.row_hash}"],
            )
        )

    upsert_unassigned(session, store, month, result.unassigned, version)

    session.execute(
        delete(SettlementProfitItemMonth).where(
            SettlementProfitItemMonth.store_id == store,
            SettlementProfitItemMonth.bill_month == month,
        )
    )
    for it in result.items.values():
        session.add(SettlementProfitItemMonth(**item_fields(it, result), calc_version=version))

    session.execute(
        delete(InventoryMovementMonth).where(
            InventoryMovementMonth.store_id == store, InventoryMovementMonth.month == month
        )
    )
    buckets: dict[tuple[str, str], dict[str, Decimal | None]] = {}
    for m in result.movements:
        if m.item_id is None:
            continue
        b = buckets.setdefault(
            (m.item_id, m.category), {"quantity": ZERO, "cny": ZERO, "usd": ZERO}
        )
        b["quantity"] = (b["quantity"] or ZERO) + m.movement.quantity
        b["cny"] = (
            None
            if b["cny"] is None or m.movement.goods_value_cny is None
            else (b["cny"] + m.movement.goods_value_cny)
        )
        b["usd"] = (
            None
            if b["usd"] is None or m.goods_value_usd is None
            else (b["usd"] + m.goods_value_usd)
        )
    for (item_id, category), b in sorted(buckets.items()):
        session.add(
            InventoryMovementMonth(
                store_id=store,
                item_id=item_id,
                month=month,
                category=category,
                quantity=b["quantity"],
                goods_value_cny=b["cny"],
                goods_value_usd=b["usd"],
                calc_version=version,
            )
        )

    _upsert_review_rows(session, store, month, _review_rows(result), version)

    values = reconcile_fields(result)
    if reconcile is None:
        session.add(
            SettlementReconcileStoreMonth(
                store_id=store,
                bill_month=month,
                calc_version=version,
                result_hash=whole_hash,
                **values,
            )
        )
    else:
        for k, v in values.items():
            setattr(reconcile, k, v)
        reconcile.calc_version = version
        reconcile.result_hash = whole_hash
    session.flush()
    return PersistOutcome(store, month, "written", version)


def persist_unmapped(
    session: Session, bill_month: date, rows: list[UnassignedResult], version: int
) -> None:
    """待指定 rows for unmapped-store inventory movements (store ``__unmapped__``)."""
    upsert_unassigned(session, UNMAPPED_STORE_ID, bill_month, rows, version)
    _upsert_review_rows(
        session, UNMAPPED_STORE_ID, bill_month, unassigned_review_rows(rows), version
    )
    session.flush()
