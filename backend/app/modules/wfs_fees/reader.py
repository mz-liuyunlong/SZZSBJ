"""WFS 费用明细只读查询：列表（原行带分摊子行）、汇总、核对、文件记录。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.walmart_bills.models import WalmartBillPeriod
from app.modules.walmart_bills.payout_service import store_code
from app.modules.wfs_fees.models import (
    WalmartWfsFeeAdjustment,
    WalmartWfsFeeCheck,
    WalmartWfsFeeFile,
    WalmartWfsFeeLine,
)
from app.modules.wfs_fees.schemas import (
    WfsFeeCheckRead,
    WfsFeeFileRead,
    WfsFeeLineRead,
    WfsFeePeriodRead,
    WfsFeeSummaryRow,
    WfsFeeTypeRead,
)

MAX_PAGE_SIZE: Final = 1000  # 和报表通用分页一致：50 / 100 / 200 / 500 / 1000


def _many(value: str | None) -> list[str]:
    """筛选参数都可多选：逗号分隔。"""
    return [v for v in (value or "").split(",") if v]


MAX_PERIODS: Final = 2000

# 费用类型中文名（和 7~10 月手工表一致）；报表里新出现的类型照原名显示
FEE_TYPE_NAMES: Final[dict[str, tuple[str, str]]] = {
    "Refund": ("费用返还", "settlement"),
    "PrepServiceFee": ("预处理费", "settlement"),
    "MultiChannelFulfillmentFee": ("多渠道履约费", "settlement"),
    "LostInventory": ("丢失赔付", "settlement"),
    "InventoryTransferFee": ("库存调拨费", "settlement"),
    "InventoryRemovalOrder": ("移除费", "settlement"),
    "InventoryDisposalOrder": ("弃置费", "settlement"),
    "FoundInventory": ("找回冲回", "settlement"),
    "DiscountAdjustment": ("新卖家补贴返还", "settlement"),
    "DamageInWarehouse": ("仓内损坏赔付", "settlement"),
    "RC_InventoryDisposalFee": ("退货中心弃置费", "settlement"),
    "Charge": ("其他扣费", "settlement"),
    "WFSWalmartFaultReturnRestockedFee": ("沃尔玛责任退货重上架费", "settlement"),
    "ReturnProcessingFee": ("退货处理费", "settlement"),
    "StorageFee": ("仓储费", "storage"),
    "InboundTransportationFee": ("入库运输费", "inbound"),
}


def fee_types() -> list[WfsFeeTypeRead]:
    return [
        WfsFeeTypeRead(code=code, name=name, source=source)
        for code, (name, source) in FEE_TYPE_NAMES.items()
    ]


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.4f}"


def _line(row: WalmartWfsFeeLine, adjusted: set[UUID]) -> WfsFeeLineRead:
    return WfsFeeLineRead(
        id=row.id,
        store_id=row.store_id,
        fee_source=row.fee_source,
        fee_type=row.fee_type,
        reason_code=row.reason_code,
        detail=row.detail,
        source_ref=row.source_ref,
        transaction_date=row.transaction_date,
        date_charged=row.date_charged,
        period_start=row.period_start,
        period_end=row.period_end,
        report_key=row.report_key,
        report_date=row.report_date,
        bill_match=row.bill_match,
        po_number=row.po_number,
        partner_id=row.partner_id,
        gtin=row.gtin,
        item_id=row.item_id,
        msku=row.msku,
        local_sku=row.local_sku,
        quantity=_money(row.quantity),
        amount_usd=_money(row.amount_usd) or "0",
        original_amount=_money(row.original_amount),
        discount_savings=_money(row.discount_savings),
        attribution=row.attribution,
        allocation_basis=row.allocation_basis,
        parent_line_id=row.parent_line_id,
        missing_since=row.missing_since,
        raw_file_id=row.raw_file_id,
        adjusted=row.id in adjusted,
    )


@dataclass(frozen=True)
class LineFilter:
    """明细、合计共用的一套筛选（复审 P2-7：页面上的合计和表格同一口径）。都可逗号分隔多选。"""

    store_id: str | None = None
    report_key: str | None = None
    fee_type: str | None = None
    fee_source: str | None = None
    attribution: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None
    include_missing: bool = False
    split: str | None = None


def _apply(query, f: LineFilter):  # type: ignore[no-untyped-def]
    query = query.where(WalmartWfsFeeLine.parent_line_id.is_(None))
    if not f.include_missing:
        query = query.where(WalmartWfsFeeLine.missing_since.is_(None))
    if f.store_id:
        query = query.where(WalmartWfsFeeLine.store_id.in_(_many(f.store_id)))
    if f.report_key:
        query = query.where(WalmartWfsFeeLine.report_key.in_(_many(f.report_key)))
    if f.fee_type:
        query = query.where(WalmartWfsFeeLine.fee_type.in_(_many(f.fee_type)))
    if f.fee_source:
        query = query.where(WalmartWfsFeeLine.fee_source.in_(_many(f.fee_source)))
    if f.attribution:
        query = query.where(WalmartWfsFeeLine.attribution.in_(_many(f.attribution)))
    wanted = set(_many(f.split))
    if wanted and wanted != {"yes", "no"}:
        # 有分摊 = 原行下有分摊子行（财务检查分摊用）
        child = WalmartWfsFeeLine.__table__.alias("child")
        has_children = exists().where(child.c.parent_line_id == WalmartWfsFeeLine.id)
        query = query.where(has_children if wanted == {"yes"} else ~has_children)
    if f.date_from:
        query = query.where(WalmartWfsFeeLine.date_charged >= f.date_from)
    if f.date_to:
        query = query.where(WalmartWfsFeeLine.date_charged <= f.date_to)
    if f.q:
        needle = f"%{f.q.strip()}%"
        child_hit = select(WalmartWfsFeeLine.parent_line_id).where(
            WalmartWfsFeeLine.parent_line_id.is_not(None),
            or_(
                WalmartWfsFeeLine.item_id.ilike(needle),
                WalmartWfsFeeLine.msku.ilike(needle),
                WalmartWfsFeeLine.local_sku.ilike(needle),
                WalmartWfsFeeLine.gtin.ilike(needle),
            ),
        )
        query = query.where(
            or_(
                WalmartWfsFeeLine.item_id.ilike(needle),
                WalmartWfsFeeLine.msku.ilike(needle),
                WalmartWfsFeeLine.local_sku.ilike(needle),
                WalmartWfsFeeLine.gtin.ilike(needle),
                WalmartWfsFeeLine.po_number.ilike(needle),
                WalmartWfsFeeLine.source_ref.ilike(needle),
                WalmartWfsFeeLine.id.in_(child_hit),
            )
        )
    return query


def list_lines(
    session: Session, f: LineFilter, *, page: int, page_size: int
) -> tuple[list[WfsFeeLineRead], int]:
    """原行分页；每个原行带它的分摊子行。"""
    query = _apply(select(WalmartWfsFeeLine), f)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    rows = list(
        session.scalars(
            query.order_by(
                WalmartWfsFeeLine.date_charged.desc(),
                WalmartWfsFeeLine.store_id,
                WalmartWfsFeeLine.fee_type,
                WalmartWfsFeeLine.transaction_date.desc(),
                WalmartWfsFeeLine.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    ids = [row.id for row in rows]
    children: dict[UUID, list[WalmartWfsFeeLine]] = defaultdict(list)
    adjusted: set[UUID] = set()
    if ids:
        for child_row in session.scalars(
            select(WalmartWfsFeeLine)
            .where(WalmartWfsFeeLine.parent_line_id.in_(ids))
            .order_by(WalmartWfsFeeLine.amount_usd)
        ):
            children[child_row.parent_line_id].append(child_row)  # type: ignore[index]
        adjusted = set(
            session.scalars(
                select(WalmartWfsFeeAdjustment.line_id).where(
                    WalmartWfsFeeAdjustment.line_id.in_(ids)
                )
            )
        )
    out = []
    for row in rows:
        item = _line(row, adjusted)
        item.children = [_line(c, adjusted) for c in children.get(row.id, [])]
        out.append(item)
    return out, int(total)


def get_line(session: Session, line_id: UUID) -> WfsFeeLineRead | None:
    row = session.get(WalmartWfsFeeLine, line_id)
    if row is None:
        return None
    adjusted = set(
        session.scalars(
            select(WalmartWfsFeeAdjustment.line_id).where(
                WalmartWfsFeeAdjustment.line_id == line_id
            )
        )
    )
    item = _line(row, adjusted)
    item.children = [
        _line(c, adjusted)
        for c in session.scalars(
            select(WalmartWfsFeeLine)
            .where(WalmartWfsFeeLine.parent_line_id == line_id)
            .order_by(WalmartWfsFeeLine.amount_usd)
        )
    ]
    return item


def summary(session: Session, f: LineFilter) -> tuple[list[WfsFeeSummaryRow], Decimal]:
    """店铺 × 账单期 × 费用类型 合计；筛选和明细同一套。"""
    query = (
        _apply(
            select(
                WalmartWfsFeeLine.store_id,
                WalmartWfsFeeLine.report_key,
                WalmartWfsFeeLine.report_date,
                WalmartWfsFeeLine.fee_type,
                func.count(),
                func.sum(WalmartWfsFeeLine.amount_usd),
            ),
            f,
        )
        .group_by(
            WalmartWfsFeeLine.store_id,
            WalmartWfsFeeLine.report_key,
            WalmartWfsFeeLine.report_date,
            WalmartWfsFeeLine.fee_type,
        )
        .order_by(
            WalmartWfsFeeLine.report_date.desc(),
            WalmartWfsFeeLine.store_id,
            WalmartWfsFeeLine.fee_type,
        )
    )
    rows = session.execute(query).all()
    total = sum((amount or Decimal("0") for *_, amount in rows), Decimal("0"))
    return [
        WfsFeeSummaryRow(
            store_id=s,
            report_key=rk,
            report_date=rd,
            fee_type=ft,
            rows=int(n),
            amount_usd=f"{(amount or 0):.4f}",
        )
        for s, rk, rd, ft, n, amount in rows
    ], total


def total_quantity(session: Session, f: LineFilter) -> Decimal:
    """数量合计（页面底部合计行用），筛选和明细同一套。"""
    value = session.scalar(_apply(select(func.sum(WalmartWfsFeeLine.quantity)), f))
    return value or Decimal("0")


def list_checks(
    session: Session, *, store_id: str | None, report_key: str | None, only_problem: bool
) -> list[WfsFeeCheckRead]:
    query = select(WalmartWfsFeeCheck).order_by(
        WalmartWfsFeeCheck.report_date.desc(),
        WalmartWfsFeeCheck.store_id,
        WalmartWfsFeeCheck.fee_type,
    )
    if store_id:
        query = query.where(WalmartWfsFeeCheck.store_id.in_(_many(store_id)))
    if report_key:
        query = query.where(WalmartWfsFeeCheck.report_key.in_(_many(report_key)))
    if only_problem:
        query = query.where(
            WalmartWfsFeeCheck.status != "ok", WalmartWfsFeeCheck.verified_at.is_(None)
        )
    return [
        WfsFeeCheckRead(
            store_id=c.store_id,
            report_key=c.report_key,
            fee_type=c.fee_type,
            report_date=c.report_date,
            lingxing_amount=_money(c.lingxing_amount),
            lingxing_rows=c.lingxing_rows,
            report_amount=_money(c.report_amount),
            report_rows=c.report_rows,
            status=c.status,
            verified_reason=c.verified_reason,
            verified_by=c.verified_by,
            verified_at=c.verified_at,
            refreshed_at=c.refreshed_at,
        )
        for c in session.scalars(query.limit(MAX_PAGE_SIZE))
    ]


def list_periods(session: Session, source_account_ref: str) -> list[WfsFeePeriodRead]:
    """领星同步的沃尔玛账单期（新到旧，最多 MAX_PERIODS 期）。

    只有费用行、还没账单的店铺也给一行（没有账单期）。
    """
    rows = session.execute(
        select(
            WalmartBillPeriod.store_id,
            WalmartBillPeriod.store_name,
            WalmartBillPeriod.report_key,
            WalmartBillPeriod.report_date,
            WalmartBillPeriod.period_start_date,
            WalmartBillPeriod.period_end_date,
        )
        .where(WalmartBillPeriod.source_account_ref == source_account_ref)
        .order_by(WalmartBillPeriod.report_date.desc(), WalmartBillPeriod.store_id)
        .limit(MAX_PERIODS)
    ).all()
    items = [
        WfsFeePeriodRead(
            store_id=sid,
            store_code=store_code(name, sid),
            store_name=name,
            report_key=key,
            report_date=report_date,
            period_start_date=start,
            period_end_date=end,
        )
        for sid, name, key, report_date, start, end in rows
    ]
    # 还没有账单的店铺也要能选（导入时选店铺）：领星店铺表里的沃尔玛店铺 + 已有费用行的店铺
    known = {item.store_id for item in items}
    stores = session.execute(
        select(LingxingStoreDimension.store_id, LingxingStoreDimension.store_name).where(
            LingxingStoreDimension.source_account_ref == source_account_ref,
            LingxingStoreDimension.platform_code == "walmart",
        )
    ).all()
    names = {sid: name for sid, name in stores}
    extra = session.scalars(
        select(WalmartWfsFeeLine.store_id)
        .where(WalmartWfsFeeLine.source_account_ref == source_account_ref)
        .distinct()
    ).all()
    for sid in sorted((set(names) | set(extra)) - known):
        name = names.get(sid)
        items.append(
            WfsFeePeriodRead(
                store_id=sid,
                store_code=store_code(name, sid),
                store_name=name,
                report_key=None,
                report_date=None,
                period_start_date=None,
                period_end_date=None,
            )
        )
    return items


def list_files(
    session: Session, *, store_id: str | None, fee_source: str | None
) -> list[WfsFeeFileRead]:
    query = (
        select(WalmartWfsFeeFile).order_by(WalmartWfsFeeFile.created_at.desc()).limit(MAX_PAGE_SIZE)
    )
    if store_id:
        query = query.where(WalmartWfsFeeFile.store_id.in_(_many(store_id)))
    if fee_source:
        query = query.where(WalmartWfsFeeFile.fee_source.in_(_many(fee_source)))
    return [
        WfsFeeFileRead(
            id=f.id,
            store_id=f.store_id,
            fee_source=f.fee_source,
            origin=f.origin,
            file_name=f.file_name,
            period_start=f.period_start,
            period_end=f.period_end,
            declared_total=_money(f.declared_total),
            row_count=f.row_count,
            rows_new=f.rows_new,
            rows_duplicate=f.rows_duplicate,
            status=f.status,
            reject_reason=f.reject_reason,
            actor=f.actor,
            created_at=f.created_at,
        )
        for f in session.scalars(query)
    ]
