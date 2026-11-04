"""Write side of the settlement profit API (PRP §5, §7, §8.9).

Every write:
- needs an ``Idempotency-Key``; the same actor + endpoint + key within 24 hours returns the
  first response, a different body under the same key is refused (IDEMPOTENCY_CONFLICT);
- is recorded in ``manual_settlement_write_log`` with actor_id, actor_role, acted_at,
  request_id, reason, before and after; manual_* rows carry the same audit columns;
- locks the target rows (SELECT … FOR UPDATE) and checks ``expected_version``
  (STALE_VERSION) so two people cannot overwrite each other;
- only touches manual_* rows, the order review state and frozen flags — never RAW / ODS.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode

from ..settlement_profit_models import (
    NetProfitAllocationConfig,
    SettlementMonthClose,
    SettlementOrderAdjustment,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementPostCloseDiff,
    SettlementProfitItemMonth,
    SettlementReconcileStoreMonth,
    SettlementReviewAction,
    SettlementWriteLog,
)
from .access import (
    ADJUST,
    CLOSE_MONTH,
    CONFIG,
    FIELD_COST,
    REVIEW_FINAL,
    REVIEW_FIRST,
    SettlementAccess,
)
from .engine import ORDER_COLUMN
from .keys import UNMAPPED_STORE_ID
from .money import ZERO, q4
from .persistence import is_month_closed
from .queries import SOURCE, adjustment_row, money, parse_month
from .rules import OwnerItem, allocate_net_profit
from .schemas import (
    BATCH_CONFIRM_THRESHOLD,
    AdjustmentCreate,
    CloseRequest,
    NetProfitConfigUpdate,
    ReopenRequest,
    ReviewRequest,
    RevokeRequest,
)
from .service import DEFAULT_FIXED_CNY

IDEMPOTENCY_TTL = timedelta(hours=24)
AMOUNT_COLUMNS = frozenset(ORDER_COLUMN.values())
# order of the blocker that names the error code when several apply
CLOSE_BLOCKERS = (
    "NOT_CALCULATED",
    "ALREADY_CLOSED",
    "FX_MISSING",
    "RECONCILE_FAILED",
    "UNASSIGNED_PENDING",
    "OWNER_MISSING",
    "OWNER_SALES_ZERO",
)

MESSAGES = {
    "STALE_VERSION": "数据已被他人修改，请刷新",
    "MONTH_CLOSED": "该月已结账",
    "ALREADY_REVOKED": "这条调整已撤销",
    "STAGE_ORDER": "终审前须先初审",
    "SAME_REVIEWER": "同一人不可对同一单既初审又终审",
    "NOT_REVIEWABLE": "这一行不能审核",
    "NOT_CLOSED": "该月未结账",
    "ALREADY_CLOSED": "该月已结账",
    "NOT_CALCULATED": "该店该月还没有计算结果",
    "FX_MISSING": "该账单月汇率缺失，请在定价规则里维护该月汇率",
    "RECONCILE_FAILED": "店铺月对平失败",
    "UNASSIGNED_PENDING": "还有待指定金额",
    "OWNER_MISSING": "有销售的商品缺少负责人",
    "OWNER_SALES_ZERO": "有负责人当月销售额为 0",
    "CONFIRM_TOKEN_MISMATCH": "确认口令不对",
    "IDEMPOTENCY_CONFLICT": "同一个 Idempotency-Key 已用于不同的请求",
    "IDEMPOTENCY_KEY_EXPIRED": "Idempotency-Key 已超过 24 小时，请换一个",
}


def fail(code: str, status_code: int = 409, **details: Any) -> ApiError:
    return ApiError(code=code, status_code=status_code, message=MESSAGES.get(code), details=details)


def invalid(**details: Any) -> ApiError:
    return ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422, details=details)


def month_text(value: date) -> str:
    return value.strftime("%Y-%m")


# ------------------------------------------------------------------ recalculation hook


class Recalculator(Protocol):
    def __call__(self, session: Session, bill_month: date, store_ids: list[str]) -> str:
        """Recalculate the month; returns ``done`` or ``deferred``."""
        ...


def deferred_recalculator(session: Session, bill_month: date, store_ids: list[str]) -> str:
    """Default until the settlement-line database loader is on main (PRP §10 PR-3)."""
    return "deferred"


def _recalc(
    recalc: Recalculator, session: Session, month: date, stores: list[str]
) -> dict[str, Any]:
    stores = sorted(set(stores))
    status = recalc(session, month, stores)
    return {"status": status, "month": month_text(month), "store_ids": stores}


# ------------------------------------------------------------------ idempotency + write log


@dataclass(frozen=True)
class WriteContext:
    access: SettlementAccess
    endpoint: str  # route template, e.g. "POST /orders/{line_id}/adjustments"
    idempotency_key: str
    request_id: str
    now: datetime


@dataclass
class WriteOutcome:
    data: dict[str, Any]
    reason: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


def request_hash(endpoint: str, params: dict[str, Any], body: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"endpoint": endpoint, "params": params, "body": body},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _find_log(session: Session, ctx: WriteContext) -> SettlementWriteLog | None:
    return session.execute(
        select(SettlementWriteLog).where(
            SettlementWriteLog.actor_id == ctx.access.actor_id,
            SettlementWriteLog.endpoint == ctx.endpoint,
            SettlementWriteLog.idempotency_key == ctx.idempotency_key,
        )
    ).scalar_one_or_none()


def _replay(log: SettlementWriteLog, ctx: WriteContext, digest: str) -> dict[str, Any]:
    if log.acted_at < ctx.now - IDEMPOTENCY_TTL:
        raise fail("IDEMPOTENCY_KEY_EXPIRED")
    if log.request_hash != digest:
        raise fail("IDEMPOTENCY_CONFLICT")
    return {"data": log.response, "write_id": str(log.id), "replay": True}


def run_write(
    session: Session,
    ctx: WriteContext,
    params: dict[str, Any],
    body: dict[str, Any],
    action: Callable[[], WriteOutcome],
) -> dict[str, Any]:
    """Replay or run ``action`` once; errors are not stored, so a fixed request can retry."""
    digest = request_hash(ctx.endpoint, params, body)
    existing = _find_log(session, ctx)
    if existing is not None:
        return _replay(existing, ctx, digest)
    try:
        outcome = action()
        log = SettlementWriteLog(
            idempotency_key=ctx.idempotency_key,
            actor_id=ctx.access.actor_id,
            actor_role=ctx.access.actor_role,
            endpoint=ctx.endpoint,
            request_hash=digest,
            request_id=ctx.request_id,
            acted_at=ctx.now,
            reason=outcome.reason,
            before=outcome.before,
            after=outcome.after,
            response=outcome.data,
            status_code=200,
        )
        session.add(log)
        session.flush()
        session.commit()
    except IntegrityError:
        # a concurrent request with the same key won, or another actor's manual_* row
        # already uses this key: replay the winner or refuse.
        session.rollback()
        existing = _find_log(session, ctx)
        if existing is not None:
            return _replay(existing, ctx, digest)
        raise fail("IDEMPOTENCY_CONFLICT") from None
    except Exception:
        session.rollback()
        raise
    return {"data": outcome.data, "write_id": str(log.id), "replay": False}


def _audit(ctx: WriteContext) -> dict[str, Any]:
    return {
        "actor_id": ctx.access.actor_id,
        "actor_role": ctx.access.actor_role,
        "acted_at": ctx.now,
        "request_id": ctx.request_id,
        "idempotency_key": ctx.idempotency_key,
    }


# ------------------------------------------------------------------ shared guards


def _visible_review(
    session: Session, access: SettlementAccess, line_id: UUID
) -> SettlementOrderReview:
    review = session.execute(
        select(SettlementOrderReview).where(SettlementOrderReview.id == line_id).with_for_update()
    ).scalar_one_or_none()
    if (
        review is None
        or not access.store_visible(review.store_id)
        or not access.owner_visible(review.owner_ref)
    ):
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    return review


def _ensure_open(session: Session, store_id: str, month: date) -> None:
    if store_id != UNMAPPED_STORE_ID and is_month_closed(session, store_id, month) is not None:
        raise fail("MONTH_CLOSED", store_id=store_id, month=month_text(month))


def _ensure_version(current: int, expected: int) -> None:
    if current != expected:
        raise fail("STALE_VERSION", current_version=current, expected_version=expected)


def _check_token(given: str | None, expected: str) -> None:
    if (given or "").strip() != expected:
        raise fail("CONFIRM_TOKEN_MISMATCH", 422, expected_format=expected)


def _line_state(review: SettlementOrderReview) -> dict[str, Any]:
    return {"line_id": str(review.id), "status": review.status, "version": review.version}


def _reset_review(review: SettlementOrderReview, status: str) -> None:
    """A change after review sends the line back to first review (§8.9)."""
    review.status = status
    review.first_reviewed_by = review.first_reviewed_at = None
    review.final_reviewed_by = review.final_reviewed_at = None
    review.version += 1


def _decimal(value: Any, field: str, *, allow_negative: bool) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise invalid(**{field: "expected a decimal string"}) from None
    if not number.is_finite() or (not allow_negative and number < 0):
        raise invalid(**{field: "must be a finite number" + ("" if allow_negative else " ≥ 0")})
    if number != q4(number):
        raise invalid(**{field: "at most 4 decimal places"})
    return number


# ------------------------------------------------------------------ adjustments


def _known_store(session: Session, store_id: str) -> bool:
    return (
        session.execute(
            select(SettlementReconcileStoreMonth.id)
            .where(SettlementReconcileStoreMonth.store_id == store_id)
            .limit(1)
        ).first()
        is not None
    )


def _normalize_payload(
    session: Session,
    access: SettlementAccess,
    review: SettlementOrderReview,
    body: AdjustmentCreate,
) -> dict[str, Any]:
    p = body.payload
    is_unmapped = review.store_id == UNMAPPED_STORE_ID

    def only(*keys: str) -> None:
        extra = sorted(set(p) - set(keys))
        if extra:
            raise invalid(payload={"unexpected": extra, "allowed": list(keys)})

    if body.kind in ("cost", "amount") and review.row_kind != "order":
        raise invalid(kind=f"{body.kind} applies to order rows only")
    if body.kind == "cost":
        access.require(FIELD_COST)
        only("purchase_cny", "head_cny")
        if not p:
            raise invalid(payload="purchase_cny or head_cny is required")
        return {
            k: format(_decimal(p[k], k, allow_negative=False), "f")
            for k in ("purchase_cny", "head_cny")
            if k in p
        }
    if body.kind == "amount":
        only("column", "delta", "currency")
        column = p.get("column")
        if column not in AMOUNT_COLUMNS:
            raise invalid(column=sorted(AMOUNT_COLUMNS))
        if p.get("currency", "USD") != "USD":
            raise invalid(currency="amount adjustments are USD")
        delta = _decimal(p.get("delta"), "delta", allow_negative=True)
        if delta == ZERO:
            raise invalid(delta="must not be 0")
        return {"column": column, "delta_usd": format(delta, "f")}
    if body.kind == "assign_item":
        only("item_id")
        if review.row_kind != "unassigned" or is_unmapped:
            raise invalid(kind="assign_item applies to 待指定 rows of a store")
        item_id = str(p.get("item_id") or "").strip()
        if not item_id or len(item_id) > 128:
            raise invalid(item_id="required, at most 128 characters")
        return {"item_id": item_id}
    if body.kind == "assign_store":
        only("store_id")
        if review.row_kind != "unassigned" or not is_unmapped:
            raise invalid(kind="assign_store applies to 未对上店铺 rows only")
        store_id = str(p.get("store_id") or "").strip()
        if not store_id or store_id == UNMAPPED_STORE_ID or not _known_store(session, store_id):
            raise invalid(store_id="must be an existing store")
        _ensure_open(session, store_id, review.bill_month)
        return {"store_id": store_id}
    only("text")
    text_value = p.get("text")
    if text_value is not None and (not isinstance(text_value, str) or len(text_value) > 2000):
        raise invalid(text="at most 2000 characters")
    return {"text": text_value} if text_value else {}


def create_adjustment(
    session: Session,
    ctx: WriteContext,
    line_id: UUID,
    body: AdjustmentCreate,
    recalc: Recalculator,
) -> dict[str, Any]:
    ctx.access.require(ADJUST)

    def action() -> WriteOutcome:
        review = _visible_review(session, ctx.access, line_id)
        _ensure_open(session, review.store_id, review.bill_month)
        _ensure_version(review.version, body.expected_version)
        payload = _normalize_payload(session, ctx.access, review, body)
        before = {"line": _line_state(review), "item_id": review.item_id}
        adjustment = SettlementOrderAdjustment(
            line_key=review.line_key,
            store_id=review.store_id,
            bill_month=review.bill_month,
            kind=body.kind,
            payload=payload,
            reason=body.reason.strip(),
            **_audit(ctx),
        )
        session.add(adjustment)
        _reset_review(review, "adjusted")
        session.flush()
        stores = [review.store_id, *([payload["store_id"]] if "store_id" in payload else [])]
        recalc_out = _recalc(
            recalc, session, review.bill_month, [s for s in stores if s != UNMAPPED_STORE_ID]
        )
        # the recalculation may bump the line version again (amounts changed): report the
        # version the caller must send next
        after = {"line": _line_state(review), "adjustment_id": str(adjustment.id)}
        adjustment.before, adjustment.after = before, after
        session.flush()
        data = {
            "adjustment": adjustment_row(adjustment),
            "line": _line_state(review),
            "recalc": recalc_out,
        }
        return WriteOutcome(data, body.reason.strip(), before, after)

    return run_write(session, ctx, {"line_id": str(line_id)}, body.model_dump(mode="json"), action)


def revoke_adjustment(
    session: Session,
    ctx: WriteContext,
    adjustment_id: UUID,
    body: RevokeRequest,
    recalc: Recalculator,
) -> dict[str, Any]:
    ctx.access.require(ADJUST)

    def action() -> WriteOutcome:
        adjustment = session.execute(
            select(SettlementOrderAdjustment)
            .where(SettlementOrderAdjustment.id == adjustment_id)
            .with_for_update()
        ).scalar_one_or_none()
        if adjustment is None or not ctx.access.store_visible(adjustment.store_id):
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if adjustment.status == "revoked":
            raise fail("ALREADY_REVOKED")
        _ensure_open(session, adjustment.store_id, adjustment.bill_month)
        if adjustment.kind == "assign_store":
            _ensure_open(session, str(adjustment.payload.get("store_id")), adjustment.bill_month)
        _ensure_version(adjustment.version, body.expected_version)
        review = session.execute(
            select(SettlementOrderReview)
            .where(
                SettlementOrderReview.store_id == adjustment.store_id,
                SettlementOrderReview.bill_month == adjustment.bill_month,
                SettlementOrderReview.line_key == adjustment.line_key,
            )
            .with_for_update()
        ).scalar_one_or_none()
        before = {
            "adjustment": {"status": adjustment.status, "version": adjustment.version},
            "line": None if review is None else _line_state(review),
        }
        adjustment.status = "revoked"
        adjustment.revoked_by = ctx.access.actor_id
        adjustment.revoked_at = ctx.now
        adjustment.revoke_reason = body.reason.strip()
        adjustment.version += 1
        if review is not None:
            _reset_review(review, "pending")  # §8.9: revoke → back to first review
        session.flush()
        stores = [adjustment.store_id]
        if adjustment.kind == "assign_store":
            stores.append(str(adjustment.payload.get("store_id")))
        recalc_out = _recalc(
            recalc, session, adjustment.bill_month, [s for s in stores if s != UNMAPPED_STORE_ID]
        )
        line = (
            _line_state(review)
            if review is not None
            else {"line_id": "", "status": "pending", "version": 0}
        )
        after = {
            "adjustment": {"status": adjustment.status, "version": adjustment.version},
            "line": line,
        }
        data = {"adjustment": adjustment_row(adjustment), "line": line, "recalc": recalc_out}
        return WriteOutcome(data, body.reason.strip(), before, after)

    return run_write(
        session, ctx, {"adjustment_id": str(adjustment_id)}, body.model_dump(mode="json"), action
    )


# ------------------------------------------------------------------ batch review


def review_lines(session: Session, ctx: WriteContext, body: ReviewRequest) -> dict[str, Any]:
    ctx.access.require(REVIEW_FIRST if body.stage == "first" else REVIEW_FINAL)
    line_ids = list(dict.fromkeys(body.line_ids))
    comment = (body.comment or "").strip() or None
    if body.decision == "reject" and comment is None:
        raise invalid(comment="退回原因必填")
    missing = [str(i) for i in line_ids if str(i) not in body.expected_versions]
    if missing:
        raise invalid(expected_versions={"missing": missing[:20]})
    if len(line_ids) >= BATCH_CONFIRM_THRESHOLD:
        _check_token(body.confirm_token, f"REVIEW {len(line_ids)}")
    actor = ctx.access.actor_id

    def one(line_id: UUID) -> dict[str, Any]:
        def result(code: str, review: SettlementOrderReview | None = None) -> dict[str, Any]:
            out: dict[str, Any] = {"line_id": str(line_id), "ok": False, "code": code}
            if review is not None:
                out.update(status=review.status, version=review.version)
            return out

        try:
            review = _visible_review(session, ctx.access, line_id)
        except ApiError:
            return result("NOT_FOUND")
        if review.row_kind != "order":
            return result("NOT_REVIEWABLE", review)
        if is_month_closed(session, review.store_id, review.bill_month) is not None:
            return result("MONTH_CLOSED", review)
        if review.version != body.expected_versions[str(line_id)]:
            return result("STALE_VERSION", review)
        if body.stage == "first" and review.status in ("first_passed", "final_passed"):
            return result("STAGE_ORDER", review)
        if body.stage == "final":
            if review.status != "first_passed":
                return result("STAGE_ORDER", review)
            if review.first_reviewed_by == actor:
                return result("SAME_REVIEWER", review)
        before = _line_state(review)
        if body.decision == "pass" and body.stage == "first":
            review.status = "first_passed"
            review.first_reviewed_by, review.first_reviewed_at = actor, ctx.now
        elif body.decision == "pass":
            review.status = "final_passed"
            review.final_reviewed_by, review.final_reviewed_at = actor, ctx.now
        else:  # 退回: back to the previous step, reason required
            review.status = "rejected"
            if body.stage == "final":
                review.final_reviewed_by = review.final_reviewed_at = None
            review.first_reviewed_by = review.first_reviewed_at = None
        review.version += 1
        session.add(
            SettlementReviewAction(
                line_key=review.line_key,
                store_id=review.store_id,
                bill_month=review.bill_month,
                stage=body.stage,
                decision=body.decision,
                comment=comment,
                line_version=before["version"],
                before=before,
                after=_line_state(review),
                **_audit(ctx),
            )
        )
        return {"line_id": str(line_id), "ok": True, **_line_state(review)} | {"code": None}

    def action() -> WriteOutcome:
        results = [one(i) for i in line_ids]
        session.flush()
        ok = sum(1 for r in results if r["ok"])
        data = {
            "stage": body.stage,
            "decision": body.decision,
            "results": results,
            "succeeded": ok,
            "failed": len(results) - ok,
        }
        return WriteOutcome(
            data,
            comment,
            {"line_ids": [str(i) for i in line_ids]},
            {"succeeded": ok, "failed": len(results) - ok},
        )

    return run_write(session, ctx, {}, body.model_dump(mode="json"), action)


# ------------------------------------------------------------------ month close / reopen


def _month_stores(session: Session, month: date) -> list[str]:
    return list(
        session.execute(
            select(SettlementReconcileStoreMonth.store_id)
            .where(
                SettlementReconcileStoreMonth.bill_month == month,
                SettlementReconcileStoreMonth.store_id != UNMAPPED_STORE_ID,
            )
            .order_by(SettlementReconcileStoreMonth.store_id)
        ).scalars()
    )


def _target_stores(
    session: Session, access: SettlementAccess, month: date, store_ids: list[str] | str
) -> list[str]:
    if store_ids == "ALL":
        if not access.all_stores:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        stores = _month_stores(session, month)
        if not stores:
            raise fail("NOT_CALCULATED", month=month_text(month))
        return stores
    stores = access.requested_stores(store_ids)
    if not stores:
        raise invalid(store_ids="at least one store, or ALL")
    return stores


def _month_blockers(session: Session, month: date) -> list[str]:
    """Blockers that hold for every store of the month (待指定 未对上店铺, 纯利)."""
    blockers: list[str] = []
    unmapped_pending = session.execute(
        select(func.count())
        .select_from(SettlementOrderReview)
        .where(
            SettlementOrderReview.store_id == UNMAPPED_STORE_ID,
            SettlementOrderReview.bill_month == month,
            SettlementOrderReview.row_kind == "unassigned",
            SettlementOrderReview.status == "pending",
        )
    ).scalar_one()
    if unmapped_pending:
        blockers.append("UNASSIGNED_PENDING")
    items = session.execute(
        select(SettlementProfitItemMonth).where(
            SettlementProfitItemMonth.bill_month == month,
            SettlementProfitItemMonth.store_id != UNMAPPED_STORE_ID,
        )
    ).scalars()
    config = _config_row(session, month)
    net = allocate_net_profit(
        [
            OwnerItem(
                key=(r.store_id, r.item_id),
                owner_ref=r.owner_ref,
                sales_usd=Decimal(r.sales_amount_usd),
                sales_quantity=Decimal(r.sales_quantity),
            )
            for r in items
        ],
        None,
        Decimal(config.fixed_cny) if config else DEFAULT_FIXED_CNY,
        list(config.excluded_owner_ids) if config else [],
    )
    blockers.extend(net.blockers)
    return blockers


def _store_blockers(
    session: Session, store_id: str, month: date, month_wide: list[str]
) -> list[str]:
    if is_month_closed(session, store_id, month) is not None:
        return ["ALREADY_CLOSED"]
    rec = session.execute(
        select(SettlementReconcileStoreMonth).where(
            SettlementReconcileStoreMonth.store_id == store_id,
            SettlementReconcileStoreMonth.bill_month == month,
        )
    ).scalar_one_or_none()
    if rec is None:
        return ["NOT_CALCULATED"]
    blockers = set(month_wide)
    if rec.fx_status == "missing":
        blockers.add("FX_MISSING")
    if rec.status == "reconcile_failed":
        blockers.add("RECONCILE_FAILED")
    pending = session.execute(
        select(func.count())
        .select_from(SettlementOrderReview)
        .where(
            SettlementOrderReview.store_id == store_id,
            SettlementOrderReview.bill_month == month,
            SettlementOrderReview.row_kind == "unassigned",
            SettlementOrderReview.status == "pending",
        )
    ).scalar_one()
    if rec.status == "unassigned_pending" or pending:
        blockers.add("UNASSIGNED_PENDING")
    return [b for b in CLOSE_BLOCKERS if b in blockers]


def _close_row(session: Session, store_id: str, month: date) -> SettlementMonthClose | None:
    return session.execute(
        select(SettlementMonthClose)
        .where(
            SettlementMonthClose.store_scope == store_id,
            SettlementMonthClose.bill_month == month,
        )
        .with_for_update()
    ).scalar_one_or_none()


def close_row_out(row: SettlementMonthClose) -> dict[str, Any]:
    return {
        "store_id": row.store_scope,
        "month": month_text(row.bill_month),
        "status": row.status,
        "frozen_calc_version": row.frozen_calc_version,
        "snapshot_totals": row.snapshot_totals,
        "reopen_reason": row.reopen_reason,
        "version": row.version,
    }


def _snapshot(session: Session, rec: SettlementReconcileStoreMonth) -> dict[str, Any]:
    sums = session.execute(
        select(
            func.coalesce(func.sum(SettlementProfitItemMonth.sales_amount_usd), 0),
            func.sum(SettlementProfitItemMonth.gross_profit_usd),
            func.sum(SettlementProfitItemMonth.net_profit_cny),
        ).where(
            SettlementProfitItemMonth.store_id == rec.store_id,
            SettlementProfitItemMonth.bill_month == rec.bill_month,
        )
    ).one()
    return {
        "calc_version": rec.calc_version,
        "settlement_total": money(rec.settlement_total_usd, "USD"),
        "order_level_total": money(rec.order_level_total_usd, "USD"),
        "diff": money(rec.diff_usd, "USD"),
        "sales": money(sums[0], "USD"),
        "gross_profit": money(sums[1], "USD"),
        "net_profit": money(sums[2], "CNY"),
    }


def close_month(
    session: Session, ctx: WriteContext, month_value: str, body: CloseRequest
) -> dict[str, Any]:
    ctx.access.require(CLOSE_MONTH)
    month = parse_month(month_value)
    _check_token(body.confirm_token, f"CLOSE {month_text(month)}")

    def action() -> WriteOutcome:
        stores = _target_stores(session, ctx.access, month, body.store_ids)
        month_wide = _month_blockers(session, month)
        blocked = {s: b for s in stores if (b := _store_blockers(session, s, month, month_wide))}
        if blocked:
            first = next(c for c in CLOSE_BLOCKERS if any(c in b for b in blocked.values()))
            raise fail(first, month=month_text(month), blockers=blocked)
        rows = []
        for store_id in stores:
            rec = session.execute(
                select(SettlementReconcileStoreMonth)
                .where(
                    SettlementReconcileStoreMonth.store_id == store_id,
                    SettlementReconcileStoreMonth.bill_month == month,
                )
                .with_for_update()
            ).scalar_one()
            version = rec.calc_version
            session.execute(
                update(SettlementOrderLine)
                .where(
                    SettlementOrderLine.store_id == store_id,
                    SettlementOrderLine.bill_month == month,
                    SettlementOrderLine.calc_version == version,
                )
                .values(frozen_at=ctx.now, frozen_by=ctx.access.actor_id)
            )
            session.execute(
                update(SettlementProfitItemMonth)
                .where(
                    SettlementProfitItemMonth.store_id == store_id,
                    SettlementProfitItemMonth.bill_month == month,
                )
                .values(frozen_at=ctx.now)
            )
            rec.frozen_at = ctx.now
            snapshot = _snapshot(session, rec)
            row = _close_row(session, store_id, month)
            if row is None:
                row = SettlementMonthClose(store_scope=store_id, bill_month=month, version=1)
                session.add(row)
            else:
                row.version += 1
            row.status = "closed"
            row.frozen_calc_version = version
            row.snapshot_totals = snapshot
            row.reopen_reason = None
            for k, v in _audit(ctx).items():
                setattr(row, k, v)
            row.before, row.after = None, {"status": "closed", "snapshot_totals": snapshot}
            rows.append(row)
        session.flush()
        out = [close_row_out(r) for r in rows]
        return WriteOutcome(
            {"month": month_text(month), "rows": out, "recalc": None},
            None,
            {"store_ids": stores, "status": "open"},
            {"rows": out},
        )

    return run_write(
        session, ctx, {"month": month_text(month)}, body.model_dump(mode="json"), action
    )


def reopen_month(
    session: Session,
    ctx: WriteContext,
    month_value: str,
    body: ReopenRequest,
    recalc: Recalculator,
) -> dict[str, Any]:
    ctx.access.require(CLOSE_MONTH)
    month = parse_month(month_value)
    _check_token(body.confirm_token, f"REOPEN {month_text(month)}")
    reason = body.reason.strip()

    def action() -> WriteOutcome:
        if body.store_ids == "ALL":
            if not ctx.access.all_stores:
                raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
            stores = list(
                session.execute(
                    select(SettlementMonthClose.store_scope)
                    .where(
                        SettlementMonthClose.bill_month == month,
                        SettlementMonthClose.status == "closed",
                    )
                    .order_by(SettlementMonthClose.store_scope)
                ).scalars()
            )
        else:
            stores = _target_stores(session, ctx.access, month, body.store_ids)
        rows = {s: _close_row(session, s, month) for s in stores}
        not_closed = [s for s, r in rows.items() if r is None or r.status != "closed"]
        if not stores or not_closed:
            raise fail("NOT_CLOSED", month=month_text(month), store_ids=not_closed)
        befores: dict[str, Any] = {}
        for store_id, row in rows.items():
            assert row is not None
            befores[store_id] = {"status": row.status, "snapshot_totals": row.snapshot_totals}
            session.execute(
                update(SettlementOrderLine)
                .where(
                    SettlementOrderLine.store_id == store_id,
                    SettlementOrderLine.bill_month == month,
                    SettlementOrderLine.frozen_at.is_not(None),
                )
                .values(frozen_at=None, frozen_by=None)
            )
            for model in (SettlementProfitItemMonth, SettlementReconcileStoreMonth):
                session.execute(
                    update(model)
                    .where(model.store_id == store_id, model.bill_month == month)
                    .values(frozen_at=None)
                )
            session.execute(
                update(SettlementPostCloseDiff)
                .where(
                    SettlementPostCloseDiff.store_id == store_id,
                    SettlementPostCloseDiff.bill_month == month,
                    SettlementPostCloseDiff.status.in_(("open", "acknowledged")),
                )
                .values(status="resolved_by_reopen")
            )
            row.status = "reopened"
            row.reopen_reason = reason
            row.version += 1
            for k, v in _audit(ctx).items():
                setattr(row, k, v)
            row.before = befores[store_id]
            row.after = {"status": "reopened", "reopen_reason": reason}
        session.flush()
        out = [close_row_out(r) for r in rows.values() if r is not None]
        data = {
            "month": month_text(month),
            "rows": out,
            "recalc": _recalc(recalc, session, month, stores),
        }
        return WriteOutcome(data, reason, befores, {"rows": out})

    return run_write(
        session, ctx, {"month": month_text(month)}, body.model_dump(mode="json"), action
    )


# ------------------------------------------------------------------ 纯利设置


def _config_row(session: Session, month: date) -> NetProfitAllocationConfig | None:
    return session.execute(
        select(NetProfitAllocationConfig)
        .where(NetProfitAllocationConfig.effective_month <= month)
        .order_by(NetProfitAllocationConfig.effective_month.desc())
        .limit(1)
    ).scalar_one_or_none()


def config_out(row: NetProfitAllocationConfig | None, month: date) -> dict[str, Any]:
    if row is None:
        return {
            "effective_month": None,
            "requested_month": month_text(month),
            "fixed_cny": money(DEFAULT_FIXED_CNY, "CNY"),
            "excluded_owner_ids": [],
            "version": 0,
            "is_default": True,
        }
    return {
        "effective_month": month_text(row.effective_month),
        "requested_month": month_text(month),
        "fixed_cny": money(row.fixed_cny, "CNY"),
        "excluded_owner_ids": list(row.excluded_owner_ids),
        "version": row.version,
        "is_default": False,
    }


def get_config(session: Session, access: SettlementAccess, month_value: str) -> dict[str, Any]:
    if not access.is_finance:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    month = parse_month(month_value)
    return config_out(_config_row(session, month), month)


def update_config(
    session: Session, ctx: WriteContext, body: NetProfitConfigUpdate, recalc: Recalculator
) -> dict[str, Any]:
    ctx.access.require(CONFIG)
    month = parse_month(body.effective_month)
    _check_token(body.confirm_token, f"CONFIG {month_text(month)}")
    fixed = _decimal(body.fixed_cny, "fixed_cny", allow_negative=False)
    excluded = [o.strip() for o in body.excluded_owner_ids]
    if any(not o or len(o) > 255 for o in excluded) or len(set(excluded)) != len(excluded):
        raise invalid(excluded_owner_ids="non-empty, unique, at most 255 characters")

    def action() -> WriteOutcome:
        closed = session.execute(
            select(SettlementMonthClose.store_scope).where(
                SettlementMonthClose.bill_month == month,
                SettlementMonthClose.status == "closed",
            )
        ).first()
        if closed is not None:
            raise fail("MONTH_CLOSED", month=month_text(month))
        row = session.execute(
            select(NetProfitAllocationConfig)
            .where(NetProfitAllocationConfig.effective_month == month)
            .with_for_update()
        ).scalar_one_or_none()
        _ensure_version(0 if row is None else row.version, body.expected_version)
        before = None if row is None else config_out(row, month)
        if row is None:
            row = NetProfitAllocationConfig(effective_month=month, version=1)
            session.add(row)
        else:
            row.version += 1
        row.fixed_cny = fixed
        row.excluded_owner_ids = sorted(excluded)
        row.updated_by = ctx.access.actor_id
        row.request_id = ctx.request_id
        row.reason = (body.reason or "").strip() or None
        session.flush()
        after = config_out(row, month)
        data = {"config": after, "recalc": _recalc(recalc, session, month, [])}
        return WriteOutcome(data, row.reason, before, after)

    return run_write(session, ctx, {}, body.model_dump(mode="json"), action)


def write_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {"source": SOURCE, "idempotent_replay": result["replay"], "write_id": result["write_id"]}
