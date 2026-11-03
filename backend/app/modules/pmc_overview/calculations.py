"""PMC overview board: rule judgement layer (pure functions, no framework or DB).

Business source: 8088 DEMO ``features/pmc-overview/drafts/src/app.jsx``
``calcItem()`` (overview-specific part) and ``computeAll()``. Daily sales,
supply segments, sell-out timeline and suggestion are *inputs* here: they are
computed once by the replenishment module (PRP pmc-overview D2) and never
recomputed in this module.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.modules.pmc_overview.rules import OverviewParams

DraftMode = Literal["replenishment", "demo_8088"]

EXCLUDE_TAGS = ("历史产品", "其他用途")

# Colour tokens mirror 8088 tag colours; the frontend maps them to theme tokens.
LEVEL_RED = "red"
LEVEL_VOLCANO = "volcano"
LEVEL_ORANGE = "orange"


@dataclass(frozen=True)
class SupplyBatch:
    """One mutually exclusive supply row (WFS available row excluded)."""

    kind: str  # receiving | shipped | domestic | po | po_pending | plan
    qty: int
    date: str = ""  # expected sellable date (ISO), from replenishment
    overdue: bool = False  # shipped and expected sellable date already passed
    no_track: bool = False
    inspected: bool = False
    overseas_ship: bool = False
    signed: int = 0
    putaway: int = 0
    order: str = ""  # PO order date / pending date
    created: str = ""  # plan created date
    status: str = ""  # plan status (待审批 / 待采购 / ...)
    ref: str = ""  # plan / PO / cargo number


@dataclass(frozen=True)
class DomesticBatchAge:
    age: int  # days in Huizhou warehouse
    qty: int


@dataclass(frozen=True)
class RecentPlan:
    plan: str
    created: str
    qty: int


@dataclass(frozen=True)
class ItemInput:
    """Per-ItemID input = replenishment result + a few raw facts."""

    item_id: str
    sku: str
    daily: float
    n30: int  # in-stock days used for daily sales (max 30)
    oos_days: int | None  # None = no in-stock day within 90 days
    no_stock_90: bool
    tail_stock: bool
    max_start: int
    supply: int  # sum of mutually exclusive segments incl. WFS available
    wm_available: int
    sellout: str | None
    gap_days: int | None
    resume: str | None
    next_date: str | None
    lead_total: float  # L
    lead_avg: float | None  # last-5-orders actual lead time
    suggest: int
    suggest_raw: int
    cap_on: bool
    capped: bool
    box: int = 0
    box_missing_after_ship: bool = False
    listing: str = ""
    tags: tuple[str, ...] = ()
    plans_recent: tuple[RecentPlan, ...] = ()
    draft_id: str = ""
    draft_reason: str = ""  # replenishment's own "why no draft" text (draft_mode=replenishment)
    overseas_sku: int = 0
    batches: tuple[SupplyBatch, ...] = ()
    dom_rows: tuple[DomesticBatchAge, ...] = ()


@dataclass
class Issue:
    label: str
    level: str
    detail: str


@dataclass
class ItemResult:
    item_id: str
    sku: str
    stock_ok: bool
    oos: bool
    risk: bool
    cover: int | None
    over: str | None  # 正常 / 库存过剩 / 严重过剩 / None
    stale: bool
    low_days: bool
    exec_flags: list[Issue] = field(default_factory=list)
    sc_flags: list[Issue] = field(default_factory=list)
    dom_over_qty: int = 0
    dom_max: int | None = None
    overseas_total: int = 0
    overseas_alloc: int = 0
    overseas_left: int = 0
    purchase: int = 0
    boxed: int | None = None
    listing_bad: bool = False
    tag_bad: list[str] = field(default_factory=list)
    is_draft: bool = False
    draft_text: str = ""
    issues: list[Issue] = field(default_factory=list)
    main: str = "正常"
    level: str = "green"
    cats: list[str] = field(default_factory=list)


def _days_between(a: str, b: str) -> int | None:
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except (TypeError, ValueError):
        return None


def _fmt(n: float | int) -> str:
    return f"{int(round(n)):,}"


def _fmt1(n: float) -> str:
    v = math.floor(n * 10 + 0.5) / 10
    return f"{v:,.1f}".rstrip("0").rstrip(".")


def judge_item(it: ItemInput, p: OverviewParams, today: str) -> ItemResult:
    """Overview-only judgements for one ItemID (8088 calcItem, overview part)."""
    exec_flags: list[Issue] = []
    sc_flags: list[Issue] = []
    s3lead = it.lead_avg if it.lead_avg is not None else p.s3_fallback
    overdue_qty = notrack_qty = insp_qty = 0
    for b in it.batches:
        if b.kind == "plan":
            age = _days_between(b.created, today) or 0
            if b.status == "待审批" and age > p.s1_days:
                exec_flags.append(
                    Issue(
                        "采购计划待审批超时",
                        LEVEL_ORANGE,
                        f"{b.ref} 待审批 {age} 天（> {p.s1_days} 天）",
                    )
                )
            if b.status == "待采购" and age > p.s2_days:
                exec_flags.append(
                    Issue(
                        "待采购超时", LEVEL_ORANGE, f"{b.ref} 待采购 {age} 天（> {p.s2_days} 天）"
                    )
                )
        elif b.kind == "po_pending":
            age = _days_between(b.order, today) or 0
            if age > p.s2_days:
                exec_flags.append(
                    Issue(
                        "待下单超时", LEVEL_ORANGE, f"{b.ref} 待下单 {age} 天（> {p.s2_days} 天）"
                    )
                )
        elif b.kind == "po":
            age = _days_between(b.order, today) or 0
            if age > s3lead:
                sc_flags.append(
                    Issue(
                        "采购已下单未到货超期",
                        LEVEL_VOLCANO,
                        f"{b.ref} 下单 {age} 天 > 交期 {round(s3lead)} 天",
                    )
                )
        elif b.kind == "shipped":
            if b.overdue:
                overdue_qty += b.qty
                if b.no_track and not b.overseas_ship:
                    notrack_qty += b.qty
            if b.inspected:
                insp_qty += b.qty

    stock_ok = it.supply >= p.min_supply_issue
    if stock_ok and overdue_qty:
        sc_flags.append(Issue("已过预计可售日未上架", LEVEL_VOLCANO, f"{overdue_qty} 件"))
    if stock_ok and notrack_qty:
        sc_flags.append(
            Issue(
                "超期无物流轨迹", LEVEL_VOLCANO, f"{notrack_qty} 件（海外仓发出的货件不套此规则）"
            )
        )
    if stock_ok and insp_qty:
        sc_flags.append(Issue("被查验", LEVEL_VOLCANO, f"{insp_qty} 件，周期无法评估"))
    if it.box_missing_after_ship:
        sc_flags.append(Issue("缺默认箱规", LEVEL_VOLCANO, "已发过货仍无默认箱规"))

    dom_over = [d for d in it.dom_rows if d.age > p.domestic_days]
    dom_over_qty = sum(d.qty for d in dom_over)
    dom_max = max((d.age for d in it.dom_rows), default=None)
    if stock_ok and dom_over_qty >= p.domestic_min_qty:
        longest = max(d.age for d in dom_over)
        exec_flags.append(
            Issue(
                "国内仓在仓超期",
                LEVEL_ORANGE,
                f"{dom_over_qty} 件超 {p.domestic_days} 天（最长 {longest} 天）· 仓库应尽快发出",
            )
        )

    sales_ok = it.n30 >= p.sales_min_days
    cover_raw = it.supply / it.daily if (sales_ok and it.daily > 0) else None
    over: str | None = None
    if cover_raw is not None:
        over = "严重过剩" if cover_raw > p.over2 else "库存过剩" if cover_raw > p.over1 else "正常"
    stale = stock_ok and sales_ok and it.daily == 0 and it.supply > 0
    low_days = stock_ok and not it.no_stock_90 and it.n30 < 30
    oos = it.daily > 0 and it.wm_available < p.instock_min
    risk = bool(it.sellout) and (
        (it.gap_days or 0) > 0
        or (it.resume is None and (_days_between(today, it.sellout or "") or 0) <= it.lead_total)
    )
    return ItemResult(
        item_id=it.item_id,
        sku=it.sku,
        stock_ok=stock_ok,
        oos=oos,
        risk=risk,
        cover=None if cover_raw is None else _js_round(cover_raw),
        over=over if stock_ok else None,
        stale=stale,
        low_days=low_days,
        exec_flags=exec_flags,
        sc_flags=sc_flags,
        dom_over_qty=dom_over_qty,
        dom_max=dom_max,
    )


def _js_round(x: float) -> int:
    """Math.round semantics (half up), not Python banker's rounding."""
    return math.floor(x + 0.5)


