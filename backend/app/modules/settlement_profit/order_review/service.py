"""订单审核服务层（PRP §7、§8.4）：期列表、订单行、精确搜索、交易类型、录成本、审核、重算。

写操作留痕（actor_id / actor_role / request_id），审核记录只增不改；同一人不可对同一行既初审
又终审；已结账的月拒绝写。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from sqlalchemy import cast, func, or_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.settlement_profit.models import (
    REVIEW_STATUSES,
    SettlementCostEntry,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementReviewAction,
)
from app.modules.settlement_profit.order_review.calc import (
    CHANGED_AFTER_REVIEW,
    OrderReviewCalculator,
    RecalcResult,
    month_is_closed,
    periods_for_recalc,
)
from app.modules.settlement_profit.order_review.schemas import (
    CostEntryCreate,
    CostEntryRead,
    CostEntryResult,
    CostEntryRevoke,
    CostSourceRead,
    LineRead,
    LookupData,
    PeriodRead,
    RecalcPeriodResult,
    RecalcRequest,
    RecalcResultData,
    ReviewLineResult,
    ReviewRequest,
    ReviewResultData,
    TransactionTypeRead,
    money,
)
from app.modules.settlement_profit.transaction_types import describe, english_name
from app.modules.walmart_bills.models import WalmartBillPeriod

SOURCE_REF: Final = "primary"
DISPLAY_FROM: Final = date(2026, 10, 1)
MAX_PAGE_SIZE: Final = 200
LOOKUP_LIMIT: Final = 1000

ERR_NOT_FOUND: Final = "NOT_FOUND"
ERR_VALIDATION: Final = "VALIDATION_ERROR"
ERR_MONTH_CLOSED: Final = "MONTH_CLOSED"
ERR_STALE_VERSION: Final = "STALE_VERSION"
ERR_STAGE_ORDER: Final = "STAGE_ORDER"
ERR_SAME_REVIEWER: Final = "SAME_REVIEWER"
ERR_ALREADY_REVOKED: Final = "ALREADY_REVOKED"
ERR_ENTRY_EXISTS: Final = "COST_ENTRY_EXISTS"
ERR_COST_MISSING: Final = "COST_MISSING"
ERR_ALREADY_PASSED: Final = "ALREADY_PASSED"
ERR_CONFIRM_REQUIRED: Final = "CONFIRM_REQUIRED"

# PRP §5：批量审核 ≥ 20 行要前端二次确认 + 后端 confirm_token（沿用仓库固定令牌写法）
BATCH_CONFIRM_THRESHOLD: Final = 20
BATCH_CONFIRM_TOKEN: Final = "CONFIRM_BATCH_REVIEW"

SORTABLE: Final[dict[str, Any]] = {
    "posted_date": SettlementOrderLine.posted_date,
    "platform_order_no": SettlementOrderLine.platform_order_no,
    "item_id": SettlementOrderLine.item_id,
    "msku": SettlementOrderLine.msku,
    "sales_usd": SettlementOrderLine.sales_usd,
    "settlement_amount_usd": SettlementOrderLine.settlement_amount_usd,
    "cost_total_cny": SettlementOrderLine.cost_total_cny,
    "quantity": SettlementOrderLine.quantity,
    "review_status": SettlementOrderReview.review_status,
    "updated_at": SettlementOrderReview.updated_at,
}


class OrderReviewError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- 期


def list_periods(session: Session, *, store_ids: Sequence[str] = ()) -> list[PeriodRead]:
    statement = select(WalmartBillPeriod).where(
        WalmartBillPeriod.source_account_ref == SOURCE_REF,
        WalmartBillPeriod.report_date >= DISPLAY_FROM,
        WalmartBillPeriod.line_count > 0,
    )
    if store_ids:
        statement = statement.where(WalmartBillPeriod.store_id.in_(list(store_ids)))
    periods = session.scalars(
        statement.order_by(WalmartBillPeriod.report_date.desc(), WalmartBillPeriod.store_id)
    ).all()
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for store, key, status, count in session.execute(
        select(
            SettlementOrderReview.store_id,
            SettlementOrderReview.period_key,
            SettlementOrderReview.review_status,
            func.count(),
        )
        .where(SettlementOrderReview.row_kind == "order")
        .group_by(
            SettlementOrderReview.store_id,
            SettlementOrderReview.period_key,
            SettlementOrderReview.review_status,
        )
    ).all():
        counts.setdefault((store, key), {})[status] = count
    versions = {
        (store, key): (version, calculated)
        for store, key, version, calculated in session.execute(
            select(
                SettlementOrderLine.store_id,
                SettlementOrderLine.period_key,
                func.max(SettlementOrderLine.calc_version),
                func.max(SettlementOrderLine.created_at),
            )
            .where(
                SettlementOrderLine.source_account_ref == SOURCE_REF,
                SettlementOrderLine.is_current.is_(True),
            )
            .group_by(SettlementOrderLine.store_id, SettlementOrderLine.period_key)
        ).all()
    }
    months = {
        (store, key): month
        for store, key, month in session.execute(
            select(
                SettlementOrderLine.store_id,
                SettlementOrderLine.period_key,
                func.max(SettlementOrderLine.bill_month),
            )
            .where(SettlementOrderLine.is_current.is_(True))
            .group_by(SettlementOrderLine.store_id, SettlementOrderLine.period_key)
        ).all()
    }
    out: list[PeriodRead] = []
    for period in periods:
        key = (period.store_id, period.report_key)
        by_status = counts.get(key, {})
        version, calculated = versions.get(key, (None, None))
        out.append(
            PeriodRead(
                store_id=period.store_id,
                store_name=period.store_name,
                period_key=period.report_key,
                report_date=period.report_date,
                period_start_date=period.period_start_date,
                period_end_date=period.period_end_date,
                bill_month=months.get(key),
                line_count=sum(by_status.values()),
                pending_count=by_status.get("pending", 0),
                auto_count=by_status.get("auto", 0),
                first_passed_count=by_status.get("first_passed", 0),
                final_passed_count=by_status.get("final_passed", 0),
                rejected_count=by_status.get("rejected", 0),
                calc_version=version,
                calculated_at=calculated,
            )
        )
    return out


# --------------------------------------------------------------------------- 订单行


@dataclass(frozen=True, slots=True)
class LineFilters:
    period_keys: Sequence[str] = ()
    store_ids: Sequence[str] = ()
    statuses: Sequence[str] = ()
    reasons: Sequence[str] = ()
    item_ids: Sequence[str] = ()
    skus: Sequence[str] = ()
    mskus: Sequence[str] = ()
    transaction_types: Sequence[str] = ()
    line_kinds: Sequence[str] = ()
    keyword: str | None = None
    owner_ids: Sequence[str] = ()


def _line_query(filters: LineFilters) -> Any:
    statement = (
        select(SettlementOrderLine, SettlementOrderReview)
        .join(
            SettlementOrderReview,
            (SettlementOrderReview.store_id == SettlementOrderLine.store_id)
            & (SettlementOrderReview.period_key == SettlementOrderLine.period_key)
            & (SettlementOrderReview.line_key == SettlementOrderLine.line_key)
            & (SettlementOrderReview.row_kind == "order"),
        )
        .where(
            SettlementOrderLine.source_account_ref == SOURCE_REF,
            SettlementOrderLine.is_current.is_(True),
        )
    )
    if filters.period_keys:
        statement = statement.where(SettlementOrderLine.period_key.in_(list(filters.period_keys)))
    if filters.store_ids:
        statement = statement.where(SettlementOrderLine.store_id.in_(list(filters.store_ids)))
    if filters.statuses:
        bad = set(filters.statuses) - set(REVIEW_STATUSES)
        if bad:
            raise OrderReviewError(422, ERR_VALIDATION, "审核状态不合法")
        statement = statement.where(SettlementOrderReview.review_status.in_(list(filters.statuses)))
    if filters.reasons:
        # changed_after_review 在审核行上，其余原因在订单行上（#373 复审第 2 轮 P3-2）
        statement = statement.where(
            or_(
                *[
                    SettlementOrderReview.reasons.contains([r])
                    if r == CHANGED_AFTER_REVIEW
                    else SettlementOrderLine.reasons.contains([r])
                    for r in filters.reasons
                ]
            )
        )
    if filters.transaction_types:
        statement = statement.where(
            or_(
                *[
                    SettlementOrderLine.transaction_types.contains([t])
                    for t in filters.transaction_types
                ]
            )
        )
    if filters.item_ids:
        statement = statement.where(SettlementOrderLine.item_id.in_(list(filters.item_ids)))
    if filters.skus:
        statement = statement.where(SettlementOrderLine.sku.in_(list(filters.skus)))
    if filters.mskus:
        statement = statement.where(SettlementOrderLine.msku.in_(list(filters.mskus)))
    if filters.line_kinds:
        statement = statement.where(SettlementOrderLine.line_kind.in_(list(filters.line_kinds)))
    if filters.owner_ids:
        statement = statement.where(SettlementOrderLine.owner_id.in_(list(filters.owner_ids)))
    keyword = (filters.keyword or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SettlementOrderLine.platform_order_no.ilike(pattern),
                SettlementOrderLine.item_id.ilike(pattern),
                SettlementOrderLine.msku.ilike(pattern),
                SettlementOrderLine.sku.ilike(pattern),
                SettlementOrderLine.gtin.ilike(pattern),
            )
        )
    return statement


def list_lines(
    session: Session,
    *,
    filters: LineFilters,
    page: int,
    page_size: int,
    sort_by: str = "posted_date",
    sort_order: Literal["asc", "desc"] = "desc",
) -> tuple[list[LineRead], int]:
    if sort_by not in SORTABLE:
        raise OrderReviewError(422, ERR_VALIDATION, "排序字段不支持")
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise OrderReviewError(422, ERR_VALIDATION, "分页参数不合法")
    statement = _line_query(filters)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    column = SORTABLE[sort_by]
    ordering = column.desc().nulls_last() if sort_order == "desc" else column.asc().nulls_last()
    rows = session.execute(
        statement.order_by(ordering, SettlementOrderLine.line_key)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [line_read(line, review) for line, review in rows], int(total)


def line_read(line: SettlementOrderLine, review: SettlementOrderReview) -> LineRead:
    profit = None
    if line.cost_total_usd is not None:
        profit = line.settlement_amount_usd - line.cost_total_usd
    return LineRead(
        id=line.id,
        review_id=review.id,
        store_id=line.store_id,
        period_key=line.period_key,
        bill_month=line.bill_month,
        line_key=line.line_key,
        line_kind=line.line_kind,
        fulfillment_type=line.fulfillment_type,
        platform_order_no=line.platform_order_no,
        order_line_no=line.order_line_no,
        gtin=line.gtin,
        item_id=line.item_id,
        sku=line.sku,
        msku=line.msku,
        owner_id=line.owner_id,
        posted_date=line.posted_date,
        quantity=f"{line.quantity:.4f}",
        transaction_types=list(line.transaction_types),
        sales=money(line.sales_usd, "USD") or _zero("USD"),
        refund=money(line.refund_usd, "USD") or _zero("USD"),
        promotion=money(line.promotion_usd, "USD") or _zero("USD"),
        commission=money(line.commission_usd, "USD") or _zero("USD"),
        return_fee=money(line.return_fee_usd, "USD") or _zero("USD"),
        tax_withheld=money(line.tax_withheld_usd, "USD") or _zero("USD"),
        wfs_fulfillment_fee=money(line.wfs_fulfillment_fee_usd, "USD") or _zero("USD"),
        mcf_fee=money(line.mcf_fee_usd, "USD") or _zero("USD"),
        settlement_amount=money(line.settlement_amount_usd, "USD") or _zero("USD"),
        purchase=money(line.purchase_cny, "CNY"),
        head=money(line.head_cny, "CNY"),
        last_leg=money(line.last_leg_cny, "CNY"),
        cost_total=money(line.cost_total_cny, "CNY"),
        cost_total_usd=money(line.cost_total_usd, "USD"),
        profit_usd=money(profit, "USD"),
        fx_rate=None if line.fx_rate is None else str(line.fx_rate),
        fx_status=line.fx_status,
        cost_sources=[CostSourceRead.model_validate(s) for s in line.cost_sources],
        cost_entry_ids=list(line.cost_entry_ids),
        reasons=list(line.reasons),
        auto_passed=line.auto_passed,
        review_status=review.review_status,
        review_reasons=list(review.reasons or []),
        first_reviewed_by=review.first_reviewed_by,
        first_reviewed_at=review.first_reviewed_at,
        final_reviewed_by=review.final_reviewed_by,
        final_reviewed_at=review.final_reviewed_at,
        version=review.version,
        calc_version=line.calc_version,
    )


def _zero(currency: str) -> Any:
    return money(Decimal("0"), currency)


def lookup(session: Session, *, kind: str, q: str, limit: int) -> LookupData:
    columns = {
        "item_id": SettlementOrderLine.item_id,
        "sku": SettlementOrderLine.sku,
        "msku": SettlementOrderLine.msku,
        "order_no": SettlementOrderLine.platform_order_no,
    }
    if kind not in columns:
        raise OrderReviewError(422, ERR_VALIDATION, "kind 只能是 item_id / sku / msku / order_no")
    limit = max(1, min(limit, LOOKUP_LIMIT))
    column = columns[kind]
    statement = (
        select(column)
        .where(
            SettlementOrderLine.source_account_ref == SOURCE_REF,
            SettlementOrderLine.is_current.is_(True),
            column.is_not(None),
        )
        .distinct()
        .order_by(column)
        .limit(limit + 1)
    )
    text = (q or "").strip()
    if text:
        statement = statement.where(column.ilike(f"%{text}%"))
    values = [v for v in session.scalars(statement).all() if v]
    return LookupData(kind=kind, items=values[:limit], truncated=len(values) > limit)


def transaction_types(session: Session) -> list[TransactionTypeRead]:
    """当前订单行里实际出现过的交易类型，附中文名；没翻译的 translated=false。"""
    element = (
        func.jsonb_array_elements_text(cast(SettlementOrderLine.transaction_types, JSONB))
        .table_valued("value")
        .lateral("tx")
    )
    rows = session.execute(
        select(element.c.value)
        .select_from(SettlementOrderLine)
        .join(element, true())
        .where(
            SettlementOrderLine.source_account_ref == SOURCE_REF,
            SettlementOrderLine.is_current.is_(True),
        )
        .distinct()
        .order_by(element.c.value)
    ).all()
    out: list[TransactionTypeRead] = []
    for (code,) in rows:
        parts = (str(code).split("|") + ["", "", ""])[:3]
        info = describe(*parts)
        out.append(
            TransactionTypeRead(
                code=str(code),
                name_zh=info.name_zh if info else None,
                name_en=english_name(*parts),
                category=info.category if info else "store",
                translated=info is not None,
            )
        )
    return out


# --------------------------------------------------------------------------- 录成本


def _affected_lines(
    session: Session, *, store_id: str, msku: str, scope_ref: str
) -> list[SettlementOrderLine]:
    probe = [{"msku": msku, "scope_ref": scope_ref}]
    return list(
        session.scalars(
            select(SettlementOrderLine).where(
                SettlementOrderLine.source_account_ref == SOURCE_REF,
                SettlementOrderLine.store_id == store_id,
                SettlementOrderLine.is_current.is_(True),
                cast(SettlementOrderLine.cost_sources, JSONB).contains(probe),
            )
        ).all()
    )


def _recalc_lines(session: Session, lines: Iterable[SettlementOrderLine]) -> int:
    periods = sorted({(line.store_id, line.period_key) for line in lines})
    calculator = OrderReviewCalculator(session, source_account_ref=SOURCE_REF)
    for store_id, period_key in periods:
        calculator.recalc_period(store_id, period_key)
    return len(periods)


def entry_read(entry: SettlementCostEntry) -> CostEntryRead:
    return CostEntryRead(
        id=entry.id,
        store_id=entry.store_id,
        msku=entry.msku,
        scope_ref=entry.scope_ref,
        shipping_list_code=entry.shipping_list_code,
        outbound_order_no=entry.outbound_order_no,
        platform_order_no=entry.platform_order_no,
        entry_kind=entry.entry_kind,
        purchase_cny=None if entry.purchase_cny is None else f"{entry.purchase_cny:.4f}",
        head_cny=None if entry.head_cny is None else f"{entry.head_cny:.4f}",
        last_leg_cny=None if entry.last_leg_cny is None else f"{entry.last_leg_cny:.4f}",
        reason=entry.reason,
        status=entry.status,
        version=entry.version,
        actor_id=entry.actor_id,
        created_at=entry.created_at,
    )


def create_cost_entry(
    session: Session,
    payload: CostEntryCreate,
    *,
    actor: str,
    actor_role: str,
    request_id: str | None,
    idempotency_key: str | None,
) -> CostEntryResult:
    try:
        scope_ref = payload.scope.scope_ref()
    except ValueError as exc:
        raise OrderReviewError(422, ERR_VALIDATION, "录入范围要给发货单号或出库单号") from exc
    if payload.entry_kind == "override" and not (payload.reason or "").strip():
        raise OrderReviewError(422, ERR_VALIDATION, "修正必须填原因")
    if payload.purchase_cny is None and payload.head_cny is None and payload.last_leg_cny is None:
        raise OrderReviewError(422, ERR_VALIDATION, "至少录一项成本")
    key = (idempotency_key or "").strip() or None
    if key:
        existing = session.scalars(
            select(SettlementCostEntry).where(SettlementCostEntry.idempotency_key == key)
        ).one_or_none()
        if existing is not None:
            return CostEntryResult(
                entry=entry_read(existing), affected_lines=0, recalculated_periods=0, replayed=True
            )
    active = session.scalars(
        select(SettlementCostEntry).where(
            SettlementCostEntry.store_id == payload.store_id,
            SettlementCostEntry.msku == payload.scope.msku,
            SettlementCostEntry.scope_ref == scope_ref,
            SettlementCostEntry.status != "revoked",
        )
    ).one_or_none()
    if active is not None:
        raise OrderReviewError(409, ERR_ENTRY_EXISTS, "这个范围已有未撤销的录入，先撤销再录")
    lines = _affected_lines(
        session, store_id=payload.store_id, msku=payload.scope.msku, scope_ref=scope_ref
    )
    for line in lines:
        if month_is_closed(session, store_id=line.store_id, bill_month=line.bill_month):
            raise OrderReviewError(409, ERR_MONTH_CLOSED, "该月已结账，先解锁")
    prefilled: dict[str, Any] = {}
    for line in lines:
        for source in line.cost_sources:
            if source.get("scope_ref") == scope_ref and source.get("msku") == payload.scope.msku:
                prefilled = {
                    k: source.get(k)
                    for k in ("purchase_cny", "head_cny", "last_leg_cny", "prefill", "kind")
                }
                break
        if prefilled:
            break
    entry = SettlementCostEntry(
        id=uuid4(),
        store_id=payload.store_id,
        msku=payload.scope.msku,
        shipping_list_code=payload.scope.shipping_list_code,
        outbound_order_no=payload.scope.outbound_order_no,
        platform_order_no=payload.scope.platform_order_no,
        scope_ref=scope_ref,
        purchase_cny=payload.purchase_cny,
        head_cny=payload.head_cny,
        last_leg_cny=payload.last_leg_cny,
        entry_kind=payload.entry_kind,
        reason=(payload.reason or "").strip() or None,
        prefilled=prefilled,
        status="pending_first",
        idempotency_key=key,
        actor_id=actor,
        actor_role=actor_role,
        request_id=request_id,
    )
    session.add(entry)
    try:
        session.flush()
    except IntegrityError as exc:
        # 两个请求同时通过了上面的检查：撞部分唯一索引的那个转成 409（#373 复审 P3-7）
        session.rollback()
        raise OrderReviewError(
            409, ERR_ENTRY_EXISTS, "这个范围已有未撤销的录入，先撤销再录"
        ) from exc
    periods = _recalc_lines(session, lines)
    session.commit()
    return CostEntryResult(
        entry=entry_read(entry), affected_lines=len(lines), recalculated_periods=periods
    )


def get_cost_entry(session: Session, entry_id: UUID) -> CostEntryRead:
    entry = session.get(SettlementCostEntry, entry_id)
    if entry is None:
        raise OrderReviewError(404, ERR_NOT_FOUND, "没有这条录入")
    return entry_read(entry)


def revoke_cost_entry(
    session: Session,
    entry_id: UUID,
    payload: CostEntryRevoke,
    *,
    actor: str,
    actor_role: str,
    request_id: str | None,
    idempotency_key: str | None = None,
) -> CostEntryResult:
    del actor_role, request_id
    entry = session.get(SettlementCostEntry, entry_id)
    if entry is None:
        raise OrderReviewError(404, ERR_NOT_FOUND, "没有这条录入")
    key = (idempotency_key or "").strip() or None
    if entry.status == "revoked":
        if key and entry.revoke_idempotency_key == key:
            return CostEntryResult(
                entry=entry_read(entry), affected_lines=0, recalculated_periods=0, replayed=True
            )
        raise OrderReviewError(409, ERR_ALREADY_REVOKED, "这条录入已经撤销")
    if entry.version != payload.expected_version:
        raise OrderReviewError(409, ERR_STALE_VERSION, "数据已被他人修改，请刷新")
    lines = _affected_lines(
        session, store_id=entry.store_id, msku=entry.msku, scope_ref=entry.scope_ref
    )
    for line in lines:
        if month_is_closed(session, store_id=line.store_id, bill_month=line.bill_month):
            raise OrderReviewError(409, ERR_MONTH_CLOSED, "该月已结账，先解锁")
    entry.status = "revoked"
    entry.revoked_by = actor
    entry.revoked_at = utc_now()
    entry.revoke_reason = payload.reason.strip()
    entry.revoke_idempotency_key = key
    entry.version += 1
    session.flush()
    # 撤销后订单行回到待审：已初审 / 终审的行也退回（§8.4 撤销回到待审）
    for line in lines:
        review = session.scalars(
            select(SettlementOrderReview).where(
                SettlementOrderReview.store_id == line.store_id,
                SettlementOrderReview.period_key == line.period_key,
                SettlementOrderReview.line_key == line.line_key,
            )
        ).one_or_none()
        if review is not None and review.review_status in {"first_passed", "final_passed"}:
            review.review_status = "pending"
            review.first_reviewed_by = review.first_reviewed_at = None
            review.final_reviewed_by = review.final_reviewed_at = None
            review.reasons = [r for r in review.reasons if r != CHANGED_AFTER_REVIEW]
            review.version += 1
    periods = _recalc_lines(session, lines)
    session.commit()
    return CostEntryResult(
        entry=entry_read(entry), affected_lines=len(lines), recalculated_periods=periods
    )


# --------------------------------------------------------------------------- 审核


def review_lines(
    session: Session,
    payload: ReviewRequest,
    *,
    actor: str,
    actor_role: str,
    request_id: str | None,
    idempotency_key: str | None = None,
) -> ReviewResultData:
    if payload.decision in {"reject"} and not (payload.comment or "").strip():
        raise OrderReviewError(422, ERR_VALIDATION, "退回必须填原因")
    if (
        len(payload.review_ids) >= BATCH_CONFIRM_THRESHOLD
        and payload.confirm_token != BATCH_CONFIRM_TOKEN
    ):
        raise OrderReviewError(
            409, ERR_CONFIRM_REQUIRED, f"批量审核 {BATCH_CONFIRM_THRESHOLD} 行以上要二次确认"
        )
    key = (idempotency_key or "").strip() or None
    if key:
        replay = _replay_review(session, key, actor)
        if replay is not None:
            return replay
    reviews = {
        row.id: row
        for row in session.scalars(
            select(SettlementOrderReview)
            .where(SettlementOrderReview.id.in_(list(payload.review_ids)))
            .with_for_update()
        ).all()
    }
    lines = {
        (line.store_id, line.period_key, line.line_key): line
        for line in session.scalars(
            select(SettlementOrderLine).where(
                SettlementOrderLine.is_current.is_(True),
                SettlementOrderLine.line_key.in_([r.line_key for r in reviews.values()]),
            )
        ).all()
    }
    items: list[ReviewLineResult] = []
    for review_id in payload.review_ids:
        review = reviews.get(review_id)
        if review is None:
            items.append(
                ReviewLineResult(
                    review_id=review_id,
                    line_key="",
                    ok=False,
                    review_status="",
                    version=0,
                    error_code=ERR_NOT_FOUND,
                    message="没有这一行",
                )
            )
            continue
        line = lines.get((review.store_id, review.period_key, review.line_key))
        try:
            _apply_review(session, review, line, payload, actor, actor_role, request_id, key)
        except OrderReviewError as exc:
            items.append(
                ReviewLineResult(
                    review_id=review.id,
                    line_key=review.line_key,
                    ok=False,
                    review_status=review.review_status,
                    version=review.version,
                    error_code=exc.code,
                    message=exc.message,
                )
            )
            continue
        items.append(
            ReviewLineResult(
                review_id=review.id,
                line_key=review.line_key,
                ok=True,
                review_status=review.review_status,
                version=review.version,
            )
        )
    session.commit()
    succeeded = sum(1 for i in items if i.ok)
    return ReviewResultData(items=items, succeeded=succeeded, failed=len(items) - succeeded)


def _replay_review(session: Session, key: str, actor: str) -> ReviewResultData | None:
    """同一人同一个 Idempotency-Key 已经处理过：按当时的审核记录重放结果，不再改任何状态。"""
    actions = session.scalars(
        select(SettlementReviewAction)
        .where(
            SettlementReviewAction.idempotency_key == key,
            SettlementReviewAction.actor_id == actor,
        )
        .order_by(SettlementReviewAction.acted_at)
    ).all()
    if not actions:
        return None
    items = [
        ReviewLineResult(
            review_id=action.target_id or uuid4(),
            line_key=action.line_key,
            ok=True,
            review_status=str(action.after.get("review_status", "")),
            version=int(action.after.get("version", 0)),
        )
        for action in actions
    ]
    return ReviewResultData(items=items, succeeded=len(items), failed=0)


def _sync_entry_status(session: Session, line: SettlementOrderLine | None, status: str) -> None:
    """审核结论同步到这一行用到的录入记录（§8.4 录入后进初审 / 终审；撤销回到待初审）。"""
    if line is None or not line.cost_entry_ids:
        return
    ids: list[UUID] = []
    for raw in line.cost_entry_ids:
        try:
            ids.append(UUID(str(raw)))
        except ValueError:
            continue
    if not ids:
        return
    for entry in session.scalars(
        select(SettlementCostEntry).where(
            SettlementCostEntry.id.in_(ids), SettlementCostEntry.status != "revoked"
        )
    ).all():
        entry.status = status


_ENTRY_STATUS_BY_REVIEW: Final[dict[str, str]] = {
    "pending": "pending_first",
    "first_passed": "first_passed",
    "final_passed": "final_passed",
    "rejected": "rejected",
}


def _apply_review(
    session: Session,
    review: SettlementOrderReview,
    line: SettlementOrderLine | None,
    payload: ReviewRequest,
    actor: str,
    actor_role: str,
    request_id: str | None,
    idempotency_key: str | None = None,
) -> None:
    if month_is_closed(session, store_id=review.store_id, bill_month=review.bill_month):
        raise OrderReviewError(409, ERR_MONTH_CLOSED, "该月已结账，先解锁")
    status = review.review_status
    before = {"review_status": status, "version": review.version}
    if payload.decision == "revert":
        if status not in {"first_passed", "final_passed", "rejected"}:
            raise OrderReviewError(409, ERR_STAGE_ORDER, "这一行没有可撤销的审核")
        if payload.stage == "final" and status != "final_passed":
            raise OrderReviewError(409, ERR_STAGE_ORDER, "这一行没有终审可撤销")
        if payload.stage == "first" and status == "final_passed":
            raise OrderReviewError(409, ERR_STAGE_ORDER, "先撤销终审再撤销初审")
        if payload.stage == "final" and status == "final_passed":
            new_status = "first_passed"
        else:
            new_status = "pending"
        if payload.stage == "final":
            review.final_reviewed_by = None
            review.final_reviewed_at = None
        else:
            review.first_reviewed_by = None
            review.first_reviewed_at = None
    elif payload.decision == "reject":
        if status == "auto":
            raise OrderReviewError(409, ERR_ALREADY_PASSED, "自动通过的行不需要审核")
        if status == "final_passed":
            raise OrderReviewError(409, ERR_STAGE_ORDER, "已终审的行先撤销终审")
        if payload.stage == "final" and status != "first_passed":
            raise OrderReviewError(409, ERR_STAGE_ORDER, "终审前须初审")
        new_status = "rejected"
    else:
        if status == "auto":
            raise OrderReviewError(409, ERR_ALREADY_PASSED, "自动通过的行不需要审核")
        if line is not None and line.reasons and line.cost_total_cny is None:
            raise OrderReviewError(409, ERR_COST_MISSING, "先录成本再审核")
        if payload.stage == "first":
            if status not in {"pending", "rejected"}:
                raise OrderReviewError(409, ERR_STAGE_ORDER, "这一行不在待初审状态")
            review.first_reviewed_by = actor
            review.first_reviewed_at = utc_now()
            new_status = "first_passed"
        else:
            if status != "first_passed":
                raise OrderReviewError(409, ERR_STAGE_ORDER, "终审前须初审")
            if review.first_reviewed_by == actor:
                raise OrderReviewError(409, ERR_SAME_REVIEWER, "同一人不能既初审又终审")
            review.final_reviewed_by = actor
            review.final_reviewed_at = utc_now()
            new_status = "final_passed"
    review.review_status = new_status
    review.version += 1
    review.updated_at = utc_now()
    # 任何一次审核动作都算「财务看过了」：清掉差异提示
    review.reasons = [r for r in review.reasons if r != CHANGED_AFTER_REVIEW]
    _sync_entry_status(session, line, _ENTRY_STATUS_BY_REVIEW[new_status])
    session.add(
        SettlementReviewAction(
            id=uuid4(),
            store_id=review.store_id,
            bill_month=review.bill_month,
            period_key=review.period_key,
            idempotency_key=idempotency_key,
            target_kind="order_line",
            target_id=review.id,
            line_key=review.line_key,
            stage=payload.stage,
            decision=payload.decision,
            comment=(payload.comment or "").strip() or None,
            before=before,
            after={"review_status": new_status, "version": review.version},
            acted_at=utc_now(),
            actor_id=actor,
            actor_role=actor_role,
            request_id=request_id,
        )
    )
    session.flush()


# --------------------------------------------------------------------------- 重算


def recalc(session: Session, payload: RecalcRequest) -> RecalcResultData:
    pairs = periods_for_recalc(
        session,
        source_account_ref=SOURCE_REF,
        store_ids=payload.store_ids,
        report_date_from=payload.report_date_from,
    )
    if payload.period_keys:
        wanted = set(payload.period_keys)
        pairs = [(s, k) for s, k in pairs if k in wanted]
    calculator = OrderReviewCalculator(session, source_account_ref=SOURCE_REF)
    results: list[RecalcResult] = []
    for store_id, period_key in pairs:
        results.append(calculator.recalc_period(store_id, period_key))
        session.commit()
    return RecalcResultData(
        items=[
            RecalcPeriodResult(
                store_id=r.store_id,
                period_key=r.period_key,
                status=r.status,
                lines_total=r.lines_total,
                lines_new_version=r.lines_new_version,
                lines_unchanged=r.lines_unchanged,
                lines_retired=r.lines_retired,
                auto_passed=r.auto_passed,
                pending=r.pending,
                calc_version=r.calc_version,
            )
            for r in results
        ],
        periods_total=len(results),
    )
