"""订单审核计算的数据库层：一店一期读账单明细，查各来源表，写 FACT / MART（PRP §8.1）。

- 同一输入重算内容 hash 不变就不写新版本；变了同一事务里把旧版本 is_current=false 再插新版本
  （#365 复审意见）。
- 已结账的月不重算（本 PR 只跳过并计数；结账后差异由结算利润 PR 写）。
- 审核页行（mart_settlement_order_review）按 line_key upsert：已初审 / 终审的行不自动改状态。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.fx_rates.reader import load_usd_cny_rates, month_key
from app.modules.settlement_profit.models import (
    FinShippingDetailItem,
    FinShippingList,
    FinWmsOutboundOrder,
    OwnerTagRule,
    SettlementCostEntry,
    SettlementMonthClose,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementSetting,
)
from app.modules.settlement_profit.order_review.rules import (
    BillRow,
    ComputedLine,
    CostEntry,
    FlowSegment,
    Lookups,
    OriginalLine,
    OutboundItem,
    OutboundOrder,
    ReviewSettings,
    ShipmentDetail,
    ShipmentHeader,
    bill_month_of,
    compute_line,
    group_order_rows,
    qty,
)
from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod
from app.modules.warehouse_wfs.inventory_flow_models import WfsCostValuationFlowOds

DEFAULT_CUTOFF_DAY = 5
# 审核行上的差异提示（不是订单行的待审原因）：已初审 / 终审后计算值变了
CHANGED_AFTER_REVIEW = "changed_after_review"


class OrderReviewCalcError(RuntimeError):
    """Safe error code only."""


@dataclass(slots=True)
class RecalcResult:
    store_id: str
    period_key: str
    status: str  # calculated / skipped_closed / no_period
    lines_total: int = 0
    lines_new_version: int = 0
    lines_unchanged: int = 0
    lines_retired: int = 0
    auto_passed: int = 0
    pending: int = 0
    calc_version: int = 0
    notes: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- 设置


def load_settings(session: Session, *, bill_month: date) -> ReviewSettings:
    """按生效月取最近一条；没有就是「清单未配置」/ 默认分界日。"""

    def latest(key: str) -> dict[str, Any] | None:
        row = session.scalars(
            select(SettlementSetting)
            .where(
                SettlementSetting.setting_key == key,
                SettlementSetting.effective_month <= bill_month,
            )
            .order_by(SettlementSetting.effective_month.desc())
            .limit(1)
        ).one_or_none()
        return None if row is None else row.value

    carriers = latest("wfs_carrier_provider_ids")
    provider_ids: frozenset[str] | None = None
    if carriers is not None:
        raw = carriers.get("provider_ids")
        if isinstance(raw, list):
            provider_ids = frozenset(str(v).strip() for v in raw if str(v).strip())
    cutoff = latest("bill_month_cutoff_day")
    cutoff_day = DEFAULT_CUTOFF_DAY
    if cutoff is not None and isinstance(cutoff.get("day"), int) and 1 <= cutoff["day"] <= 28:
        cutoff_day = int(cutoff["day"])
    return ReviewSettings(wfs_carrier_provider_ids=provider_ids, bill_month_cutoff_day=cutoff_day)


def month_is_closed(session: Session, *, store_id: str, bill_month: date) -> bool:
    last = session.scalars(
        select(SettlementMonthClose.action)
        .where(
            SettlementMonthClose.store_id == store_id,
            SettlementMonthClose.bill_month == bill_month,
        )
        .order_by(SettlementMonthClose.seq.desc())
        .limit(1)
    ).one_or_none()
    return last == "close"


# --------------------------------------------------------------------------- 查表


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def _outbound_item(item: dict[str, Any]) -> OutboundItem:
    """出库单 items 一行（#370 保留的键）。

    seller_sku 即 MSKU；运费币种取 logistics_freight_currency_code。
    """
    msku = item.get("seller_sku")
    currency = item.get("logistics_freight_currency_code")
    return OutboundItem(
        msku=str(msku).strip() if msku not in (None, "") else None,
        count=_decimal(item.get("count")),
        apportion_freight=_decimal(item.get("apportion_freight")),
        currency_code=str(currency).strip() if currency not in (None, "") else None,
    )


class DbLookups(Lookups):
    def __init__(
        self,
        session: Session,
        *,
        source_account_ref: str,
        store_id: str,
        period_key: str,
        report_date: date,
    ) -> None:
        self.session = session
        self.account = source_account_ref
        self.store_id = store_id
        self.period_key = period_key
        self.report_date = report_date
        self._rates = load_usd_cny_rates(session)
        self._listing: dict[str, ListingManagementCurrentMart | None] = {}
        self._tag_rules: dict[str, str] | None = None
        self._details: dict[tuple[str, str], ShipmentDetail | None] = {}
        self._headers: dict[str, ShipmentHeader | None] = {}
        self._outbound: dict[str, list[OutboundOrder]] = {}
        self._entries: dict[tuple[str, str], CostEntry | None] = {}
        self._originals: dict[tuple[str, str, str], OriginalLine | None] = {}

    def flow_segments(self, order_nos: Iterable[str], gtin: str | None) -> list[FlowSegment]:
        numbers = [n for n in order_nos if n]
        if not numbers:
            return []
        # 只取出库方向（quantity < 0）：流水表全类型入库，客户退货入库行也带订单号，
        # 不能当成第二段发货（#373 复审 P2-1）。订单发货的 businessType 编码待首次探测后再收紧。
        statement = select(WfsCostValuationFlowOds).where(
            WfsCostValuationFlowOds.source_account_ref == self.account,
            WfsCostValuationFlowOds.is_current.is_(True),
            WfsCostValuationFlowOds.order_number.in_(numbers),
            WfsCostValuationFlowOds.quantity < 0,
            or_(
                WfsCostValuationFlowOds.store_id == self.store_id,
                WfsCostValuationFlowOds.store_id.is_(None),
            ),
        )
        if gtin:
            statement = statement.where(
                or_(
                    WfsCostValuationFlowOds.gtin == gtin,
                    WfsCostValuationFlowOds.gtin.is_(None),
                )
            )
        rows = self.session.scalars(
            statement.order_by(WfsCostValuationFlowOds.source_item_ordinal)
        ).all()
        return [
            FlowSegment(
                cost_source=row.cost_source,
                msku=row.msku,
                gtin=row.gtin,
                quantity=qty(abs(row.quantity)),
                business_number=row.business_number,
                business_type=row.business_type,
                purchase_total=row.purchase_total_amount,
                logistics_total=row.logistics_total_amount,
                other_total=row.other_total_amount,
                currency_code=row.currency_code,
                row_hash=row.row_hash,
            )
            for row in rows
        ]

    def shipment_detail(self, code: str, msku: str) -> ShipmentDetail | None:
        key = (code, msku)
        if key not in self._details:
            row = self.session.scalars(
                select(FinShippingDetailItem).where(
                    FinShippingDetailItem.source_account_ref == self.account,
                    FinShippingDetailItem.shipping_list_code == code,
                    FinShippingDetailItem.msku == msku,
                )
            ).one_or_none()
            self._details[key] = (
                None
                if row is None
                else ShipmentDetail(
                    shipping_list_code=code,
                    msku=msku,
                    purchase_price=row.purchase_price,
                    head_stock_price=row.head_stock_price,
                    per_firstlet_cost=row.per_firstlet_cost,
                    per_tax=row.per_tax,
                    wfs_stock_price=row.wfs_stock_price,
                    currency_code=row.currency_code,
                    logistics_way=row.logistics_way,
                )
            )
        return self._details[key]

    def shipment_header(self, code: str) -> ShipmentHeader | None:
        if code not in self._headers:
            rows = self.session.scalars(
                select(FinShippingList).where(
                    FinShippingList.source_account_ref == self.account,
                    FinShippingList.shipping_list_code == code,
                )
            ).all()
            # 多店发货单在每家店各有一行；优先本店那一行
            row = next((r for r in rows if r.store_id == self.store_id), rows[0] if rows else None)
            self._headers[code] = (
                None
                if row is None
                else ShipmentHeader(
                    shipping_list_code=code,
                    logistics_provider_id=row.logistics_provider_id,
                    logistics_provider_name=row.logistics_provider_name,
                )
            )
        return self._headers[code]

    def outbound_orders(self, platform_order_no: str) -> list[OutboundOrder]:
        # 一单拆多个包裹会有多张出库单：全部取回，按 MSKU 累加分摊运费（#373 P1，不再 limit 1）
        if platform_order_no not in self._outbound:
            rows = self.session.scalars(
                select(FinWmsOutboundOrder)
                .where(
                    FinWmsOutboundOrder.source_account_ref == self.account,
                    FinWmsOutboundOrder.store_id == self.store_id,
                    FinWmsOutboundOrder.platform_order_no == platform_order_no,
                )
                .order_by(
                    FinWmsOutboundOrder.outbound_at.asc().nulls_last(),
                    FinWmsOutboundOrder.outbound_order_no,
                )
            ).all()
            self._outbound[platform_order_no] = [
                OutboundOrder(
                    outbound_order_no=row.outbound_order_no,
                    logistics_fee=row.logistics_fee,
                    currency_code=row.currency_code,
                    items=tuple(_outbound_item(item) for item in row.items or [] if item),
                )
                for row in rows
            ]
        return self._outbound[platform_order_no]

    def cost_entry(self, msku: str, scope_ref: str) -> CostEntry | None:
        key = (msku, scope_ref)
        if key not in self._entries:
            row = self.session.scalars(
                select(SettlementCostEntry).where(
                    SettlementCostEntry.store_id == self.store_id,
                    SettlementCostEntry.msku == msku,
                    SettlementCostEntry.scope_ref == scope_ref,
                    SettlementCostEntry.status != "revoked",
                )
            ).one_or_none()
            self._entries[key] = (
                None
                if row is None
                else CostEntry(
                    id=str(row.id),
                    msku=row.msku,
                    scope_ref=row.scope_ref,
                    purchase_cny=row.purchase_cny,
                    head_cny=row.head_cny,
                    last_leg_cny=row.last_leg_cny,
                    entry_kind=row.entry_kind,
                    status=row.status,
                )
            )
        return self._entries[key]

    def _listing_for(self, item_id: str | None) -> ListingManagementCurrentMart | None:
        if not item_id:
            return None
        if item_id not in self._listing:
            self._listing[item_id] = self.session.scalars(
                select(ListingManagementCurrentMart)
                .where(
                    ListingManagementCurrentMart.source_account_ref == self.account,
                    ListingManagementCurrentMart.store_id == self.store_id,
                    ListingManagementCurrentMart.item_id == item_id,
                )
                .limit(1)
            ).one_or_none()
        return self._listing[item_id]

    def _rules(self) -> dict[str, str]:
        if self._tag_rules is None:
            rows = self.session.execute(
                select(OwnerTagRule.tag_name, OwnerTagRule.owner_id).where(
                    OwnerTagRule.is_active.is_(True)
                )
            ).all()
            self._tag_rules = {name.strip(): owner for name, owner in rows if name}
        return self._tag_rules

    def owner_for_item(self, item_id: str | None) -> str | None:
        listing = self._listing_for(item_id)
        if listing is None:
            return None
        owner = (listing.owner_ref or "").strip()
        if owner:
            return owner
        rules = self._rules()
        for tag in listing.tags_json or []:
            name = ""
            if isinstance(tag, str):
                name = tag.strip()
            elif isinstance(tag, dict):
                raw = tag.get("name") or tag.get("label") or tag.get("title")
                name = str(raw).strip() if raw is not None else ""
            if name and name in rules:
                return rules[name]
        return None

    def msku_for_item(self, item_id: str | None) -> str | None:
        listing = self._listing_for(item_id)
        value = (listing.msku or "").strip() if listing else ""
        return value or None

    def fx_rate(self, month: date) -> Decimal | None:
        return self._rates.get(month_key(month))

    def original_line(
        self, platform_order_no: str, order_line_no: str, gtin: str | None
    ) -> OriginalLine | None:
        key = (platform_order_no, order_line_no, gtin or "")
        if key not in self._originals:
            statement = (
                select(SettlementOrderLine)
                .join(
                    WalmartBillPeriod,
                    (WalmartBillPeriod.store_id == SettlementOrderLine.store_id)
                    & (WalmartBillPeriod.report_key == SettlementOrderLine.period_key)
                    & (
                        WalmartBillPeriod.source_account_ref
                        == SettlementOrderLine.source_account_ref
                    ),
                )
                .where(
                    SettlementOrderLine.source_account_ref == self.account,
                    SettlementOrderLine.store_id == self.store_id,
                    SettlementOrderLine.is_current.is_(True),
                    SettlementOrderLine.line_kind.in_(("sale", "mcf")),
                    SettlementOrderLine.platform_order_no == platform_order_no,
                    SettlementOrderLine.order_line_no == order_line_no,
                    SettlementOrderLine.period_key != self.period_key,
                    WalmartBillPeriod.report_date <= self.report_date,
                )
                .order_by(WalmartBillPeriod.report_date.desc())
                .limit(1)
            )
            if gtin:
                statement = statement.where(SettlementOrderLine.gtin == gtin)
            row = self.session.scalars(statement).one_or_none()
            self._originals[key] = (
                None
                if row is None
                else OriginalLine(
                    quantity=row.quantity,
                    purchase_cny=row.purchase_cny,
                    head_cny=row.head_cny,
                    last_leg_cny=row.last_leg_cny,
                    auto_passed=row.auto_passed,
                    msku=row.msku,
                )
            )
        return self._originals[key]


# --------------------------------------------------------------------------- 读账单


def load_bill_rows(
    session: Session, *, source_account_ref: str, store_id: str, period_key: str
) -> list[BillRow]:
    rows = session.scalars(
        select(WalmartBillLine)
        .where(
            WalmartBillLine.source_account_ref == source_account_ref,
            WalmartBillLine.store_id == store_id,
            WalmartBillLine.report_key == period_key,
            WalmartBillLine.delete_flag == 0,
            WalmartBillLine.missing_since.is_(None),
        )
        .order_by(WalmartBillLine.posted_at, WalmartBillLine.lx_line_id)
    ).all()
    return [
        BillRow(
            transaction_type=row.transaction_type,
            transaction_description=row.transaction_description,
            amount_type=row.amount_type,
            amount=row.amount,
            currency_code=row.currency_code,
            ship_qty=row.ship_qty,
            customer_order_no=row.customer_order_no,
            customer_order_line_no=row.customer_order_line_no,
            purchase_order_no=row.purchase_order_no,
            purchase_order_line_no=row.purchase_order_line_no,
            partner_gtin=row.partner_gtin,
            partner_item_id=row.partner_item_id,
            fulfillment_type=row.fulfillment_type,
            posted_date=row.posted_date,
            report_key=row.report_key,
            report_date=row.report_date,
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- 计算 + 写表


class OrderReviewCalculator:
    def __init__(self, session: Session, *, source_account_ref: str) -> None:
        self.session = session
        self.account = source_account_ref

    def recalc_period(
        self, store_id: str, period_key: str, *, run_ids: Iterable[str] = ()
    ) -> RecalcResult:
        # 锁住这一期：页面「重算」和账单同步后的任务可能同时跑同一期，串行化免得撞当前版本唯一索引
        period = self.session.scalars(
            select(WalmartBillPeriod)
            .where(
                WalmartBillPeriod.source_account_ref == self.account,
                WalmartBillPeriod.store_id == store_id,
                WalmartBillPeriod.report_key == period_key,
            )
            .with_for_update()
        ).one_or_none()
        if period is None:
            return RecalcResult(store_id=store_id, period_key=period_key, status="no_period")
        settings = load_settings(self.session, bill_month=period.report_date)
        bill_month = bill_month_of(period.report_date, settings.bill_month_cutoff_day)
        if month_is_closed(self.session, store_id=store_id, bill_month=bill_month):
            return RecalcResult(store_id=store_id, period_key=period_key, status="skipped_closed")

        rows = load_bill_rows(
            self.session, source_account_ref=self.account, store_id=store_id, period_key=period_key
        )
        lookups = DbLookups(
            self.session,
            source_account_ref=self.account,
            store_id=store_id,
            period_key=period_key,
            report_date=period.report_date,
        )
        lines = [
            compute_line(group, store_id=store_id, lookups=lookups, settings=settings)
            for group in group_order_rows(rows)
        ]
        result = RecalcResult(
            store_id=store_id, period_key=period_key, status="calculated", lines_total=len(lines)
        )
        self._write_fact(store_id, period_key, lines, result, run_ids=list(run_ids))
        self._write_review(store_id, period_key, bill_month, lines, result)
        return result

    def _write_fact(
        self,
        store_id: str,
        period_key: str,
        lines: list[ComputedLine],
        result: RecalcResult,
        *,
        run_ids: list[str],
    ) -> None:
        current = {
            row.line_key: row
            for row in self.session.scalars(
                select(SettlementOrderLine).where(
                    SettlementOrderLine.source_account_ref == self.account,
                    SettlementOrderLine.store_id == store_id,
                    SettlementOrderLine.period_key == period_key,
                    SettlementOrderLine.is_current.is_(True),
                )
            ).all()
        }
        max_version = (
            self.session.scalar(
                select(func.max(SettlementOrderLine.calc_version)).where(
                    SettlementOrderLine.source_account_ref == self.account,
                    SettlementOrderLine.store_id == store_id,
                    SettlementOrderLine.period_key == period_key,
                )
            )
            or 0
        )
        next_version = max_version + 1
        wrote_new = False
        seen: set[str] = set()
        for line in lines:
            seen.add(line.line_key)
            existing = current.get(line.line_key)
            if existing is not None and existing.content_hash == line.content_hash:
                result.lines_unchanged += 1
                continue
            if existing is not None:
                existing.is_current = False
                self.session.flush()
            self.session.add(_fact_row(self.account, store_id, line, next_version, run_ids))
            result.lines_new_version += 1
            wrote_new = True
        for line_key, existing in current.items():
            if line_key not in seen:
                existing.is_current = False
                result.lines_retired += 1
        result.calc_version = next_version if wrote_new else max_version
        self.session.flush()

    def _write_review(
        self,
        store_id: str,
        period_key: str,
        bill_month: date,
        lines: list[ComputedLine],
        result: RecalcResult,
    ) -> None:
        existing = {
            row.line_key: row
            for row in self.session.scalars(
                select(SettlementOrderReview).where(
                    SettlementOrderReview.store_id == store_id,
                    SettlementOrderReview.period_key == period_key,
                    SettlementOrderReview.row_kind == "order",
                )
            ).all()
        }
        seen: set[str] = set()
        for line in lines:
            seen.add(line.line_key)
            row = existing.get(line.line_key)
            computed_status = "auto" if line.auto_passed else "pending"
            flagged = row is not None and CHANGED_AFTER_REVIEW in (row.reasons or [])
            if row is None:
                row = SettlementOrderReview(
                    id=uuid4(),
                    store_id=store_id,
                    period_key=period_key,
                    bill_month=bill_month,
                    line_key=line.line_key,
                    row_kind="order",
                    review_status=computed_status,
                    calc_version=result.calc_version,
                    content_hash=line.content_hash,
                )
                self.session.add(row)
            else:
                changed = row.content_hash != line.content_hash
                if row.review_status in {"pending", "auto"}:
                    row.review_status = computed_status
                elif changed and row.review_status == "rejected":
                    row.review_status = computed_status
                # first_passed / final_passed 保持；计算值变了版本号 +1，并加差异提示
                # changed_after_review（§8.4：已确认 / 修正的行不自动改，写差异提示；
                # 撤销或重审后清掉）
                if changed:
                    row.version += 1
                    if row.review_status in {"first_passed", "final_passed"}:
                        flagged = True
                row.calc_version = result.calc_version
                row.content_hash = line.content_hash
                row.bill_month = bill_month
            row.platform_order_no = line.platform_order_no
            row.item_id = line.item_id
            row.sku = line.sku
            row.msku = line.msku
            row.owner_id = line.owner_id
            row.transaction_types = list(line.transaction_types)
            row.reasons = list(line.reasons) + ([CHANGED_AFTER_REVIEW] if flagged else [])
            row.settlement_amount_usd = line.settlement_amount_usd
            row.cost_total_cny = line.cost_total_cny
            row.updated_at = utc_now()
            if row.review_status == "auto":
                result.auto_passed += 1
            elif row.review_status == "pending":
                result.pending += 1
        for line_key, row in existing.items():
            if line_key not in seen:
                self.session.delete(row)
        self.session.flush()


def _fact_row(
    account: str, store_id: str, line: ComputedLine, version: int, run_ids: list[str]
) -> SettlementOrderLine:
    return SettlementOrderLine(
        id=uuid4(),
        source_account_ref=account,
        store_id=store_id,
        period_key=line.period_key,
        bill_month=line.bill_month,
        line_key=line.line_key,
        is_current=True,
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
        quantity=line.quantity,
        transaction_types=list(line.transaction_types),
        sales_usd=line.sales_usd,
        refund_usd=line.refund_usd,
        promotion_usd=line.promotion_usd,
        commission_usd=line.commission_usd,
        return_fee_usd=line.return_fee_usd,
        tax_withheld_usd=line.tax_withheld_usd,
        wfs_fulfillment_fee_usd=line.wfs_fulfillment_fee_usd,
        mcf_fee_usd=line.mcf_fee_usd,
        settlement_amount_usd=line.settlement_amount_usd,
        purchase_cny=line.purchase_cny,
        head_cny=line.head_cny,
        last_leg_cny=line.last_leg_cny,
        cost_total_cny=line.cost_total_cny,
        cost_total_usd=line.cost_total_usd,
        fx_rate=line.fx_rate,
        fx_month=line.fx_month,
        fx_status=line.fx_status,
        cost_sources=list(line.cost_sources),
        cost_entry_ids=list(line.cost_entry_ids),
        reasons=list(line.reasons),
        auto_passed=line.auto_passed,
        source_run_ids=run_ids,
        calc_version=version,
        content_hash=line.content_hash,
    )


def periods_for_recalc(
    session: Session,
    *,
    source_account_ref: str,
    store_ids: Iterable[str] | None = None,
    report_date_from: date | None = None,
) -> list[tuple[str, str]]:
    """要重算的 (store_id, period_key)：有明细的期，默认 2026-10-01 起（§0.1）。"""
    statement = select(WalmartBillPeriod.store_id, WalmartBillPeriod.report_key).where(
        WalmartBillPeriod.source_account_ref == source_account_ref,
        WalmartBillPeriod.report_date >= (report_date_from or date(2026, 10, 1)),
        WalmartBillPeriod.line_count > 0,
    )
    stores = [s for s in (store_ids or []) if s]
    if stores:
        statement = statement.where(WalmartBillPeriod.store_id.in_(stores))
    rows = session.execute(
        statement.order_by(WalmartBillPeriod.store_id, WalmartBillPeriod.report_date)
    ).all()
    return [(store, key) for store, key in rows]