def allocate_overseas(items: list[ItemInput], results: dict[str, ItemResult]) -> None:
    """Overseas stock is per SKU, never split into ItemIDs; earliest sell-out first."""
    by_sku: dict[str, list[ItemInput]] = defaultdict(list)
    for it in items:
        by_sku[it.sku].append(it)
    for lst in by_sku.values():
        ov = max((x.overseas_sku or 0 for x in lst), default=0)
        remain = ov
        ordered = sorted(lst, key=lambda x: (x.sellout or "9999", -x.suggest))
        for x in ordered:
            r = results[x.item_id]
            r.overseas_total = ov
            r.overseas_alloc = 0
            if x.suggest > 0 and remain > 0:
                r.overseas_alloc = min(remain, x.suggest)
                remain -= r.overseas_alloc
        for x in lst:
            results[x.item_id].overseas_left = remain


def _boxed(purchase: int, box: int, cap_on: bool, cap_qty: int) -> int | None:
    if not (box > 0 and purchase > 0):
        return None
    n = purchase // box
    rem = purchase - n * box
    boxed = max(1, n + 1 if rem >= box / 2 else n) * box
    if cap_on and boxed > cap_qty:
        return n * box if n > 0 else None
    return boxed


def finish_item(
    it: ItemInput, r: ItemResult, p: OverviewParams, today: str, draft_mode: DraftMode
) -> None:
    """Draft status, issue list, main problem and categories (8088 computeAll)."""
    r.purchase = max(0, it.suggest - r.overseas_alloc)
    r.boxed = _boxed(r.purchase, it.box, it.cap_on, p.cap_qty)
    r.listing_bad = bool(it.listing) and it.listing != "PUBLISHED"
    r.tag_bad = [t for t in it.tags if t in EXCLUDE_TAGS]
    block = [pl for pl in it.plans_recent if (_days_between(pl.created, today) or 0) <= p.cycle]
    if draft_mode == "replenishment":
        r.is_draft = bool(it.draft_id)
    else:
        r.is_draft = (
            it.daily > 0
            and r.purchase >= p.min_qty
            and not r.listing_bad
            and not r.tag_bad
            and not block
        )

    if r.tag_bad and it.suggest > 0:
        r.draft_text = (
            f"标签 {' / '.join(r.tag_bad)}，不出草稿（建议 {_fmt(it.suggest)} 件仅供参考）"
        )
    elif block and it.suggest > 0:
        b0 = block[0]
        r.draft_text = (
            f"{p.cycle} 天内已有采购计划 {b0.plan}（{b0.created[5:]} 建 {_fmt(b0.qty)} 件），"
            f"不出草稿（建议 {_fmt(it.suggest)} 件仅供参考）"
        )
    elif r.is_draft:
        extra = f"（扣海外仓 {_fmt(r.overseas_alloc)} 件）" if r.overseas_alloc else ""
        r.draft_text = f"本轮草稿 建议 {_fmt(r.boxed or r.purchase)} 件{extra}"
    elif draft_mode == "replenishment" and (it.draft_reason or r.purchase >= p.min_qty):
        r.draft_text = (
            it.draft_reason or f"本轮未出草稿（以自动补货为准；建议 {_fmt(it.suggest)} 件）"
        )
    elif it.suggest > 0 and r.overseas_alloc:
        r.draft_text = f"海外仓先补 {_fmt(r.overseas_alloc)} 件，不出草稿"
    elif it.suggest > 0:
        r.draft_text = f"建议 {_fmt(it.suggest)} 件 < {p.min_qty}，不出草稿"
    else:
        r.draft_text = "本轮不需补货"

    issues: list[Issue] = []
    if r.tag_bad:
        issues.append(
            Issue(
                f"标签 {' / '.join(r.tag_bad)}",
                "default",
                "领星产品标签，不出采购计划草稿；库存 / 在途照常计入",
            )
        )
    if r.listing_bad:
        issues.append(
            Issue(
                "Listing 异常",
                "magenta",
                f"Walmart 在线商品状态 {it.listing}，不出草稿；链路上 {_fmt(it.supply)} 件",
            )
        )
    if r.oos:
        days = "90+" if it.oos_days is None else str(it.oos_days)
        stock = (
            f"（库存 {_fmt(it.wm_available)} 件 < {p.instock_min} 视同断货）"
            if it.wm_available > 0
            else ""
        )
        nxt = f"，下一批 {it.next_date} 可售" if it.next_date else "，无来货"
        issues.append(
            Issue("已断货", LEVEL_RED, f"已断货 {days} 天{stock}，日销 {_fmt1(it.daily)}{nxt}")
        )
    if r.risk and not r.oos:
        tail = f"，断 {it.gap_days} 天，{it.resume} 恢复" if it.gap_days else "，之后无来货"
        issues.append(Issue("断货风险", LEVEL_RED, f"能卖到 {it.sellout}{tail}"))
    issues.extend(r.sc_flags)
    issues.extend(r.exec_flags)
    if r.over == "严重过剩":
        issues.append(Issue("严重过剩", "purple", f"覆盖 {_fmt(r.cover or 0)} 天（> {p.over2}）"))
    if r.over == "库存过剩":
        issues.append(
            Issue("库存过剩", "gold", f"覆盖 {_fmt(r.cover or 0)} 天（{p.over1}–{p.over2}）")
        )
    if r.stale:
        issues.append(
            Issue("滞销", "default", f"有货 {it.n30} 天销量 0，仍有 {_fmt(it.supply)} 件")
        )
    if it.tail_stock and r.stock_ok:
        issues.append(
            Issue(
                f"尾货 <{p.instock_min} 件",
                "default",
                f"近 90 天库存最多 {it.max_start} 件，从没到过 {p.instock_min} 件，"
                f"算不出日销；链路上有 {_fmt(it.supply)} 件",
            )
        )
    elif it.no_stock_90 and r.stock_ok:
        issues.append(
            Issue(
                "近 90 天无库存",
                "default",
                f"90 天里没有一天期初库存 ≥ {p.instock_min} 件，"
                f"算不出日销；链路上有 {_fmt(it.supply)} 件",
            )
        )
    if r.low_days:
        note = f"（< {p.sales_min_days}，不判过剩 / 滞销）" if it.n30 < p.sales_min_days else ""
        issues.append(
            Issue(f"有库存天数 {it.n30} 天", "cyan", f"近 90 天只有 {it.n30} 个有货日{note}")
        )
    if r.overseas_alloc:
        issues.append(
            Issue(
                "海外仓可补",
                "blue",
                f"海外仓 {_fmt(r.overseas_total)} 件，先补 {_fmt(r.overseas_alloc)} 件",
            )
        )
    if it.capped:
        issues.append(
            Issue(
                f"单次封顶 {_fmt(p.cap_qty)}",
                LEVEL_ORANGE,
                f"有货日 {it.n30} 天（< {p.cap_days}），按公式建议 {_fmt(it.suggest_raw)} 件，"
                f"单次最多补 {_fmt(p.cap_qty)} 件",
            )
        )
    r.issues = issues
    r.main = issues[0].label if issues else "正常"
    r.level = issues[0].level if issues else "green"

    cats: list[str] = []
    if r.listing_bad:
        cats.append("Listing 异常")
    if r.oos:
        cats.append("已断货")
    if r.risk and not r.oos:
        cats.append("断货风险")
    if r.sc_flags:
        cats.append("供应链异常")
    if r.exec_flags:
        cats.append("执行异常")
    if r.over in ("库存过剩", "严重过剩"):
        cats.append(r.over)
    if r.stale:
        cats.append("滞销")
    if it.no_stock_90 and r.stock_ok:
        cats.append("近 90 天无库存")
    if r.low_days:
        cats.append("有库存不足 30 天")
    if r.overseas_alloc:
        cats.append("海外仓可补")
    if any(f.label == "已过预计可售日未上架" for f in r.sc_flags):
        cats.append("超期未上架")
    if any(f.label == "缺默认箱规" for f in r.sc_flags):
        cats.append("缺默认箱规")
    r.cats = cats


