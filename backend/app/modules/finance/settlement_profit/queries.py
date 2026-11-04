"""Read side of the settlement profit API (PRP §7). All filters go through SettlementAccess."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode

from ..settlement_profit_models import (
    InventoryMovementLine,
    InventoryMovementMonth,
    NetProfitAllocationConfig,
    SettlementOrderAdjustment,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementProfitItemMonth,
    SettlementReconcileStoreMonth,
)
from .access import UNMAPPED_STORE_LABEL, SettlementAccess
from .keys import UNMAPPED_STORE_ID
from .money import ZERO, q4

SOURCE = "finance_settlement_profit_v2"
MAX_PAGE_SIZE = 200

REVENUE = ("sales_amount_usd", "platform_subsidy_usd", "refund_amount_usd")
ORDER_FEES = ("commission_usd", "wfs_fulfillment_fee_usd", "return_fee_usd", "tax_withheld_usd")
ITEM_FEES = ("wfs_service_fee_usd", "storage_fee_usd", "review_accelerator_usd")
COST_COLUMNS = ("purchase_cost_cny", "head_cost_cny", "goods_cost_usd")


def money(value: Decimal | None, currency: str) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": format(q4(Decimal(value)), "f"), "currency_code": currency}


def parse_month(value: str) -> date:
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, TypeError):
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details={"month": "expected YYYY-MM"},
        ) from None


def parse_months(values: list[str] | None) -> list[date]:
    return sorted({parse_month(v) for v in values or []})


@dataclass(frozen=True)
class Page:
    page: int
    page_size: int

    @classmethod
    def of(cls, page: int, page_size: int) -> Page:
        if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                details={"page_size": f"1..{MAX_PAGE_SIZE}", "page": ">= 1"},
            )
        return cls(page, page_size)

    def slice(self, rows: list[Any]) -> list[Any]:
        start = (self.page - 1) * self.page_size
        return rows[start : start + self.page_size]


def meta(
    tables: list[str], total: int, calc_version: int | None, data_as_of: datetime | None
) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "source_tables": tables,
        "calc_version": calc_version,
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "total": total,
    }


def store_label(store_id: str) -> str:
    return UNMAPPED_STORE_LABEL if store_id == UNMAPPED_STORE_ID else store_id


def _scope_stores(stmt: Select[Any], column: Any, access: SettlementAccess, stores) -> Select[Any]:
    """Restrict to visible stores; ``__unmapped__`` never matches a store filter."""
    if stores is not None:
        return stmt.where(column.in_(stores))
    if access.sees_unmapped:
        return stmt
    return stmt.where(column != UNMAPPED_STORE_ID)


def _scope_owner(stmt: Select[Any], column: Any, access: SettlementAccess) -> Select[Any]:
    if access.owner_ids is None:
        return stmt
    return stmt.where(column.in_(sorted(access.owner_ids)))


# ------------------------------------------------------------------ stores (filter options)


def list_stores(session: Session, access: SettlementAccess, months: list[date]) -> list[dict]:
    stmt = select(SettlementReconcileStoreMonth.store_id).distinct()
    if months:
        stmt = stmt.where(SettlementReconcileStoreMonth.bill_month.in_(months))
    stmt = stmt.where(SettlementReconcileStoreMonth.store_id != UNMAPPED_STORE_ID)
    if not access.all_stores:
        stmt = stmt.where(SettlementReconcileStoreMonth.store_id.in_(sorted(access.store_ids)))
    if access.owner_ids is not None:
        owned = select(SettlementProfitItemMonth.store_id).where(
            SettlementProfitItemMonth.owner_ref.in_(sorted(access.owner_ids))
        )
        stmt = stmt.where(SettlementReconcileStoreMonth.store_id.in_(owned))
    return [{"store_id": s, "label": s} for s in session.execute(stmt).scalars()]


# ------------------------------------------------------------------ summary / item


def _item_rows(
    session: Session,
    access: SettlementAccess,
    months: list[date],
    stores: list[str] | None,
    owner_ids: list[str] | None,
) -> list[SettlementProfitItemMonth]:
    stmt = select(SettlementProfitItemMonth).where(
        SettlementProfitItemMonth.store_id != UNMAPPED_STORE_ID
    )
    if months:
        stmt = stmt.where(SettlementProfitItemMonth.bill_month.in_(months))
    if stores is not None:
        stmt = stmt.where(SettlementProfitItemMonth.store_id.in_(stores))
    if owner_ids:
        stmt = stmt.where(SettlementProfitItemMonth.owner_ref.in_(owner_ids))
    stmt = _scope_owner(stmt, SettlementProfitItemMonth.owner_ref, access)
    return list(session.execute(stmt).scalars())


def _convert(value: Decimal | None, row: SettlementProfitItemMonth, currency: str):
    if value is None:
        return None
    if currency == "USD":
        return Decimal(value)
    return None if row.fx_rate is None else Decimal(value) * Decimal(row.fx_rate)


def _groups(row: SettlementProfitItemMonth, currency: str, access: SettlementAccess) -> dict:
    def total(cols: tuple[str, ...]) -> Decimal | None:
        parts = [_convert(getattr(row, c), row, currency) for c in cols]
        return None if any(p is None for p in parts) else sum(parts, ZERO)

    groups: dict[str, Decimal | None] = {
        "sales": _convert(row.sales_amount_usd, row, currency),
        "revenue": total(REVENUE),
        "order_fees": total(ORDER_FEES),
        "item_fees": total(ITEM_FEES),
        "ad_cost": _convert(row.ad_cost_usd, row, currency),
        "disposal_loss": _convert(row.disposal_loss_usd, row, currency),
        "gross_profit": (
            _convert(row.gross_profit_usd, row, currency)
            if currency == "USD"
            else (None if row.gross_profit_cny is None else Decimal(row.gross_profit_cny))
        ),
    }
    if access.can_see_cost:
        groups["goods_cost"] = _convert(row.goods_cost_usd, row, currency)
    return groups


def summary(
    session: Session,
    access: SettlementAccess,
    *,
    months: list[date],
    stores: list[str] | None,
    owner_ids: list[str] | None,
    view: str,
    currency: str,
    page: Page,
    sort_by: str | None,
    sort_order: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _item_rows(session, access, months, stores, owner_ids)
    buckets: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in rows:
        key = {
            "item": (r.store_id, r.item_id),
            "store": (r.store_id,),
            "owner": (r.owner_ref or "",),
        }[view]
        b = buckets.setdefault(
            key,
            {
                "values": defaultdict(lambda: ZERO),
                "missing": set(),
                "net": ZERO,
                "net_missing": False,
            },
        )
        for name, value in _groups(r, currency, access).items():
            if value is None:
                b["missing"].add(name)
            else:
                b["values"][name] += value
        if r.net_profit_cny is None:
            b["net_missing"] = True
        else:
            b["net"] += Decimal(r.net_profit_cny)

    out: list[dict[str, Any]] = []
    for key, b in buckets.items():
        values = {k: (None if k in b["missing"] else v) for k, v in b["values"].items()}
        for k in b["missing"]:
            values.setdefault(k, None)
        sales, gross = values.get("sales"), values.get("gross_profit")
        row: dict[str, Any] = {
            "key": dict(
                zip(
                    {
                        "item": ("store_id", "item_id"),
                        "store": ("store_id",),
                        "owner": ("owner_ref",),
                    }[view],
                    key,
                    strict=True,
                )
            ),
            **{k: money(v, currency) for k, v in sorted(values.items())},
            "margin": (
                format((gross / sales).quantize(Decimal("0.0001")), "f")
                if gross is not None and sales
                else None
            ),
        }
        if access.can_see_net_profit:
            row["net_profit"] = None if b["net_missing"] else money(b["net"], "CNY")
        out.append(row)
    sort_key = sort_by or "gross_profit"
    allowed = {"sales", "gross_profit", "margin", "ad_cost", "revenue"}
    if sort_key not in allowed:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR, status_code=422, details={"sort_by": sorted(allowed)}
        )

    def sort_value(r: dict[str, Any]) -> Decimal:
        v = r.get(sort_key)
        if isinstance(v, dict):
            return Decimal(v["amount"])
        return Decimal(v) if v is not None else Decimal("-1e30")

    out.sort(key=sort_value, reverse=sort_order == "desc")
    totals: dict[str, Any] = {}
    for name in (
        "sales",
        "revenue",
        "order_fees",
        "item_fees",
        "ad_cost",
        "disposal_loss",
        "gross_profit",
        *(["goods_cost"] if access.can_see_cost else []),
    ):
        vals = [r.get(name) for r in out]
        totals[name] = (
            None
            if any(v is None for v in vals)
            else money(sum((Decimal(v["amount"]) for v in vals), ZERO), currency)
        )
    version = max((r.calc_version for r in rows), default=None)
    as_of = max((r.updated_at for r in rows), default=None)
    return (
        {"rows": page.slice(out), "totals": totals, "view": view, "currency": currency},
        meta(["mart_settlement_profit_item_month"], len(out), version, as_of),
    )


WATERFALL = (
    ("revenue", REVENUE),
    ("order_fees", ORDER_FEES),
    ("item_fees", ITEM_FEES),
    ("ad_cost", ("ad_cost_usd",)),
    ("disposal_loss", ("disposal_loss_usd",)),
)


def item_detail(
    session: Session, access: SettlementAccess, store_id: str, item_id: str, months: list[date]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if store_id == UNMAPPED_STORE_ID or not access.store_visible(store_id):
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    stmt = select(SettlementProfitItemMonth).where(
        SettlementProfitItemMonth.store_id == store_id,
        SettlementProfitItemMonth.item_id == item_id,
    )
    if months:
        stmt = stmt.where(SettlementProfitItemMonth.bill_month.in_(months))
    rows = [
        r
        for r in session.execute(stmt.order_by(SettlementProfitItemMonth.bill_month)).scalars()
        if access.owner_visible(r.owner_ref)
    ]
    if not rows:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    out = []
    for r in rows:
        groups = []
        for name, cols in WATERFALL:
            groups.append(
                {
                    "group": name,
                    "columns": [{"column": c, "value": money(getattr(r, c), "USD")} for c in cols],
                }
            )
        if access.can_see_cost:
            groups.append(
                {
                    "group": "goods_cost",
                    "columns": [
                        {"column": "purchase_cost_cny", "value": money(r.purchase_cost_cny, "CNY")},
                        {"column": "head_cost_cny", "value": money(r.head_cost_cny, "CNY")},
                        {"column": "goods_cost_usd", "value": money(r.goods_cost_usd, "USD")},
                    ],
                }
            )
        month: dict[str, Any] = {
            "month": r.bill_month.strftime("%Y-%m"),
            "owner_ref": r.owner_ref,
            "fx_status": r.fx_status,
            "groups": groups,
            "gross_profit": money(r.gross_profit_usd, "USD"),
            "gross_profit_cny": money(r.gross_profit_cny, "CNY"),
            "ad_scope_note": r.ad_scope_note,
        }
        if access.can_see_net_profit:
            month["net_profit"] = money(r.net_profit_cny, "CNY")
        out.append(month)
    return (
        {"store_id": store_id, "item_id": item_id, "months": out},
        meta(
            ["mart_settlement_profit_item_month"],
            len(out),
            max(r.calc_version for r in rows),
            max(r.updated_at for r in rows),
        ),
    )


# ------------------------------------------------------------------ orders (订单审核)

ORDER_SORT = {
    "bill_month": SettlementOrderReview.bill_month,
    "store_id": SettlementOrderReview.store_id,
    "platform_order_no": SettlementOrderReview.platform_order_no,
    "status": SettlementOrderReview.status,
    "amount": SettlementOrderReview.amount_usd,
    "profit": SettlementOrderReview.profit_usd,
}


def orders(
    session: Session,
    access: SettlementAccess,
    *,
    months: list[date],
    stores: list[str] | None,
    owner_ids: list[str] | None,
    status: list[str] | None,
    reason: list[str] | None,
    keyword: str | None,
    page: Page,
    sort_by: str | None,
    sort_order: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stmt = select(SettlementOrderReview, SettlementOrderLine).outerjoin(
        SettlementOrderLine,
        and_(
            SettlementOrderLine.line_key == SettlementOrderReview.line_key,
            SettlementOrderLine.store_id == SettlementOrderReview.store_id,
            SettlementOrderLine.bill_month == SettlementOrderReview.bill_month,
            SettlementOrderLine.calc_version == SettlementOrderReview.calc_version,
        ),
    )
    if months:
        stmt = stmt.where(SettlementOrderReview.bill_month.in_(months))
    stmt = _scope_stores(stmt, SettlementOrderReview.store_id, access, stores)
    if owner_ids:
        stmt = stmt.where(SettlementOrderReview.owner_ref.in_(owner_ids))
    stmt = _scope_owner(stmt, SettlementOrderReview.owner_ref, access)
    if status:
        stmt = stmt.where(SettlementOrderReview.status.in_(status))
    if reason:
        stmt = stmt.where(or_(*[SettlementOrderReview.reasons.contains([r]) for r in reason]))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                SettlementOrderReview.platform_order_no.ilike(like),
                SettlementOrderReview.item_id.ilike(like),
                SettlementOrderReview.line_key.ilike(like),
            )
        )
    if sort_by is not None and sort_by not in ORDER_SORT:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details={"sort_by": sorted(ORDER_SORT)},
        )
    column = ORDER_SORT[sort_by or "bill_month"]
    order = column.desc() if sort_order == "desc" else column.asc()
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    page_rows = session.execute(
        stmt.order_by(order, SettlementOrderReview.line_key)
        .offset((page.page - 1) * page.page_size)
        .limit(page.page_size)
    ).all()
    out = [order_row(review, line, access) for review, line in page_rows]
    version = max((r.calc_version for r, _ in page_rows), default=None)
    as_of = max((r.updated_at for r, _ in page_rows), default=None)
    return (
        {"rows": out},
        meta(
            ["mart_settlement_order_review", "fact_settlement_order_lines"], total, version, as_of
        ),
    )


def order_row(
    review: SettlementOrderReview, line: SettlementOrderLine | None, access: SettlementAccess
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "line_id": str(review.id),
        "line_key": review.line_key,
        "row_kind": review.row_kind,
        "month": review.bill_month.strftime("%Y-%m"),
        "store_id": review.store_id,
        "store_label": store_label(review.store_id),
        "platform_order_no": review.platform_order_no,
        "order_item_no": review.order_item_no,
        "item_id": review.item_id,
        "owner_ref": review.owner_ref,
        "status": review.status,
        "reasons": list(review.reasons),
        "amount": money(review.amount_usd, "USD"),
        "profit": money(review.profit_usd, "USD"),
        "version": review.version,
        "first_reviewed_by": review.first_reviewed_by,
        "final_reviewed_by": review.final_reviewed_by,
    }
    if line is not None:
        row.update(
            {
                "sku": line.msku,
                "gtin": line.gtin,
                "serial_number": line.serial_number,
                "ordered_at": line.ordered_at.isoformat() if line.ordered_at else None,
                "shipped_at": line.shipped_at.isoformat() if line.shipped_at else None,
                "settled_at": line.settled_at.isoformat() if line.settled_at else None,
                "quantity": format(q4(Decimal(line.quantity)), "f"),
                "fx_status": line.fx_status,
                "amounts": {
                    c: money(getattr(line, c), "USD")
                    for c in (*REVENUE, *ORDER_FEES, *ITEM_FEES, "ad_cost_usd", "disposal_loss_usd")
                },
            }
        )
        if access.can_see_cost:
            row["costs"] = {
                "purchase_cost_cny": money(line.purchase_cost_cny, "CNY"),
                "head_cost_cny": money(line.head_cost_cny, "CNY"),
                "goods_cost_usd": money(line.goods_cost_usd, "USD"),
            }
        if access.can_see_net_profit:
            row["net_profit_share"] = money(line.net_profit_share_cny, "CNY")
    return row


# ------------------------------------------------------------------ inventory


def inventory(
    session: Session,
    access: SettlementAccess,
    *,
    months: list[date],
    stores: list[str] | None,
    category: list[str] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    owned_items: set[tuple[str, str]] | None = None
    if access.owner_ids is not None:
        owned_items = {
            (r.store_id, r.item_id) for r in _item_rows(session, access, months, stores, None)
        }
    summary_stmt = select(InventoryMovementMonth).where(
        InventoryMovementMonth.store_id != UNMAPPED_STORE_ID
    )
    detail_stmt = select(InventoryMovementLine).join(
        SettlementReconcileStoreMonth,
        and_(
            SettlementReconcileStoreMonth.store_id == InventoryMovementLine.store_id,
            SettlementReconcileStoreMonth.bill_month == InventoryMovementLine.movement_month,
            SettlementReconcileStoreMonth.calc_version == InventoryMovementLine.calc_version,
        ),
    )
    if months:
        summary_stmt = summary_stmt.where(InventoryMovementMonth.month.in_(months))
        detail_stmt = detail_stmt.where(InventoryMovementLine.movement_month.in_(months))
    if stores is not None:
        summary_stmt = summary_stmt.where(InventoryMovementMonth.store_id.in_(stores))
        detail_stmt = detail_stmt.where(InventoryMovementLine.store_id.in_(stores))
    if category:
        summary_stmt = summary_stmt.where(InventoryMovementMonth.category.in_(category))
        detail_stmt = detail_stmt.where(InventoryMovementLine.category.in_(category))
    summary_rows = [
        r
        for r in session.execute(summary_stmt).scalars()
        if owned_items is None or (r.store_id, r.item_id) in owned_items
    ]
    detail_rows = [
        r
        for r in session.execute(detail_stmt).scalars()
        if owned_items is None or (r.store_id, r.item_id) in owned_items
    ]

    def value(cny, usd) -> dict[str, Any]:
        if not access.can_see_cost:
            return {}
        return {"goods_value_cny": money(cny, "CNY"), "goods_value_usd": money(usd, "USD")}

    return (
        {
            "summary": [
                {
                    "store_id": r.store_id,
                    "item_id": r.item_id,
                    "month": r.month.strftime("%Y-%m"),
                    "category": r.category,
                    "quantity": format(q4(Decimal(r.quantity)), "f"),
                    **value(r.goods_value_cny, r.goods_value_usd),
                }
                for r in summary_rows
            ],
            "details": [
                {
                    "store_id": r.store_id,
                    "store_mapping_status": r.store_mapping_status,
                    "item_id": r.item_id,
                    "month": r.movement_month.strftime("%Y-%m"),
                    "business_type": r.business_type,
                    "category": r.category,
                    "serial_number": r.serial_number,
                    "quantity": format(q4(Decimal(r.quantity)), "f"),
                    "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                    **value(r.goods_value_cny, r.goods_value_usd),
                }
                for r in detail_rows
            ],
        },
        meta(
            ["mart_inventory_movement_month", "fact_inventory_movement_lines"],
            len(detail_rows),
            max((r.calc_version for r in detail_rows), default=None),
            max((r.updated_at for r in detail_rows), default=None),
        ),
    )


# ------------------------------------------------------------------ adjustments ledger


def adjustment_row(a: SettlementOrderAdjustment) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "line_key": a.line_key,
        "store_id": a.store_id,
        "store_label": store_label(a.store_id),
        "month": a.bill_month.strftime("%Y-%m"),
        "kind": a.kind,
        "payload": a.payload,
        "reason": a.reason,
        "status": a.status,
        "version": a.version,
        "actor_id": a.actor_id,
        "actor_role": a.actor_role,
        "acted_at": a.acted_at.isoformat(),
        "revoked_by": a.revoked_by,
        "revoked_at": a.revoked_at.isoformat() if a.revoked_at else None,
        "revoke_reason": a.revoke_reason,
    }


def adjustments(
    session: Session,
    access: SettlementAccess,
    *,
    months: list[date],
    status: str | None,
    page: Page,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stmt = select(SettlementOrderAdjustment)
    if months:
        stmt = stmt.where(SettlementOrderAdjustment.bill_month.in_(months))
    if status:
        stmt = stmt.where(SettlementOrderAdjustment.status == status)
    stmt = _scope_stores(stmt, SettlementOrderAdjustment.store_id, access, None)
    if not access.all_stores:
        stmt = stmt.where(SettlementOrderAdjustment.store_id.in_(sorted(access.store_ids)))
    if access.owner_ids is not None:
        owned = select(SettlementOrderReview.line_key).where(
            SettlementOrderReview.owner_ref.in_(sorted(access.owner_ids))
        )
        stmt = stmt.where(SettlementOrderAdjustment.line_key.in_(owned))
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        session.execute(
            stmt.order_by(SettlementOrderAdjustment.acted_at.desc())
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        ).scalars()
    )
    return (
        {"rows": [adjustment_row(a) for a in rows]},
        meta(
            ["manual_settlement_order_adjustments"],
            total,
            None,
            max((a.updated_at for a in rows), default=None),
        ),
    )


# ------------------------------------------------------------------ reconcile


def reconcile(
    session: Session, access: SettlementAccess, *, months: list[date], stores: list[str] | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    access.require_not_owner_limited()  # store-level totals are not per-owner data
    stmt = select(SettlementReconcileStoreMonth).where(
        SettlementReconcileStoreMonth.store_id != UNMAPPED_STORE_ID
    )
    if months:
        stmt = stmt.where(SettlementReconcileStoreMonth.bill_month.in_(months))
    if stores is not None:
        stmt = stmt.where(SettlementReconcileStoreMonth.store_id.in_(stores))
    rows = list(
        session.execute(
            stmt.order_by(
                SettlementReconcileStoreMonth.bill_month, SettlementReconcileStoreMonth.store_id
            )
        ).scalars()
    )
    return (
        {
            "rows": [
                {
                    "store_id": r.store_id,
                    "month": r.bill_month.strftime("%Y-%m"),
                    "settlement_total": money(r.settlement_total_usd, "USD"),
                    "order_level_total": money(r.order_level_total_usd, "USD"),
                    "unassigned_pending": money(r.unassigned_pending_usd, "USD"),
                    "diff": money(r.diff_usd, "USD"),
                    "ad_daily_vs_settlement_diff": money(r.ad_daily_vs_settlement_diff_usd, "USD"),
                    "inbound_freight_lx_vs_settlement_diff": money(
                        r.inbound_freight_lx_vs_settlement_diff_usd, "USD"
                    ),
                    "cross_month_disposal_fee": money(r.cross_month_disposal_fee_usd, "USD"),
                    "status": r.status,
                    "fx_status": r.fx_status,
                    "calc_version": r.calc_version,
                    "frozen": r.frozen_at is not None,
                }
                for r in rows
            ]
        },
        meta(
            ["mart_settlement_reconcile_store_month"],
            len(rows),
            max((r.calc_version for r in rows), default=None),
            max((r.updated_at for r in rows), default=None),
        ),
    )


# ------------------------------------------------------------------ config


def config_for_month(session: Session, month: date) -> NetProfitAllocationConfig | None:
    return session.execute(
        select(NetProfitAllocationConfig)
        .where(NetProfitAllocationConfig.effective_month <= month)
        .order_by(NetProfitAllocationConfig.effective_month.desc())
        .limit(1)
    ).scalar_one_or_none()
