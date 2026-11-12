"""WFS 费用归属到商品的规则（沿用 2026-07~10 月手工表 features/finance/drafts/build_fee.py）。

纯函数，不碰数据库：service 把需要的上下文（商品表、仓储费、货件分摊比例、无折扣配送费基数）
查好传进来。

- 有 GTIN：店铺 + GTIN → 商品（item_id / msku / local_sku）→ matched；查不到 → unmatched。
- 无 GTIN：
  - Refund · InboundTransportationShippingRefund（入库运费多收退款）：
    按该货件的入库运费分摊比例分到商品；货件没有分摊数据 → unallocated。
  - Refund · StorageFeeDispute（仓储费争议退款）：company。
  - DiscountAdjustment（新卖家补贴返还）：按明细里的期间；
    配送费返还 = 期间内无逐行折扣的配送费原价 × 10%，仓储费返还 = 期间内各 SKU 仓储费原价 × 10%；
    基数 × 10% 与返还额差 > 1% → allocated_check（基数待核）。
  - 其他 → unallocated，财务在页面调整。
- 入库运费（货件）：按货件商品实发数量分，没有实发按申报数量，尾差归最后一行；
  货件查无 → unallocated。
金额分摊到分，尾差归最后一行，Σ子行 = 原行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.modules.wfs_fees.parsing import INBOUND_FEE

ATTR_MATCHED = "matched"
ATTR_UNMATCHED = "unmatched"
ATTR_ALLOCATED = "allocated"
ATTR_ALLOCATED_CHECK = "allocated_check"
ATTR_UNALLOCATED = "unallocated"
ATTR_COMPANY = "company"

REBATE_RATE = Decimal("0.10")
CENT = Decimal("0.01")
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
PERIOD_IN_DETAIL = re.compile(r"for ([A-Z]{3})-(\d{2})-(\d{2}) to ([A-Z]{3})-(\d{2})-(\d{2})")
CARGO_IN_DETAIL = re.compile(r"_(\d{7}WF[A-Z])_")


@dataclass(frozen=True)
class Listing:
    item_id: str = ""
    msku: str = ""
    local_sku: str = ""


@dataclass
class Share:
    """分摊的一份：商品 + 比例依据。"""

    gtin: str = ""
    item_id: str = ""
    msku: str = ""
    local_sku: str = ""
    weight: Decimal = Decimal("0")
    basis: str = ""


@dataclass
class Allocation:
    attribution: str
    children: list[tuple[Share, Decimal]] = field(default_factory=list)
    note: str = ""


def lookup(listings: dict[tuple[str, str], Listing], store_id: str, gtin: str) -> Listing | None:
    """店铺 + GTIN 查商品；领星 / 报表的 GTIN 可能少前导 0。"""
    if not gtin:
        return None
    for candidate in (gtin, gtin.lstrip("0"), gtin.zfill(14)):
        hit = listings.get((store_id, candidate))
        if hit:
            return hit
    return None


def split_amount(total: Decimal, shares: list[Share]) -> list[tuple[Share, Decimal]]:
    """按 weight 比例分到分，尾差归最后一行，Σ = total。weight 全 0 返回空。"""
    weight_sum = sum((s.weight for s in shares), Decimal("0"))
    if not shares or weight_sum == 0:
        return []
    out: list[tuple[Share, Decimal]] = []
    allocated = Decimal("0")
    for index, share in enumerate(shares):
        if index == len(shares) - 1:
            amount = total - allocated
        else:
            amount = (total * share.weight / weight_sum).quantize(CENT, rounding=ROUND_HALF_UP)
            allocated += amount
        out.append((share, amount))
    return out


def parse_rebate_period(detail: str) -> tuple[date, date] | None:
    m = PERIOD_IN_DETAIL.search(detail or "")
    if not m:
        return None
    try:
        start = date(2000 + int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        end = date(2000 + int(m.group(6)), MONTHS[m.group(4)], int(m.group(5)))
    except (KeyError, ValueError):
        return None
    return start, end


def cargo_in_detail(detail: str) -> str:
    m = CARGO_IN_DETAIL.search(detail or "")
    return m.group(1) if m else ""


def _close(base_total: Decimal, amount: Decimal) -> bool:
    expected = base_total * REBATE_RATE
    tolerance = max(Decimal("0.05"), abs(amount) * Decimal("0.01"))
    return abs(expected - amount) <= tolerance


def allocate_inbound(
    amount: Decimal,
    items: list[tuple[str, str, Listing | None, Decimal, Decimal]],
) -> Allocation:
    """入库运费按货件商品分：items = (gtin, msku, listing, shipped, declared)。

    实发有数用实发，否则用申报。
    """
    use_shipped = any(shipped > 0 for _, _, _, shipped, _ in items)
    shares = [
        Share(
            gtin=gtin,
            item_id=(listing.item_id if listing else ""),
            msku=msku or (listing.msku if listing else ""),
            local_sku=(listing.local_sku if listing else ""),
            weight=(shipped if use_shipped else declared),
            basis=(
                f"货件按{'实发' if use_shipped else '申报'}数量 "
                f"{int(shipped if use_shipped else declared)}"
            ),
        )
        for gtin, msku, listing, shipped, declared in items
        if (shipped if use_shipped else declared) > 0
    ]
    children = split_amount(amount, shares)
    if not children:
        return Allocation(ATTR_UNALLOCATED, note="货件商品明细还没有（等领星货件同步）")
    return Allocation(
        ATTR_ALLOCATED,
        children,
        note=f"按货件商品{'实发' if use_shipped else '申报'}数量分到 {len(children)} 个商品",
    )


def allocate_no_gtin(
    *,
    fee_type: str,
    reason_code: str,
    detail: str,
    amount: Decimal,
    cargo_shares: dict[str, list[Share]],
    storage_base: dict[tuple[str, str], tuple[Decimal, Decimal, Listing | None]] | None,
    fulfillment_base: dict[str, Decimal] | None,
    listings: dict[tuple[str, str], Listing],
    store_id: str,
) -> Allocation:
    """无 GTIN 行的归属。
    cargo_shares：货件号 → 各商品比例（来自入库运费的分摊子行）。
    storage_base：期间内 (gtin, msku) → (原价合计, 无折扣原价合计, listing)，由 service 按期间查好。
    fulfillment_base：期间内无逐行折扣的配送费原价，gtin → 合计，由 service 从存档的结算报表算。
    """
    if fee_type == "Refund" and reason_code == "StorageFeeDispute":
        return Allocation(ATTR_COMPANY, note="仓储费争议退款：无商品信息，记公司")
    if fee_type == "Refund" and reason_code == "InboundTransportationShippingRefund":
        cargo = cargo_in_detail(detail)
        shares = cargo_shares.get(cargo) if cargo else None
        if not shares:
            return Allocation(ATTR_UNALLOCATED, note=f"货件 {cargo or '?'} 的入库运费分摊还没有")
        children = split_amount(amount, shares)
        return Allocation(
            ATTR_ALLOCATED,
            children,
            note=f"货件 {cargo} 按入库运费分摊比例分到 {len(children)} 个商品",
        )
    if fee_type == "DiscountAdjustment":
        period = parse_rebate_period(detail)
        if not period:
            return Allocation(ATTR_UNALLOCATED, note="明细里没有期间，无法分摊")
        start, end = period
        if "storage" in (detail or "").lower():
            if not storage_base:
                return Allocation(ATTR_UNALLOCATED, note=f"期间 {start}~{end} 的仓储费还没有导入")
            total = sum((v[0] for v in storage_base.values()), Decimal("0"))
            nodisc = sum((v[1] for v in storage_base.values()), Decimal("0"))
            use_nodisc = _close(nodisc, amount)
            shares = [
                Share(
                    gtin=gtin,
                    msku=msku,
                    item_id=(listing.item_id if listing else ""),
                    local_sku=(listing.local_sku if listing else ""),
                    weight=(nd if use_nodisc else orig),
                    basis=f"期间内仓储费原价 {(nd if use_nodisc else orig):.2f}",
                )
                for (gtin, msku), (orig, nd, listing) in storage_base.items()
                if (nd if use_nodisc else orig) > 0
            ]
            children = split_amount(amount, shares)
            if not children:
                return Allocation(ATTR_UNALLOCATED, note=f"期间 {start}~{end} 的仓储费基数为 0")
            base_total = nodisc if use_nodisc else total
            ok = _close(base_total, amount)
            return Allocation(
                ATTR_ALLOCATED if ok else ATTR_ALLOCATED_CHECK,
                children,
                note=(
                    f"仓储费返还 {start}~{end}：基数 {base_total:.2f} × 10% = "
                    f"{base_total * REBATE_RATE:.2f}（返还 {amount:.2f}）"
                    + ("" if ok else " ← 基数对不上，按比例先分，待核")
                ),
            )
        if not fulfillment_base:
            return Allocation(ATTR_UNALLOCATED, note=f"期间 {start}~{end} 的配送费报表还没有")
        shares = []
        for gtin, base in fulfillment_base.items():
            if base <= 0:
                continue
            listing = lookup(listings, store_id, gtin)
            shares.append(
                Share(
                    gtin=gtin,
                    item_id=(listing.item_id if listing else ""),
                    msku=(listing.msku if listing else ""),
                    local_sku=(listing.local_sku if listing else ""),
                    weight=base,
                    basis=f"期间内无折扣配送费原价 {base:.2f}",
                )
            )
        children = split_amount(amount, shares)
        if not children:
            return Allocation(ATTR_UNALLOCATED, note=f"期间 {start}~{end} 的无折扣配送费为 0")
        base_total = sum(fulfillment_base.values(), Decimal("0"))
        ok = _close(base_total, amount)
        return Allocation(
            ATTR_ALLOCATED if ok else ATTR_ALLOCATED_CHECK,
            children,
            note=(
                f"配送费返还 {start}~{end}：无折扣行原价 {base_total:.2f} × 10% = "
                f"{base_total * REBATE_RATE:.2f}（返还 {amount:.2f}）"
                + ("" if ok else " ← 基数对不上，按比例先分，待核")
            ),
        )
    if fee_type == INBOUND_FEE:
        return Allocation(ATTR_UNALLOCATED, note="入库运费按货件分，等货件商品明细")
    return Allocation(ATTR_UNALLOCATED, note="没有商品信息，未定规则，请财务调整")


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
