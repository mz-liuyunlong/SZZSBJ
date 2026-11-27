"""订单审核的纯计算规则（PRP §8.1～§8.4）：不碰数据库，输入都是普通数据结构。

一期一店：账单明细 → 订单行（订单号 × 订单行号 × GTIN）→ 收入 / 费用列 → 货本（按成本计价流水的段）
→ 待审原因 / 自动通过。金额全程 Decimal；分段加权用件数，合计按列精度（4 位）规范化。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.modules.settlement_profit.transaction_types import categorize, type_code

MONEY_Q = Decimal("0.0001")
QTY_Q = Decimal("0.0001")
ZERO = Decimal("0")

SHIPMENT_PREFIX = "shipment:"
# 录入范围 MSKU × 平台订单号（自发货订单、流水没覆盖的差额段）；
# 迁移 0101 的 scope_ref_matches 第三种
ORDER_SCOPE_PREFIX = "order:"
FIXED_VALUE_SOURCE = "无源单配置-固定值"
LAST_RECEIVED_SOURCE = "无源单配置-最近签收成本"

# 退货入库的退款描述（件数回仓才冲货本，§8.3 第 5 条）；免退货 / 卖家主动退款 / 拒付不回仓。
RETURNED_REFUND_DESCRIPTIONS = frozenset({"Return Refund", "Seller Initiated Returns"})

CostSourceKind = Literal["shipment", "fixed_value", "last_received", "missing", "outbound", "entry"]


# --------------------------------------------------------------------------- 输入


@dataclass(frozen=True, slots=True)
class BillRow:
    transaction_type: str | None
    transaction_description: str | None
    amount_type: str | None
    amount: Decimal
    currency_code: str
    ship_qty: int | None
    customer_order_no: str | None
    customer_order_line_no: str | None
    purchase_order_no: str | None
    purchase_order_line_no: str | None
    partner_gtin: str | None
    partner_item_id: str | None
    fulfillment_type: str | None
    posted_date: date | None
    report_key: str
    report_date: date


@dataclass(frozen=True, slots=True)
class FlowSegment:
    """成本计价流水一段（订单发货）：件数取绝对值。"""

    cost_source: str | None
    msku: str | None
    gtin: str | None
    quantity: Decimal
    business_number: str | None
    purchase_total: Decimal | None
    logistics_total: Decimal | None
    other_total: Decimal | None
    currency_code: str | None
    row_hash: str
    # 领星 businessType 原值，只记录不判定（订单发货的编码待首次探测后再收紧）
    business_type: str | None = None


@dataclass(frozen=True, slots=True)
class ShipmentDetail:
    shipping_list_code: str
    msku: str
    purchase_price: Decimal | None
    head_stock_price: Decimal | None
    per_firstlet_cost: Decimal | None
    per_tax: Decimal | None
    wfs_stock_price: Decimal | None
    currency_code: str | None
    logistics_way: str | None


@dataclass(frozen=True, slots=True)
class ShipmentHeader:
    shipping_list_code: str
    logistics_provider_id: str | None
    logistics_provider_name: str | None


@dataclass(frozen=True, slots=True)
class OutboundItem:
    """销售出库单 items 一行（#370 同步保留的键）。

    seller_sku = MSKU，apportion_freight = 该行分摊运费。
    """

    msku: str | None
    count: Decimal | None
    apportion_freight: Decimal | None
    currency_code: str | None


@dataclass(frozen=True, slots=True)
class OutboundOrder:
    outbound_order_no: str
    logistics_fee: Decimal | None
    currency_code: str | None
    items: tuple[OutboundItem, ...] = ()
    # 出库单状态原值（#370 同步存 status_name，没有时存 status 编码）
    order_status: str | None = None


# 出库单状态（刘云龙 11-27 终审拍板）：已截单 / 已作废不计运费；只有确认已发出的才计；
# 其余（空、编码、没见过的名称）一律"待核实"，尾程留空不自动算。
# 枚举值按领星页面上的状态名先列，首次探测拿到真实取值后再在决策文件里确认、补全。
OUTBOUND_SHIPPED_STATUSES = frozenset({"已出库", "已发货"})
OUTBOUND_EXCLUDED_STATUSES = frozenset({"已截单", "已作废", "已取消"})


@dataclass(frozen=True, slots=True)
class CostEntry:
    id: str
    msku: str
    scope_ref: str
    purchase_cny: Decimal | None
    head_cny: Decimal | None
    last_leg_cny: Decimal | None
    entry_kind: str
    status: str


@dataclass(frozen=True, slots=True)
class ReviewSettings:
    # None = 清单还没配置（§8.3 第 4 条：算不满足）
    wfs_carrier_provider_ids: frozenset[str] | None
    bill_month_cutoff_day: int = 5


@dataclass(frozen=True, slots=True)
class OriginalLine:
    """退款行要冲回的原订单行：货本单价（¥ / 件）与审核结论。"""

    quantity: Decimal
    purchase_cny: Decimal | None
    head_cny: Decimal | None
    last_leg_cny: Decimal | None
    auto_passed: bool
    msku: str | None


class Lookups:
    """计算需要的查表；由 calc 层用数据库实现，测试用字典实现。"""

    def flow_segments(self, order_nos: Iterable[str], gtin: str | None) -> list[FlowSegment]:
        raise NotImplementedError

    def shipment_detail(self, code: str, msku: str) -> ShipmentDetail | None:
        raise NotImplementedError

    def shipment_header(self, code: str) -> ShipmentHeader | None:
        raise NotImplementedError

    def outbound_orders(self, platform_order_no: str) -> list[OutboundOrder]:
        """该平台订单号下的全部销售出库单（一单可能拆多个包裹）。"""
        raise NotImplementedError

    def cost_entry(self, msku: str, scope_ref: str) -> CostEntry | None:
        raise NotImplementedError

    def owner_for_item(self, item_id: str | None) -> str | None:
        raise NotImplementedError

    def msku_for_item(self, item_id: str | None) -> str | None:
        raise NotImplementedError

    def fx_rate(self, month: date) -> Decimal | None:
        raise NotImplementedError

    def original_line(
        self, platform_order_no: str, order_line_no: str, gtin: str | None
    ) -> OriginalLine | None:
        raise NotImplementedError


# --------------------------------------------------------------------------- 输出


@dataclass(slots=True)
class ComputedLine:
    line_key: str
    line_kind: str
    fulfillment_type: str
    platform_order_no: str
    order_line_no: str
    gtin: str | None
    item_id: str | None
    sku: str | None
    msku: str | None
    owner_id: str | None
    posted_date: date | None
    period_key: str
    report_date: date
    bill_month: date
    quantity: Decimal
    transaction_types: list[str]
    sales_usd: Decimal = ZERO
    refund_usd: Decimal = ZERO
    promotion_usd: Decimal = ZERO
    commission_usd: Decimal = ZERO
    return_fee_usd: Decimal = ZERO
    tax_withheld_usd: Decimal = ZERO
    wfs_fulfillment_fee_usd: Decimal = ZERO
    mcf_fee_usd: Decimal = ZERO
    settlement_amount_usd: Decimal = ZERO
    purchase_cny: Decimal | None = None
    head_cny: Decimal | None = None
    last_leg_cny: Decimal | None = None
    cost_total_cny: Decimal | None = None
    cost_total_usd: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_month: date | None = None
    fx_status: str = "missing"
    cost_sources: list[dict[str, Any]] = field(default_factory=list)
    cost_entry_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    auto_passed: bool = False
    content_hash: str = ""


# --------------------------------------------------------------------------- 工具


def money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def qty(value: Decimal | int | None) -> Decimal:
    return (Decimal(value or 0)).quantize(QTY_Q, rounding=ROUND_HALF_UP)


def bill_month_of(report_date: date, cutoff_day: int) -> date:
    """账单日 ≤ 次月 cutoff 号算上月（§8.2，默认 5 号）。"""
    if report_date.day <= cutoff_day:
        year, month = (report_date.year, report_date.month - 1)
        if month == 0:
            year, month = year - 1, 12
        return date(year, month, 1)
    return date(report_date.year, report_date.month, 1)


def fulfillment_of(value: str | None) -> str:
    text = (value or "").strip().lower()
    return "wfs" if "wfs" in text or "walmart-fulfilled" in text else "seller"


def line_key_of(
    store_id: str, report_key: str, order_no: str, line_no: str, gtin: str | None
) -> str:
    return f"{store_id}|{report_key}|{order_no}|{line_no}|{gtin or ''}"


def _text(value: str | None) -> str:
    return (value or "").strip()


# --------------------------------------------------------------------------- 分组


@dataclass(slots=True)
class OrderGroup:
    order_no: str
    line_no: str
    gtin: str | None
    purchase_order_no: str | None
    rows: list[BillRow]


def group_order_rows(rows: Iterable[BillRow]) -> list[OrderGroup]:
    """账单行按 订单号 × 订单行号 × GTIN 归组；没有订单号或不属于订单级的行丢掉（店铺级另算）。"""
    groups: dict[tuple[str, str, str], OrderGroup] = {}
    for row in rows:
        category = categorize(row.transaction_type, row.transaction_description, row.amount_type)
        if category in {"store", "excluded"}:
            continue
        order_no = _text(row.customer_order_no) or _text(row.purchase_order_no)
        if not order_no:
            continue
        line_no = _text(row.customer_order_line_no) or _text(row.purchase_order_line_no) or "1"
        gtin = _text(row.partner_gtin) or None
        key = (order_no, line_no, gtin or "")
        group = groups.get(key)
        if group is None:
            group = OrderGroup(
                order_no=order_no,
                line_no=line_no,
                gtin=gtin,
                purchase_order_no=_text(row.purchase_order_no) or None,
                rows=[],
            )
            groups[key] = group
        group.rows.append(row)
    return list(groups.values())


# --------------------------------------------------------------------------- 一行


def _amounts(group: OrderGroup) -> tuple[dict[str, Decimal], list[str], Decimal, str]:
    totals: dict[str, Decimal] = {}
    types: list[str] = []
    quantity = ZERO
    kinds: set[str] = set()
    for row in group.rows:
        category = categorize(row.transaction_type, row.transaction_description, row.amount_type)
        totals[category] = totals.get(category, ZERO) + row.amount
        code = type_code(row.transaction_type, row.transaction_description, row.amount_type)
        if code not in types:
            types.append(code)
        if category == "sales":
            kinds.add("sale")
            quantity += Decimal(row.ship_qty or 0)
        elif category == "refund" and _text(row.amount_type) == "Product Price":
            kinds.add("refund")
            quantity -= Decimal(row.ship_qty or 0)
        elif category == "mcf_fee":
            kinds.add("mcf")
    if "sale" in kinds:
        kind = "sale"
    elif "refund" in kinds:
        kind = "refund"
    elif "mcf" in kinds:
        kind = "mcf"
    else:
        kind = "sale"
    return totals, sorted(types), quantity, kind


@dataclass(slots=True)
class _Segment:
    kind: CostSourceKind
    quantity: Decimal
    msku: str | None
    scope_ref: str | None
    purchase: Decimal | None
    head: Decimal | None
    last_leg: Decimal | None
    reasons: list[str]
    detail: dict[str, Any]
    entry_id: str | None = None


def _four_valid(detail: ShipmentDetail) -> tuple[bool, Decimal | None, Decimal | None]:
    """四项齐全、前三项 > 0、税 ≥ 0、之和 = 单位成本、币种 CNY、物流方式非空。"""
    values = (
        detail.purchase_price,
        detail.head_stock_price,
        detail.per_firstlet_cost,
        detail.per_tax,
    )
    if any(value is None for value in values) or detail.wfs_stock_price is None:
        return False, None, None
    purchase, head_stock, firstlet, tax = (money(v) for v in values)
    assert purchase is not None and head_stock is not None and firstlet is not None
    assert tax is not None
    if purchase <= 0 or head_stock <= 0 or firstlet <= 0 or tax < 0:
        return False, None, None
    total = money(purchase + head_stock + firstlet + tax)
    if total != money(detail.wfs_stock_price):
        return False, None, None
    if _text(detail.currency_code).upper() != "CNY" or not _text(detail.logistics_way):
        return False, None, None
    return True, purchase, money(head_stock + firstlet + tax)


def _wfs_carrier(
    header: ShipmentHeader | None, detail: ShipmentDetail | None, settings: ReviewSettings
) -> bool:
    """按 §8.3 第 4 条：任一条成立就当作 WFS 承运（不能自动通过）。"""
    provider = _text(header.logistics_provider_id) if header else ""
    way = _text(detail.logistics_way) if detail else ""
    if not provider:
        return True
    if settings.wfs_carrier_provider_ids is None:
        return True
    if provider in settings.wfs_carrier_provider_ids:
        return True
    return way.upper().startswith("WFS")


def _apply_entry(segment: _Segment, entry: CostEntry | None, *, with_last_leg: bool) -> None:
    if entry is None or entry.status == "revoked":
        return
    segment.kind = "entry"
    segment.entry_id = entry.id
    segment.purchase = money(entry.purchase_cny)
    segment.head = money(entry.head_cny)
    if with_last_leg:
        segment.last_leg = money(entry.last_leg_cny)
    segment.reasons = []
    segment.detail["entry_kind"] = entry.entry_kind


def _shipment_segment(
    flow: FlowSegment,
    code: str,
    lookups: Lookups,
    settings: ReviewSettings,
    *,
    seller: bool,
) -> _Segment:
    msku = _text(flow.msku) or None
    detail = lookups.shipment_detail(code, msku) if msku else None
    header = lookups.shipment_header(code)
    segment = _Segment(
        kind="shipment",
        quantity=flow.quantity,
        msku=msku,
        scope_ref=f"shipping:{code}",
        purchase=None,
        head=None,
        last_leg=None,
        reasons=[],
        detail={
            "shipping_list_code": code,
            "business_type": flow.business_type,
            "logistics_provider_id": header.logistics_provider_id if header else None,
            "logistics_provider_name": header.logistics_provider_name if header else None,
            "logistics_way": detail.logistics_way if detail else None,
            "flow_row_hash": flow.row_hash,
        },
    )
    if detail is None:
        segment.reasons.append("shipment_detail_invalid")
    else:
        valid, purchase, head = _four_valid(detail)
        segment.detail["prefill"] = {
            "purchase_price": _s(detail.purchase_price),
            "head_stock_price": _s(detail.head_stock_price),
            "per_firstlet_cost": _s(detail.per_firstlet_cost),
            "per_tax": _s(detail.per_tax),
            "wfs_stock_price": _s(detail.wfs_stock_price),
            "currency_code": detail.currency_code,
        }
        if valid:
            segment.purchase, segment.head = purchase, head
        else:
            segment.reasons.append("shipment_detail_invalid")
            segment.purchase = money(detail.purchase_price)
            if (
                detail.head_stock_price is not None
                and detail.per_firstlet_cost is not None
                and detail.per_tax is not None
            ):
                segment.head = money(
                    detail.head_stock_price + detail.per_firstlet_cost + detail.per_tax
                )
    # 自发货订单的待审原因是 self_fulfilled，不再叠加 WFS 承运；
    # 录入范围也在出库单上（见 _seller_last_leg）。
    if not seller and _wfs_carrier(header, detail, settings):
        segment.reasons.append("wfs_carrier_shipment")
    if msku and not seller:
        entry = lookups.cost_entry(msku, segment.scope_ref or "")
        _apply_entry(segment, entry, with_last_leg=False)
    return segment


def _flow_prefill(flow: FlowSegment) -> tuple[Decimal | None, Decimal | None]:
    if flow.quantity <= 0:
        return None, None
    purchase = None if flow.purchase_total is None else abs(flow.purchase_total) / flow.quantity
    head = None
    if flow.logistics_total is not None or flow.other_total is not None:
        head = (abs(flow.logistics_total or ZERO) + abs(flow.other_total or ZERO)) / flow.quantity
    return money(purchase), money(head)


def _config_segment(
    flow: FlowSegment, kind: CostSourceKind, reason: str, lookups: Lookups, *, seller: bool
) -> _Segment:
    msku = _text(flow.msku) or None
    scope = f"outbound:{_text(flow.business_number)}" if _text(flow.business_number) else None
    purchase, head = _flow_prefill(flow)
    segment = _Segment(
        kind=kind,
        quantity=flow.quantity,
        msku=msku,
        scope_ref=scope,
        purchase=None,
        head=None,
        last_leg=None,
        reasons=[reason],
        detail={
            "cost_source": flow.cost_source,
            "business_type": flow.business_type,
            "business_number": flow.business_number,
            "flow_row_hash": flow.row_hash,
            "prefill": {"purchase_cny": _s(purchase), "head_cny": _s(head)},
        },
    )
    if msku and scope and not seller:
        _apply_entry(segment, lookups.cost_entry(msku, scope), with_last_leg=False)
    return segment


def _s(value: Decimal | None) -> str | None:
    return None if value is None else str(money(value))


def _weighted(segments: list[_Segment], attr: str) -> Decimal | None:
    """按件数加权合计；任何一段缺值整列为空（不拿半截数当货本）。"""
    total = ZERO
    for segment in segments:
        value = getattr(segment, attr)
        if value is None:
            return None
        total += value * segment.quantity
    return money(total)


def compute_line(
    group: OrderGroup,
    *,
    store_id: str,
    lookups: Lookups,
    settings: ReviewSettings,
) -> ComputedLine:
    totals, types, quantity, kind = _amounts(group)
    first = group.rows[0]
    # MCF 行账单里没有履约类型：按 §0.3 走 WFS 同一规则（经 costSource 定位发货单），不当自发货
    fulfillment = "wfs" if kind == "mcf" else fulfillment_of(first.fulfillment_type)
    item_id = next((_text(r.partner_item_id) for r in group.rows if _text(r.partner_item_id)), None)
    report_date = first.report_date
    line = ComputedLine(
        line_key=line_key_of(store_id, first.report_key, group.order_no, group.line_no, group.gtin),
        line_kind=kind,
        fulfillment_type=fulfillment,
        platform_order_no=group.order_no,
        order_line_no=group.line_no,
        gtin=group.gtin,
        item_id=item_id,
        sku=None,
        msku=lookups.msku_for_item(item_id),
        owner_id=lookups.owner_for_item(item_id),
        posted_date=min((r.posted_date for r in group.rows if r.posted_date), default=None),
        period_key=first.report_key,
        report_date=report_date,
        bill_month=bill_month_of(report_date, settings.bill_month_cutoff_day),
        quantity=qty(quantity),
        transaction_types=types,
        sales_usd=money(totals.get("sales", ZERO)) or ZERO,
        refund_usd=money(totals.get("refund", ZERO)) or ZERO,
        promotion_usd=money(totals.get("promotion", ZERO)) or ZERO,
        commission_usd=money(totals.get("commission", ZERO)) or ZERO,
        return_fee_usd=money(totals.get("return_fee", ZERO)) or ZERO,
        tax_withheld_usd=money(totals.get("tax_withheld", ZERO)) or ZERO,
        wfs_fulfillment_fee_usd=money(totals.get("wfs_fulfillment_fee", ZERO)) or ZERO,
        mcf_fee_usd=money(totals.get("mcf_fee", ZERO)) or ZERO,
    )
    line.settlement_amount_usd = money(sum(totals.values(), ZERO)) or ZERO

    if kind == "refund":
        _refund_cost(line, group, lookups)
    else:
        _sale_cost(line, group, lookups, settings)

    if line.owner_id is None and "owner_missing" not in line.reasons:
        line.reasons.append("owner_missing")
    line.reasons = sorted(set(line.reasons))
    line.auto_passed = bool(line.auto_passed and not line.reasons)
    _fx(line, lookups)
    line.content_hash = content_hash(line)
    return line


def _sale_cost(
    line: ComputedLine, group: OrderGroup, lookups: Lookups, settings: ReviewSettings
) -> None:
    # 客户订单号和 PO 号常常相同：去重后再查流水，免得同一段取两遍
    order_nos = list(dict.fromkeys(n for n in (group.order_no, group.purchase_order_no) if n))
    flows = lookups.flow_segments(order_nos, group.gtin)
    seller = line.fulfillment_type == "seller"
    sold = line.quantity

    # 同期卖出又取消退款、净件数 0、未发货的自发货订单（§8.4 cancelled_refund）
    if seller and sold == 0 and line.refund_usd != 0 and not flows:
        line.reasons.append("cancelled_refund")
        line.purchase_cny = line.head_cny = line.last_leg_cny = ZERO
        line.cost_total_cny = ZERO
        line.cost_sources = [{"kind": "cancelled_refund", "quantity": "0"}]
        return

    segments: list[_Segment] = []
    for flow in flows:
        source = _text(flow.cost_source)
        if source.startswith(SHIPMENT_PREFIX):
            code = source[len(SHIPMENT_PREFIX) :]
            segments.append(_shipment_segment(flow, code, lookups, settings, seller=seller))
        elif source == FIXED_VALUE_SOURCE:
            segments.append(
                _config_segment(flow, "fixed_value", "fixed_value", lookups, seller=seller)
            )
        elif source == LAST_RECEIVED_SOURCE:
            segments.append(
                _config_segment(flow, "last_received", "last_received", lookups, seller=seller)
            )
        else:
            segments.append(
                _config_segment(flow, "missing", "cost_missing", lookups, seller=seller)
            )

    covered = sum((s.quantity for s in segments), ZERO)
    if sold > 0 and covered < sold:
        # 流水没覆盖全部件数：差的那部分没有来源
        line.reasons.append("cost_missing")
        missing_msku = line.msku
        segments.append(
            _Segment(
                kind="missing",
                quantity=sold - covered,
                msku=missing_msku,
                scope_ref=f"{ORDER_SCOPE_PREFIX}{group.order_no}",
                purchase=None,
                head=None,
                last_leg=None,
                reasons=["cost_missing"],
                # 没有任何单据可挂：范围退化为 MSKU × 平台订单号（order: 前缀，见接口文档 §2）
                detail={"note": "flow_not_covering", "scope_kind": "platform_order"},
            )
        )
        if missing_msku and not seller:
            _apply_entry(
                segments[-1],
                lookups.cost_entry(missing_msku, segments[-1].scope_ref or ""),
                with_last_leg=False,
            )

    if seller:
        _seller_last_leg(line, group, segments, lookups)

    for segment in segments:
        line.reasons.extend(segment.reasons)
        if segment.entry_id:
            line.cost_entry_ids.append(segment.entry_id)
    if not segments:
        line.reasons.append("cost_missing")

    line.cost_sources = [
        {
            "kind": s.kind,
            "quantity": str(s.quantity),
            "msku": s.msku,
            "scope_ref": s.scope_ref,
            "purchase_cny": _s(s.purchase),
            "head_cny": _s(s.head),
            "last_leg_cny": _s(s.last_leg),
            "reasons": s.reasons,
            "entry_id": s.entry_id,
            **s.detail,
        }
        for s in segments
    ]
    line.purchase_cny = _weighted(segments, "purchase") if segments else None
    line.head_cny = _weighted(segments, "head") if segments else None
    if seller:
        line.last_leg_cny = _weighted(segments, "last_leg") if segments else None
    else:
        line.last_leg_cny = None
    parts = [line.purchase_cny, line.head_cny] + ([line.last_leg_cny] if seller else [])
    line.cost_total_cny = None if any(p is None for p in parts) else money(sum(parts, ZERO))
    if line.msku is None:
        line.msku = next((s.msku for s in segments if s.msku), None)
    if seller:
        line.reasons.append("self_fulfilled")
    # 自动通过只认发货单来源；套用了人工录入（entry）的段要走初审 / 终审（#373 复审 P1）
    line.auto_passed = (
        not seller
        and bool(segments)
        and all(s.kind == "shipment" for s in segments)
        and all(not s.reasons for s in segments)
        and covered >= sold
    )


def _seller_last_leg(
    line: ComputedLine, group: OrderGroup, segments: list[_Segment], lookups: Lookups
) -> None:
    """自发货尾程（#373 P1）。

    该平台订单号下全部出库单 items 里本 MSKU 的 apportion_freight 跨张累加，
    按本 MSKU 出库件数折成单价；不用整单 logistics_fee（一单多商品会把同一笔运费扣多次）。
    items 缺本 MSKU、缺分摊运费或缺件数 → 尾程留空、self_fulfilled 待审，不退回整单运费。
    录入范围 = MSKU × 平台订单号（一单拆多张出库单也只有一个范围）。"""
    if not segments:
        return
    msku = line.msku or next((s.msku for s in segments if s.msku), None)
    unit, total, outbounds, note = _msku_freight(
        msku, lookups.outbound_orders(group.order_no), line.report_date, lookups
    )
    scope = f"{ORDER_SCOPE_PREFIX}{group.order_no}"
    for segment in segments:
        segment.scope_ref = scope
        segment.detail["scope_kind"] = "platform_order"
        segment.detail["outbound_order_nos"] = outbounds  # [{no, status, counted}]
        segment.detail["last_leg_prefill_cny"] = _s(unit)  # 单价，录入抽屉的默认值
        segment.detail["last_leg_msku_total_cny"] = _s(total)  # 本 MSKU 在该订单的运费合计
        if note:
            segment.detail["last_leg_note"] = note
        segment.last_leg = unit
        if segment.msku:
            entry = lookups.cost_entry(segment.msku, scope)
            if entry is not None and entry.status != "revoked":
                _apply_entry(segment, entry, with_last_leg=True)


def _freight_cny(
    amount: Decimal, currency: str | None, report_date: date, lookups: Lookups
) -> Decimal | None:
    code = _text(currency).upper()
    if code in {"CNY", ""}:
        return amount
    if code == "USD":
        rate = lookups.fx_rate(report_date)
        return amount * rate if rate else None
    return None


def _msku_freight(
    msku: str | None, outbounds: list[OutboundOrder], report_date: date, lookups: Lookups
) -> tuple[Decimal | None, Decimal | None, list[dict[str, Any]], str | None]:
    """返回（单价 ¥、合计 ¥、含本 MSKU 的出库单 [{no, status, counted}]、留空原因）。

    只看含本 MSKU 的出库单。已截单 / 已作废跳过；状态确认不了 → 整体留空待核实；
    本 MSKU 任何一行缺分摊运费或件数 → 整体留空，不按剩余件数半算（#373 终审）。
    """
    if not msku:
        return None, None, [], "msku_missing"
    total = ZERO
    count = ZERO
    listed: list[dict[str, Any]] = []
    blank: str | None = None
    for outbound in outbounds:
        mine = [item for item in outbound.items if _text(item.msku) == msku]
        if not mine:
            continue
        status = _text(outbound.order_status)
        counted = status in OUTBOUND_SHIPPED_STATUSES
        listed.append(
            {"no": outbound.outbound_order_no, "status": status or None, "counted": counted}
        )
        if status in OUTBOUND_EXCLUDED_STATUSES:
            continue
        if not counted:
            blank = blank or "outbound_status_unverified"
            continue
        for item in mine:
            if item.apportion_freight is None:
                blank = blank or "apportion_freight_missing"
                continue
            if item.count is None or item.count <= 0:
                blank = blank or "outbound_count_missing"
                continue
            cny = _freight_cny(
                item.apportion_freight,
                item.currency_code or outbound.currency_code,
                report_date,
                lookups,
            )
            if cny is None:
                blank = blank or "freight_currency_unconverted"
                continue
            total += cny
            count += item.count
    if blank is not None:
        # 半算会误导：单价和合计都不给
        return None, None, listed, blank
    if count <= 0:
        # 含本 MSKU 的出库单都已截单 / 作废（或根本没有）
        return None, None, listed, "msku_not_in_outbound"
    return money(total / count), money(total), listed, None


def _refund_cost(line: ComputedLine, group: OrderGroup, lookups: Lookups) -> None:
    """退款行：退货入库才按退回件数 × 原行货本单价冲回（负数）；沿用原行来源与审核结论。"""
    returned = any(
        _text(r.transaction_description) in RETURNED_REFUND_DESCRIPTIONS for r in group.rows
    )
    original = lookups.original_line(group.order_no, group.line_no, group.gtin)
    line.cost_sources = [{"kind": "refund", "returned": returned}]
    if not returned:
        line.purchase_cny = line.head_cny = line.last_leg_cny = ZERO
        line.cost_total_cny = ZERO
        line.auto_passed = True
        if original is not None and original.msku and line.msku is None:
            line.msku = original.msku
        return
    if original is None or original.quantity <= 0:
        # 退货入库却找不到原订单行（如 10 月前卖出 10 月退货）：货本冲不了，待审（#373 复审 P3-6）
        line.reasons.append("cost_missing")
        line.cost_sources[0]["note"] = "original_line_missing"
        return
    units = abs(line.quantity)
    if line.msku is None:
        line.msku = original.msku

    def reverse(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return money(-(value / original.quantity) * units)

    line.purchase_cny = reverse(original.purchase_cny)
    line.head_cny = reverse(original.head_cny)
    line.last_leg_cny = reverse(original.last_leg_cny)
    parts = [p for p in (line.purchase_cny, line.head_cny, line.last_leg_cny) if p is not None]
    line.cost_total_cny = money(sum(parts, ZERO)) if parts else None
    line.auto_passed = original.auto_passed
    line.cost_sources[0]["original_quantity"] = str(original.quantity)


def _fx(line: ComputedLine, lookups: Lookups) -> None:
    rate = lookups.fx_rate(line.report_date)
    line.fx_month = date(line.report_date.year, line.report_date.month, 1)
    if rate is None or rate <= 0:
        line.fx_rate = None
        line.fx_status = "missing"
        line.cost_total_usd = None
        return
    line.fx_rate = rate
    line.fx_status = "final"
    line.cost_total_usd = None if line.cost_total_cny is None else money(line.cost_total_cny / rate)


_HASH_FIELDS = (
    "line_key",
    "line_kind",
    "fulfillment_type",
    "platform_order_no",
    "order_line_no",
    "gtin",
    "item_id",
    "msku",
    "owner_id",
    "posted_date",
    "period_key",
    "bill_month",
    "quantity",
    "transaction_types",
    "sales_usd",
    "refund_usd",
    "promotion_usd",
    "commission_usd",
    "return_fee_usd",
    "tax_withheld_usd",
    "wfs_fulfillment_fee_usd",
    "mcf_fee_usd",
    "settlement_amount_usd",
    "purchase_cny",
    "head_cny",
    "last_leg_cny",
    "cost_total_cny",
    "cost_total_usd",
    "fx_rate",
    "fx_status",
    "cost_sources",
    "cost_entry_ids",
    "reasons",
    "auto_passed",
)


def content_hash(line: ComputedLine) -> str:
    """只算业务字段（§8.1）：不含 id、版本、时间戳、同步批次。"""

    def normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in sorted(value.items())}
        return value

    payload = {name: normalize(getattr(line, name)) for name in _HASH_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


LookupFactory = Callable[[], Lookups]