# Sort priority of the main table (8088 App PRI / catOf).
CATEGORY_PRIORITY = {
    "Listing 异常": -1,
    "已断货": 0,
    "断货风险": 1,
    "供应链异常": 2,
    "执行异常": 3,
    "严重过剩": 4,
    "库存过剩": 5,
    "滞销": 6,
    "海外仓可补": 7,
    "近 90 天无库存": 8,
    "有库存不足 30 天": 9,
    "正常": 10,
}


def sort_category(it: ItemInput, r: ItemResult) -> str:
    if r.listing_bad:
        return "Listing 异常"
    if r.oos:
        return "已断货"
    if r.risk:
        return "断货风险"
    if r.sc_flags:
        return "供应链异常"
    if r.exec_flags:
        return "执行异常"
    if r.over in ("严重过剩", "库存过剩"):
        return r.over
    if r.stale:
        return "滞销"
    if r.overseas_alloc:
        return "海外仓可补"
    if it.no_stock_90 and r.stock_ok:
        return "近 90 天无库存"
    if r.low_days:
        return "有库存不足 30 天"
    return "正常"


def summarize(results: Iterable[ItemResult]) -> dict[str, int]:
    """Summary cards (8088 computeAll kpi)."""
    rows = list(results)

    def cnt(pred) -> int:  # type: ignore[no-untyped-def]
        return sum(1 for r in rows if pred(r))

    return {
        "items": len(rows),
        "listing_bad": cnt(lambda r: r.listing_bad),
        "oos": cnt(lambda r: r.oos),
        "risk": cnt(lambda r: r.risk and not r.oos),
        "over1": cnt(lambda r: r.over == "库存过剩"),
        "over2": cnt(lambda r: r.over == "严重过剩"),
        "stale": cnt(lambda r: r.stale),
        "supply_chain": cnt(lambda r: bool(r.sc_flags)),
        "execution": cnt(lambda r: bool(r.exec_flags)),
        "no_stock_90": cnt(lambda r: "近 90 天无库存" in r.cats),
        "low_days": cnt(lambda r: r.low_days),
        "overseas": cnt(lambda r: r.overseas_alloc > 0),
        "drafts": cnt(lambda r: r.is_draft),
        "normal": cnt(lambda r: not r.issues),
        "low_supply": cnt(lambda r: not r.stock_ok),
        "overdue": cnt(lambda r: "超期未上架" in r.cats),
        "box_missing": cnt(lambda r: "缺默认箱规" in r.cats),
    }


def compute_all(
    items: list[ItemInput], p: OverviewParams, today: str, draft_mode: DraftMode = "replenishment"
) -> tuple[list[ItemResult], dict[str, int]]:
    """Run the whole overview judgement for one round (data day)."""
    results = {it.item_id: judge_item(it, p, today) for it in items}
    allocate_overseas(items, results)
    for it in items:
        finish_item(it, results[it.item_id], p, today, draft_mode)
    ordered = [results[it.item_id] for it in items]
    return ordered, summarize(ordered)
