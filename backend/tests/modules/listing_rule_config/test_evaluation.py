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
    value = grade_listing(
        cutoff=CUTOFF,
        stage="稳定期",
        days=days,
        unconfirmed_account_ad_days=frozenset(),
        config=CFG,
    )
    assert value.grade == "待评级"
    assert value.valid_medium == 0


def test_grade_requires_both_window_sample_minima() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=True)
        for i in range(8, 14)
    ]
    value = grade_listing(
        cutoff=CUTOFF,
        stage="启动期",
        days=days,
        unconfirmed_account_ad_days=frozenset(),
        config=CFG,
    )
    assert value.grade == "待评级"
    assert value.valid_short == 0


def test_grade_exact_boundary_and_nonzero_denominator() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    value = grade_listing(
        cutoff=CUTOFF,
        stage="稳定期",
        days=days,
        unconfirmed_account_ad_days=frozenset(),
        config=CFG,
    )
    assert value.grade == "B"
    assert value.weighted_margin == Decimal(15)


def test_one_account_day_with_zero_ad_spend_blocks_the_whole_rating() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(15), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    value = grade_listing(
        cutoff=CUTOFF,
        stage="稳定期",
        days=days,
        unconfirmed_account_ad_days=frozenset({_day(3)}),
        config=CFG,
    )
    assert value.grade == "待评级"
    assert _day(3) in value.invalid_dates
    assert "账号业务日广告报表为零或缺失" in value.reason


def test_zero_sales_losses_generate_special_d() -> None:
    days = [
        FinancialDay(_day(i), Decimal(0), Decimal(-4), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    value = grade_listing(
        cutoff=CUTOFF,
        stage="稳定期",
        days=days,
        unconfirmed_account_ad_days=frozenset(),
        config=CFG,
    )
    assert value.grade == "D"
    assert value.weighted_margin is None


def test_clearance_excluded_even_if_profitable() -> None:
    days = [
        FinancialDay(_day(i), Decimal(100), Decimal(30), "complete", upstream_confirmed=True)
        for i in range(14)
    ]
    assert (
        grade_listing(
            cutoff=CUTOFF,
            stage="清货期",
            days=days,
            unconfirmed_account_ad_days=frozenset(),
            config=CFG,
        ).grade
        == "不参与评级"
    )


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


def test_fbm_lifecycle_is_excluded_even_with_valid_sales() -> None:
    days = [BusinessDay(_day(i), None, Decimal("2")) for i in range(30)]
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage=None,
        days=days,
        first_effective_stock=False,
        config=CFG,
        fulfillment_type="0",
    )
    assert result.stage == "待确认"
    assert not result.evidence_complete
    assert "非WFS不参与" in result.reason


def test_existing_fbm_stage_is_not_recalculated() -> None:
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage="稳定期",
        days=[BusinessDay(_day(i), None, Decimal("2")) for i in range(30)],
        first_effective_stock=False,
        config=CFG,
        fulfillment_type="0",
    )
    assert result.stage == "稳定期"
    assert not result.evidence_complete


def test_initial_lifecycle_missing_sales_stays_pending() -> None:
    days = [BusinessDay(_day(i), None, None) for i in range(14)]
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage=None,
        days=days,
        first_effective_stock=False,
        config=CFG,
        fulfillment_type="0",
    )
    assert result.stage == "待确认"
    assert not result.evidence_complete


def test_low_positive_wfs_stock_does_not_mean_stockout() -> None:
    days = [BusinessDay(_day(i), Decimal("1"), Decimal("0")) for i in range(7)]
    result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage="稳定期",
        days=days,
        first_effective_stock=True,
        config=CFG,
        fulfillment_type="1",
    )
    assert result.stage != "断货期"


def test_explicit_zero_sales_is_not_equivalent_to_missing_sales() -> None:
    zero = [BusinessDay(_day(i), Decimal("3"), Decimal("0")) for i in range(7)]
    missing = [BusinessDay(_day(i), Decimal("3"), None) for i in range(7)]
    zero_result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage=None,
        days=zero,
        first_effective_stock=True,
        config=CFG,
        fulfillment_type="1",
    )
    missing_result = lifecycle_listing(
        cutoff=CUTOFF,
        previous_stage=None,
        days=missing,
        first_effective_stock=True,
        config=CFG,
        fulfillment_type="1",
    )
    assert zero_result.stage == "启动期"
    assert missing_result.stage == "待确认"
