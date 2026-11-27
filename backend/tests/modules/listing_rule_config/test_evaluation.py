from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.modules.listing_rule_config.evaluation import (
    BusinessDay,
    FinancialDay,
    grade_listing,
    lifecycle_listing,
    rating_cutoff_la,
)
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CFG = ListingGradeRuleConfig()
CUTOFF = date(2026, 10, 23)


def _day(n: int) -> date:
    return CUTOFF - timedelta(days=n)


def test_grade_never_counts_unconfirmed_ads_as_zero() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=False)
        for i in range(14)
    ]
    value = grade_listing(cutoff=CUTOFF, stage="稳定期", days=days, config=CFG)
    assert value.grade == "待评级"
    assert value.valid_medium == 0


def test_grade_requires_both_window_sample_minima() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=True)
        for i in range(8, 14)
    ]
    value = grade_listing(cutoff=CUTOFF, stage="启动期", days=days, config=CFG)
    assert value.grade == "待评级"
    assert value.valid_short == 0


def test_grade_exact_boundary_and_nonzero_denominator() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    value = grade_listing(cutoff=CUTOFF, stage="稳定期", days=days, config=CFG)
    assert value.grade == "B"
    assert value.weighted_margin == Decimal(15)


def test_zero_sales_losses_generate_special_d() -> None:
    days = [
        FinancialDay(_day(i), Decimal(0), Decimal(-4), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    value = grade_listing(cutoff=CUTOFF, stage="稳定期", days=days, config=CFG)
    assert value.grade == "D"
    assert value.weighted_margin is None


def test_clearance_excluded_even_if_profitable() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(30), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    assert grade_listing(cutoff=CUTOFF, stage="清货期", days=days, config=CFG).grade == "不参与评级"


def test_new_listing_never_classed_stockout_without_prior_effective_stock() -> None:
    days = [BusinessDay(_day(i), Decimal(0), Decimal(0)) for i in range(10)]
    value = lifecycle_listing(
        cutoff=CUTOFF, previous_stage="启动期", days=days, first_effective_stock=False, config=CFG
    )
    assert value.stage == "启动期"


def test_stockout_after_verified_stock() -> None:
    days = [BusinessDay(_day(i), Decimal(0), Decimal(0)) for i in range(7)]
    value = lifecycle_listing(
        cutoff=CUTOFF, previous_stage="稳定期", days=days, first_effective_stock=True, config=CFG
    )
    assert value.stage == "断货期"


def test_missing_stock_snapshot_preserves_state() -> None:
    days = [BusinessDay(_day(i), Decimal(0), Decimal(0)) for i in range(1, 8)]
    value = lifecycle_listing(
        cutoff=CUTOFF, previous_stage="稳定期", days=days, first_effective_stock=True, config=CFG
    )
    assert value.stage == "稳定期"
    assert not value.evidence_complete


def test_la_t_minus_two_in_summer_and_winter() -> None:
    assert rating_cutoff_la(
        datetime(2026, 10, 25, 22, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    ) == date(2026, 10, 23)
    assert rating_cutoff_la(
        datetime(2026, 12, 25, 22, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    ) == date(2026, 12, 23)


def test_short_stockout_recovers_previous_stage_without_sales_trend() -> None:
    # Seven contiguous low-stock days, then positive WFS stock again.
    # No valid sales observations: recovery is still an evidenced transition.
    days = [BusinessDay(_day(0), Decimal(20), None)] + [
        BusinessDay(_day(i), Decimal(0), None) for i in range(1, 8)
    ]
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage="断货期",
        days=days,
        first_effective_stock=True,
        stockout_previous_stage="稳定期",
        stockout_days_before_recovery=7,
        config=CFG,
    )
    assert result.stage == "稳定期"
    assert result.evidence_complete


def test_short_stockout_without_previous_stage_stays_blocked() -> None:
    days = [BusinessDay(_day(0), Decimal(20), None)] + [
        BusinessDay(_day(i), Decimal(0), None) for i in range(1, 8)
    ]
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage="断货期",
        days=days,
        first_effective_stock=True,
        stockout_days_before_recovery=7,
        stockout_previous_stage=None,
        config=CFG,
    )
    assert result.stage == "断货期"
    assert not result.evidence_complete
