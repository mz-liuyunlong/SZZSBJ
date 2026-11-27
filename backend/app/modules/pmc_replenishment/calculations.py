"""Pure replenishment calculations for one ItemID (PRP ``PRPs/pmc-purchase-group.md`` §6.1).

The rules follow the 8088 demo (``calc()`` in the replenishment page) clause by
clause, because phase 1 must reconcile with 8088 to zero difference (PRP §11).
Everything here is deterministic, side-effect free and database free: the
period job builds an ``ItemInput`` from DWD/DWS rows and calls
``calculate_item``.

Two deliberate choices keep the numbers identical to 8088:

* arithmetic is binary ``float`` in the same operation order as 8088, so
  ``ceil`` on the gap lands on the same integer;
* adding a fractional number of days rounds half up (8088 ``Math.round``),
  not Python's half-to-even ``round``.

Supply attribution (which ItemID a purchase line belongs to) is *not* done
here; batches arrive already attributed by the 8088 order (D5 = a).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final, Literal

SupplyKind = Literal["wfs", "receiving", "shipped", "domestic", "po", "po_pending", "plan"]

EXCLUDE_TAGS: Final = ("历史产品", "其他用途")
SALES_WINDOW_INSTOCK_DAYS: Final = 30
TIMELINE_HORIZON_DAYS: Final = 400
INBOUND_GAP_STATUS: Final = "INBOUND_GAP"


@dataclass(frozen=True)
class ReplenishmentParams:
    """Rule parameters (PRP B13). Defaults are the 8088 ``PARAMS_INIT`` values."""

    min_qty: int = 50
    approve_days: float = 5
    pack_days: float = 7
    transport_days: float = 30
    shelf_days: float = 10
    cycle_days: int = 14
    safety_days: float = 0
    lead_fallback_days: float = 15
    cap_days: int = 30
    cap_qty: int = 300
    instock_min: int = 5
    low_margin_pct: float = 5


@dataclass(frozen=True)
class SupplyBatch:
    """One supply line already attributed to this ItemID.

    ``order_date`` is used by ``po``; ``created_date`` by ``plan``;
    ``arrival_date`` by ``shipped`` (``None`` = no arrival estimate yet).
    """

    kind: Literal["receiving", "shipped", "domestic", "po", "po_pending", "plan"]
    qty: float
    order_date: date | None = None
    created_date: date | None = None
    arrival_date: date | None = None
    inspected: bool = False
    no_track: bool = False
    ref: str = ""


@dataclass(frozen=True)
class RecentPlan:
    """A Lingxing purchase plan for this ItemID (not voided / rejected)."""

    plan_sn: str
    created_date: date | None


@dataclass(frozen=True)
class MarginWindow:
    margin_pct: float | None


@dataclass(frozen=True)
class ItemInput:
    item_id: str
    today: date
    daily_sales: Sequence[float]
    """Sales per day over the look-back window, oldest first, excluding ``today``."""
    start_stock: Sequence[float] | None
    """Opening WFS available per day (previous day close); ``None`` = old data without it."""
    instock_flags: Sequence[int] | None = None
    """Fallback in-stock flags, used only when ``start_stock`` is ``None``."""
    wfs_available: float = 0
    lead_avg_days: float | None = None
    lead_sample_count: int = 0
    cg_delivery_days: float | None = None
    box_qty: int | None = None
    batches: Sequence[SupplyBatch] = ()
    plans_recent: Sequence[RecentPlan] = ()
    tags: Sequence[str] = ()
    listing_status: str | None = None
    archived: bool = False
    margin_30d: MarginWindow | None = None
    margin_7d: MarginWindow | None = None
    owner_count: int = 1
    box_missing_after_ship: bool = False
    overseas_qty: float = 0
    cycle_override_days: int | None = None


@dataclass(frozen=True)
class SupplyLine:
    kind: SupplyKind
    qty: float
    sellable_date: date | None
    overdue: bool = False
    ref: str = ""


@dataclass(frozen=True)
class Flag:
    code: str
    label: str


@dataclass(frozen=True)
class ItemResult:
    item_id: str
    instock_days_used: int
    lookback_span_days: int
    sales_in_window: float
    daily_sales: float
    days_since_instock: int | None
    no_stock_90: bool
    tail_stock: bool
    max_start_stock: float
    lead_days: float
    lead_source: Literal["real", "lx", "fallback"]
    lead_total_days: float
    cycle_days: int
    supply_lines: tuple[SupplyLine, ...]
    supply: float
    target: float
    suggest_raw: int
    suggest: int
    cap_on: bool
    capped: bool
    boxed: int | None
    sellout_date: date | None
    gap_days: int | None
    resume_date: date | None
    next_arrival_date: date | None
    new_arrival_date: date
    flags: tuple[Flag, ...]
    blocking_plans: tuple[str, ...]
    bad_tags: tuple[str, ...]
    is_draft: bool
    below_min: bool
    extra: Mapping[str, object] = field(default_factory=dict)


# --- helpers ----------------------------------------------------------------------------


def round_half_up(value: float) -> int:
    """8088 ``Math.round``: halves go towards +infinity."""

    return math.floor(value + 0.5)


def add_days(day: date | None, days: float) -> date | None:
    if day is None:
        return None
    return day + timedelta(days=round_half_up(days))


def max_date(a: date | None, b: date | None) -> date | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def days_between(a: date | None, b: date | None) -> int | None:
    if a is None or b is None:
        return None
    return (b - a).days


def format_qty(value: float) -> str:
    """8088 ``toLocaleString("en-US")``: thousands separators, at most 3 decimals."""

    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def box_round(suggest: int, box: int | None, *, cap_on: bool, cap_qty: int) -> int | None:
    """Round to whole cartons: under half a carton rounds down, half or more rounds up,
    never below one carton. Under the cap, never round above the cap (round down, or
    leave unrounded when even one carton exceeds it)."""

    if not box or box <= 0 or suggest <= 0:
        return None
    full = suggest // box
    rem = suggest - full * box
    boxed = max(1, full + 1 if rem >= box / 2 else full) * box
    if cap_on and boxed > cap_qty:
        return full * box if full > 0 else None
    return boxed


# --- main calculation -------------------------------------------------------------------


def calculate_item(item: ItemInput, params: ReplenishmentParams) -> ItemResult:  # noqa: C901
    p = params
    today = item.today
    sales = list(item.daily_sales)
    lookback = len(sales)
    if item.start_stock is not None:
        instock = [1 if v >= p.instock_min else 0 for v in item.start_stock]
    else:
        instock = list(item.instock_flags or [0] * lookback)

    # Daily sales = sales of the latest 30 in-stock days / number of those days (90-day look-back).
    used = 0
    sales_sum = 0.0
    last_in = -1
    first_idx = lookback
    for i in range(lookback - 1, -1, -1):
        if used >= SALES_WINDOW_INSTOCK_DAYS:
            break
        if instock[i]:
            if last_in < 0:
                last_in = i
            used += 1
            sales_sum += sales[i]
            first_idx = i
    max_start = max([0.0, *item.start_stock]) if item.start_stock is not None else 0.0
    tail_stock = last_in < 0 and 0 < max_start < p.instock_min
    span = lookback - first_idx if last_in >= 0 else 0
    daily = sales_sum / used if used > 0 else 0.0
    oos_days = lookback - 1 - last_in if last_in >= 0 else None
    no_stock_90 = last_in < 0

    if item.lead_avg_days is not None:
        lead, lead_src = item.lead_avg_days, "real"
    elif item.cg_delivery_days is not None and item.cg_delivery_days > 0:
        lead, lead_src = item.cg_delivery_days, "lx"
    else:
        lead, lead_src = p.lead_fallback_days, "fallback"
    lead_total = p.approve_days + lead + p.pack_days + p.transport_days + p.shelf_days
    cycle = item.cycle_override_days if item.cycle_override_days is not None else p.cycle_days
    tail = p.pack_days + p.transport_days + p.shelf_days

    lines: list[SupplyLine] = [SupplyLine("wfs", item.wfs_available, today)]
    inspected = False
    overdue_no_track = False
    for b in item.batches:
        overdue = False
        sellable: date | None
        if b.kind == "receiving":
            sellable = today
        elif b.kind == "shipped":
            sell = add_days(b.arrival_date, p.shelf_days)
            overdue = sell is not None and sell < today
            sellable = max_date(sell, today) if sell is not None else None
        elif b.kind == "domestic":
            sellable = add_days(today, tail)
        elif b.kind == "po":
            sellable = add_days(max_date(add_days(b.order_date, lead), today), tail)
        elif b.kind == "po_pending":
            sellable = add_days(today, lead + tail)
        else:  # plan
            sellable = add_days(
                max_date(add_days(b.created_date, p.approve_days), today), lead + tail
            )
        inspected = inspected or b.inspected
        overdue_no_track = overdue_no_track or (overdue and b.no_track)
        lines.append(SupplyLine(b.kind, b.qty, sellable, overdue, b.ref))

    supply = sum(line.qty for line in lines)
    target = daily * (lead_total + cycle + p.safety_days)
    gap = target - supply
    suggest_raw = math.ceil(gap) if gap > 0 else 0
    cap_on = used < p.cap_days
    capped = cap_on and suggest_raw > p.cap_qty
    suggest = p.cap_qty if capped else suggest_raw
    boxed = box_round(suggest, item.box_qty, cap_on=cap_on, cap_qty=p.cap_qty)

    # Stock-out timeline: today's sellable stock runs down by daily sales; later lines join on
    # their sellable date.
    sellout: date | None = None
    gap_days: int | None = 0  # 8088: 0 when never sold out; None when no arrival after sell-out
    resume: date | None = None
    future = sorted(
        (ln for ln in lines if ln.sellable_date and ln.sellable_date > today and ln.qty > 0),
        key=lambda ln: ln.sellable_date or today,
    )
    next_arrival = future[0].sellable_date if future else None
    if daily > 0:
        stock = sum(ln.qty for ln in lines if ln.sellable_date == today)
        arrivals: dict[int, float] = {}
        for ln in future:
            t = (ln.sellable_date - today).days  # type: ignore[operator]
            arrivals[t] = arrivals.get(t, 0) + ln.qty
        for t in range(TIMELINE_HORIZON_DAYS + 1):
            if t > 0:
                stock += arrivals.get(t, 0)
            stock -= daily
            if stock < 0:
                sellout = today + timedelta(days=t)
                later = sorted(x for x in arrivals if x > t)
                if later:
                    resume = today + timedelta(days=later[0])
                    gap_days = later[0] - t
                else:
                    gap_days = None
                break

    flags: list[Flag] = []
    if item.archived:
        flags.append(Flag("archived", "已归档 · 不出草稿"))
    if any(ln.overdue for ln in lines):
        flags.append(Flag("overdue_unshelved", "已过可售日未上架"))
    if inspected:
        flags.append(Flag("inspected", "被查验"))
    if overdue_no_track:
        flags.append(Flag("overdue_no_track", "超期无物流轨迹"))
    bad_tags = tuple(t for t in item.tags if t in EXCLUDE_TAGS)
    # A plan already exists in Lingxing within the cycle -> no draft. A plan without a
    # creation date counts as recent (8088 compares ``null <= R`` as true).
    blocking = tuple(
        pl.plan_sn
        for pl in item.plans_recent
        if (days_between(pl.created_date, today) or 0) <= cycle
    )
    if blocking:
        flags.append(Flag("recent_plan", f"{cycle} 天内已有采购计划"))
    if bad_tags:
        flags.append(Flag("excluded_tag", f"标签 {' / '.join(bad_tags)}"))
    if item.listing_status and item.listing_status != "PUBLISHED":
        flags.append(Flag("listing_not_published", f"Listing {item.listing_status}"))
    if capped:
        flags.append(Flag("capped", f"单次封顶 {p.cap_qty}"))
    m30 = item.margin_30d.margin_pct if item.margin_30d else None
    m7 = item.margin_7d.margin_pct if item.margin_7d else None
    if m30 is not None and m30 < p.low_margin_pct and (m7 is None or m7 < p.low_margin_pct):
        flags.insert(0, Flag("low_margin", "低利润 · 建议不补"))
    if tail_stock:
        flags.append(Flag("tail_stock", f"尾货 <{p.instock_min} 件"))
    elif no_stock_90:
        flags.append(Flag("no_stock_90", "近 90 天无库存"))
    if 0 < item.wfs_available < p.instock_min:
        flags.append(
            Flag(
                "low_wfs",
                f"库存 {format_qty(item.wfs_available)} 件（<{p.instock_min} 视同断货）",
            )
        )
    elif used < SALES_WINDOW_INSTOCK_DAYS:
        flags.append(Flag("few_instock_days", f"有库存天数 {used} 天"))
    if oos_days and oos_days > 0 and daily > 0:
        flags.append(Flag("out_of_stock", f"已断货 {oos_days} 天"))
    if item.lead_avg_days is None:
        flags.append(Flag("no_lead_sample", "采购交期无样本"))
    if item.owner_count > 1:
        flags.append(Flag("multiple_owners", "多个负责人"))
    if item.box_missing_after_ship:
        flags.append(Flag("box_missing", "缺默认箱规"))
    if item.overseas_qty:
        flags.append(Flag("overseas", f"海外仓 {format_qty(item.overseas_qty)}（未计入）"))

    listing_ok = not item.listing_status or item.listing_status == "PUBLISHED"
    is_draft = (
        daily > 0
        and suggest >= p.min_qty
        and listing_ok
        and not bad_tags
        and not blocking
        and not item.archived
    )
    return ItemResult(
        item_id=item.item_id,
        instock_days_used=used,
        lookback_span_days=span,
        sales_in_window=sales_sum,
        daily_sales=daily,
        days_since_instock=oos_days,
        no_stock_90=no_stock_90,
        tail_stock=tail_stock,
        max_start_stock=max_start,
        lead_days=lead,
        lead_source=lead_src,  # type: ignore[arg-type]
        lead_total_days=lead_total,
        cycle_days=cycle,
        supply_lines=tuple(lines),
        supply=supply,
        target=target,
        suggest_raw=suggest_raw,
        suggest=suggest,
        cap_on=cap_on,
        capped=capped,
        boxed=boxed,
        sellout_date=sellout,
        gap_days=gap_days,
        resume_date=resume,
        next_arrival_date=next_arrival,
        new_arrival_date=today + timedelta(days=round_half_up(lead_total)),
        flags=tuple(flags),
        blocking_plans=blocking,
        bad_tags=bad_tags,
        is_draft=is_draft,
        below_min=daily > 0 and 0 < suggest < p.min_qty,
    )
