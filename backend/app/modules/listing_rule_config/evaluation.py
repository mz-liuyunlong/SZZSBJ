"""Pure Listing grade and lifecycle evaluators, independent of persistence and jobs.

Inputs are LA-calendar-day evidence. Incomplete days never become zero business days.
Callers MUST provide external proof of advertising/financial completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

ZERO = Decimal("0")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")


def rating_cutoff_la(executed_at: datetime) -> date:
    """Use the Los Angeles calendar day of the execution instant, minus two days."""
    if executed_at.tzinfo is None or executed_at.utcoffset() is None:
        raise ValueError("executed_at must contain a time zone")
    return executed_at.astimezone(LOS_ANGELES).date() - timedelta(days=2)


Grade = Literal["A", "B", "C", "D", "待评级", "不参与评级"]
Lifecycle = Literal[
    "测品期",
    "打品期",
    "启动期",
    "上升期",
    "稳定期",
    "下滑期",
    "断货期",
    "修复期",
    "清货期",
    "已归档",
]
TIER_KEYS = ("lt2", "from2to5", "from5to10", "from10to20", "gte20")


@dataclass(frozen=True)
class FinancialDay:
    day: date
    sales: Decimal
    profit: Decimal | None
    cost_status: str
    missing_cost_codes: tuple[str, ...] = ()
    upstream_confirmed: bool = False

    @property
    def valid(self) -> bool:
        return (
            self.upstream_confirmed
            and self.cost_status == "complete"
            and not self.missing_cost_codes
            and self.profit is not None
            and self.sales >= ZERO
        )


@dataclass(frozen=True)
class GradeResult:
    grade: Grade
    reason: str
    cutoff: date
    valid_short: int
    valid_medium: int
    sales_short: Decimal
    profit_short: Decimal
    sales_medium: Decimal
    profit_medium: Decimal
    margin_short: Decimal | None
    margin_medium: Decimal | None
    weighted_margin: Decimal | None
    invalid_dates: tuple[date, ...]


def grade_listing(
    *,
    cutoff: date,
    stage: str | None,
    days: list[FinancialDay],
    config: ListingGradeRuleConfig,
) -> GradeResult:
    """Calculate weighted profitability only from complete, independently confirmed days."""
    window_start = cutoff - timedelta(days=config.medium_days - 1)
    by_day = {d.day: d for d in days if window_start <= d.day <= cutoff}
    medium_dates = [window_start + timedelta(days=i) for i in range(config.medium_days)]
    short_dates = medium_dates[-config.short_days :]
    valid = {d for d, row in by_day.items() if row.valid}
    mdates = [d for d in medium_dates if d in valid]
    sdates = [d for d in short_dates if d in valid]

    def totals(dates: list[date]) -> tuple[Decimal, Decimal]:
        return (
            sum((by_day[d].sales for d in dates), ZERO),
            sum((by_day[d].profit for d in dates if by_day[d].profit is not None), ZERO),
        )

    ss, sp = totals(sdates)
    ms, mp = totals(mdates)
    sm = sp / ss * 100 if ss > ZERO else None
    mm = mp / ms * 100 if ms > ZERO else None
    invalid = tuple(d for d in medium_dates if d not in valid)
    grade: Grade = "待评级"
    reason = "有效财务日期不足或利润率不可计算"
    weighted = None
    if stage in {"清货期", "已归档"} or stage not in config.included_stages:
        grade, reason = "不参与评级", "生命周期未纳入评级范围"
    elif len(sdates) < config.short_min_valid_days or len(mdates) < config.medium_min_valid_days:
        reason = "财务或广告未确认完整：有效日期不足"
    elif ss == ZERO and sp < ZERO:
        grade, reason = "D", "近短期零销售额且实际亏损"
    elif ss > ZERO and ms > ZERO and sm is not None and mm is not None:
        weighted = (
            sm * Decimal(config.short_weight_percent) + mm * Decimal(config.medium_weight_percent)
        ) / Decimal(100)
        if weighted > config.a_above_percent:
            grade = "A"
        elif weighted >= config.b_min_percent:
            grade = "B"
        elif weighted >= config.c_min_percent:
            grade = "C"
        else:
            grade = "D"
        reason = "已确认财务数据的滚动加权毛利率"
    return GradeResult(
        grade, reason, cutoff, len(sdates), len(mdates), ss, sp, ms, mp, sm, mm, weighted, invalid
    )


@dataclass(frozen=True)
class BusinessDay:
    day: date
    wfs_qty: Decimal | None
    sales_qty: Decimal | None
    strike_price_abnormal: bool | None = None
    buybox_abnormal: bool | None = None
    available_qty: Decimal | None = None


@dataclass(frozen=True)
class LifecycleResult:
    stage: str
    reason: str
    valid_stock_days_30: int
    consecutive_stockout: int
    evidence_complete: bool


def _tier(value: Decimal, tier) -> Decimal:
    if value < 2:
        return Decimal(tier.lt2)
    if value < 5:
        return Decimal(tier.from2to5)
    if value < 10:
        return Decimal(tier.from5to10)
    if value < 20:
        return Decimal(tier.from10to20)
    return Decimal(tier.gte20)


def _streak(records: list[BusinessDay], cutoff: date, field: str, value: bool) -> int:
    """Strict contiguous calendar days; missing/null evidence breaks the streak."""
    by_day = {x.day: x for x in records if x.day <= cutoff}
    count = 0
    cursor = cutoff
    while cursor in by_day:
        row = by_day[cursor]
        result = getattr(row, field)
        if result is None or result != value:
            break
        count += 1
        cursor -= timedelta(days=1)
    return count


def lifecycle_listing(
    *,
    cutoff: date,
    previous_stage: str | None,
    days: list[BusinessDay],
    first_effective_stock: bool,
    config: ListingGradeRuleConfig,
    stockout_previous_stage: str | None = None,
    stockout_days_before_recovery: int | None = None,
    repair_stock_valid_days: int | None = None,
    repair_reasons: tuple[str, ...] = (),
    fulfillment_type: str = "1",
) -> LifecycleResult:
    """Conservative state transition; missing event history is NEVER guessed.

    Pre-commercial, clearance and archive statuses require workflow events.
    A historical stockout stage and repair counters must come from snapshots.
    """
    if previous_stage in {"测品期", "打品期", "清货期", "已归档"}:
        return LifecycleResult(previous_stage, "流程/审批状态优先", 0, 0, True)
    if fulfillment_type not in {"0", "1"}:
        return LifecycleResult(
            previous_stage or "待确认", "履约方式未知，禁止套用WFS/FBM库存规则", 0, 0, False
        )
    is_wfs = fulfillment_type == "1"
    by_day = {d.day: d for d in days if d.day <= cutoff}
    today = by_day.get(cutoff)
    low = config.inventory_repair.low_stock_max_units
    consecutive = 0
    cursor = cutoff
    # Inventory strictly above zero is low-stock, not out-of-stock.
    while is_wfs and first_effective_stock and cursor in by_day:
        obs = by_day[cursor]
        if obs.wfs_qty is None or obs.wfs_qty != ZERO:
            break
        consecutive += 1
        cursor -= timedelta(days=1)
    recent = [by_day.get(cutoff - timedelta(days=i)) for i in range(30)]
    valid_stock30 = sum(
        1 for row in recent
        if row is not None
        and (row.wfs_qty if is_wfs else row.available_qty) is not None
    )
    valid_sales30 = sum(
        1 for row in recent if row is not None and row.sales_qty is not None
    )
    if is_wfs and (today is None or today.wfs_qty is None):
        return LifecycleResult(
            previous_stage or "待确认",
            "WFS当日库存快照缺失，不能当作零库存",
            valid_stock30, consecutive, False,
        )
    if not is_wfs and (today is None or today.sales_qty is None):
        return LifecycleResult(
            previous_stage or "待确认",
            "FBM当日经营记录缺失，不使用WFS库存推断",
            valid_stock30, 0, False,
        )
    if is_wfs and first_effective_stock and consecutive >= config.inventory_repair.stockout_consecutive_days:
        return LifecycleResult(
            "断货期", "连续WFS零库存达到断货门槛", valid_stock30, consecutive, True
        )
    if previous_stage is None:
        if valid_sales30 >= 7 and (not is_wfs or first_effective_stock):
            previous_stage = "启动期"
        else:
            return LifecycleResult(
                "待确认", "首次阶段缺少7天经营记录或首批入库证据",
                valid_stock30, consecutive, False,
            )

    if previous_stage == "断货期":
        if not first_effective_stock or (is_wfs and today.wfs_qty == ZERO):
            return LifecycleResult("断货期", "历史断货尚未证实恢复", valid_stock30, consecutive, False)
        if stockout_days_before_recovery is None:
            return LifecycleResult("断货期", "缺少本轮断货持续天数", valid_stock30, consecutive, False)
        if stockout_days_before_recovery > config.inventory_repair.long_stockout_days:
            return LifecycleResult(
                "修复期", "长期断货恢复，进入修复验收", valid_stock30, consecutive, True
            )
        if stockout_previous_stage is None:
            return LifecycleResult("断货期", "缺少断货前阶段快照", valid_stock30, consecutive, False)
        previous_stage = stockout_previous_stage

    if previous_stage == "修复期":
        if repair_stock_valid_days is None and "stockout" in repair_reasons:
            return LifecycleResult("修复期", "缺少修复累计有效有货日", valid_stock30, consecutive, False)
        if "stockout" in repair_reasons and (
            repair_stock_valid_days is None
            or repair_stock_valid_days < config.inventory_repair.stockout_repair_valid_days
            or (is_wfs and today.wfs_qty == ZERO)
        ):
            return LifecycleResult("修复期", "库存修复验收尚未完成", valid_stock30, consecutive, True)
        for field, reason in (("strike_price_abnormal", "划线价"), ("buybox_abnormal", "购物车")):
            if field in repair_reasons:
                if (
                    _streak(days, cutoff, field, False)
                    < config.inventory_repair.abnormal_recovery_days
                ):
                    return LifecycleResult(
                        "修复期", reason + "恢复确认未完成", valid_stock30, consecutive, False
                    )
        # Leaving repair resets normal-stage evaluation to 启动期 if sample is inadequate.
        previous_stage = "启动期"

    for field, label, threshold in (
        ("strike_price_abnormal", "划线价", config.inventory_repair.strike_price_abnormal_days),
        ("buybox_abnormal", "购物车", config.inventory_repair.buybox_abnormal_days),
    ):
        if _streak(days, cutoff, field, True) > threshold:
            return LifecycleResult("修复期", label + "异常持续超过门槛", valid_stock30, consecutive, True)

    # A stage cannot be inferred from a single latest sales/stock snapshot.
    recent28 = [by_day.get(cutoff - timedelta(days=i)) for i in range(27, -1, -1)]
    weeks = [recent28[i : i + 7] for i in range(0, 28, 7)]
    counts = []
    means = []
    for week in weeks:
        valid = [
            r
            for r in week
            if r is not None and r.sales_qty is not None
        ]
        counts.append(len(valid))
        means.append(sum((r.sales_qty for r in valid), ZERO) / len(valid) if valid else ZERO)

    t = config.lifecycle
    first14 = [
        r
        for r in recent28[:14]
        if r is not None and r.sales_qty is not None
    ]
    last14 = [
        r
        for r in recent28[14:]
        if r is not None and r.sales_qty is not None
    ]
    avg1 = sum((r.sales_qty for r in first14), ZERO) / len(first14) if first14 else ZERO
    avg2 = sum((r.sales_qty for r in last14), ZERO) / len(last14) if last14 else ZERO
    valid3 = all(counts[i] >= t.min_week_valid_days for i in (1, 2, 3))
    growth = (
        valid_sales30 >= t.growth_min_valid_days_30
        and valid3
        and avg1 > 0
        and means[1] < means[2] < means[3]
        and (avg2 - avg1) * 100 / avg1 >= _tier(avg1, t.growth_threshold_pct)
    )
    decline = (
        valid_sales30 >= t.decline_min_valid_days_30
        and valid3
        and avg1 > 0
        and means[1] > means[2] > means[3]
        and (avg1 - avg2) * 100 / avg1 >= _tier(avg1, t.decline_threshold_pct)
    )
    mean4 = sum(means, ZERO) / Decimal(4)
    stable = (
        valid_sales30 >= t.stable_min_valid_days_30
        and all(n >= t.min_week_valid_days for n in counts)
        and all(x > 0 for x in means)
        and mean4 > 0
        and all(abs(m - mean4) * 100 / mean4 <= _tier(mean4, t.stable_tolerance_pct) for m in means)
    )

    if decline:
        return LifecycleResult("下滑期", "有效销量连续下降", valid_stock30, consecutive, True)
    if previous_stage == "稳定期" and (stable or growth):
        return LifecycleResult("稳定期", "成熟稳定期保护", valid_stock30, consecutive, True)
    if growth:
        return LifecycleResult("上升期", "有效销量连续增长", valid_stock30, consecutive, True)
    if stable:
        return LifecycleResult("稳定期", "四周有效销量处于稳定区间", valid_stock30, consecutive, True)
    if previous_stage not in {"启动期", "上升期", "稳定期", "下滑期"}:
        return LifecycleResult(
            "启动期", "修复验收后重新判断，趋势证据不足", valid_stock30, consecutive, False
        )
    return LifecycleResult(
        previous_stage, "趋势证据不足，保留原经营阶段", valid_stock30, consecutive, False
    )
