"""Read-only, same-source daily-new-product profit regression tests."""

from datetime import date
from decimal import Decimal

from app.modules.new_products.testing_profit import (
    build_operating_daily_same_source,
    calculate_testing_profit,
)

CUT = date(2026, 11, 16)
START = date(2026, 11, 14)


def mart_row(
    day: date,
    *,
    sample: int = 0,
    sales: str = "49.98",
    units: int = 2,
    orders: int = 2,
    sem: str = "2",
    fallback_sp: str = "0",
) -> dict:
    total_units = units + sample
    return {
        "day": day,
        "sales_qty": units,
        "order_count": orders,
        "sales_amount": sales,
        "sales_currency_code": "USD",
        "sample_qty": sample,
        "cost_quantity": total_units,
        "ad_spend_amount": fallback_sp,
        "sem_ad_spend_amount": sem,
        "ad_spend_currency_code": "USD",
        "commission_rate": "0.15",
        "purchase_cost_total_usd": str(total_units * 10),
        "first_leg_cost_total_usd": str(total_units * 2),
        "wfs_fee_total_amount": str(total_units * 4),
        "wfs_fee_actual_total_amount": str(total_units * 4),
        "wfs_fee_expected_total_amount": str(total_units * 4),
        "wfs_low_price_surcharge_amount": "0",
        "storage_fee_total_amount": str(total_units),
        "calculation_warnings_json": [],
        "refund_amount": "9.99",  # Intentionally ignored by the SAME score engine.
    }


def fake_sp(rows: list[tuple[date, str]]) -> tuple[dict, list[dict]]:
    return (
        {
            "source_rows": len(rows),
            "incomplete_spend_rows": 0,
            "sp_spend": str(sum((Decimal(n) for _, n in rows), Decimal(0))),
        },
        [{"day": d, "source_rows": 1, "incomplete_spend_rows": 0, "sp_spend": n} for d, n in rows],
    )


def test_sample_refund_and_zero_sale_ad_day_exactly_reconcile():
    first = mart_row(START, sample=1)
    # One day contains no paid sale, but has real ad cost.
    second = mart_row(date(2026, 11, 15), units=0, orders=0, sales="0", sem="1.50")
    sp, by_day = fake_sp([(START, "5"), (date(2026, 11, 15), "3")])
    full = calculate_testing_profit([first, second], sp_data=sp)
    detail = build_operating_daily_same_source(
        [first, second], sp, by_day, cutoff=CUT, first_wfs=START
    )
    assert detail["status"] == "scored"
    rows = {r["date"]: r for r in detail["rows"]}
    paid = rows[START.isoformat()]
    no_sales = rows["2026-11-15"]
    assert paid["sales_units"] == "2"
    assert paid["sales_orders"] == "2"
    assert paid["sales_amount_usd"] == "49.98"
    assert Decimal(paid["invested_usd"]) == Decimal("24")
    assert Decimal(paid["ad_spend_usd"]) == Decimal("7")
    assert Decimal(no_sales["profit_usd"]) == Decimal("-4.50")
    assert no_sales["roi"] is None
    assert no_sales["margin_pct"] is None
    assert detail["totals"]["profit_usd"] == full["profit_usd"]
    assert detail["totals"]["roi"] == full["roi"]
    assert detail["totals"]["margin_pct"] == full["gross_margin_pct"]
    assert detail["totals"]["ad_spend_usd"] == full["ad_spend_usd"]
    assert detail["complete_calendar_days"] is False  # 16th has no MART proof


def test_source_sp_not_double_counted_with_mart_fallback():
    a = mart_row(START, sample=1, fallback_sp="999")
    sp, by_day = fake_sp([(START, "5")])
    result = build_operating_daily_same_source([a], sp, by_day, cutoff=START, first_wfs=START)
    assert result["status"] == "scored"
    assert Decimal(result["totals"]["ad_spend_usd"]) == Decimal("7")


def test_fallback_sp_is_used_only_if_no_fact_sp_rows():
    a = mart_row(START, fallback_sp="5")
    result = build_operating_daily_same_source(
        [a],
        {"source_rows": 0, "incomplete_spend_rows": 0, "sp_spend": None},
        [],
        cutoff=START,
        first_wfs=START,
    )
    assert result["status"] == "scored"
    assert Decimal(result["totals"]["ad_spend_usd"]) == Decimal("7")


def test_missing_cost_blocks_daily_profit_not_zero():
    row = mart_row(START)
    row["commission_rate"] = None
    sp, by_day = fake_sp([(START, "5")])
    result = build_operating_daily_same_source([row], sp, by_day, cutoff=START, first_wfs=START)
    assert result["status"] == "unverified"
    assert result["totals"] is None
    assert result["rows"] == []
    assert "commission_rate_missing" in result["missing"]


def test_bad_or_stale_sp_daily_evidence_blocks_totals():
    row = mart_row(START)
    sp, by_day = fake_sp([(START, "5")])
    by_day[0]["sp_spend"] = "4.99"
    result = build_operating_daily_same_source([row], sp, by_day, cutoff=START, first_wfs=START)
    assert result["reason"] == "sp_daily_aggregation_not_reconciled"


def test_pre_wfs_sample_and_ads_do_not_hide_daily_details():
    prior = date(2026, 11, 13)
    sample_only = mart_row(prior, sample=1, units=0, orders=0, sales="0", sem="1.50")
    paid = mart_row(START)
    sp, by_day = fake_sp([(prior, "2.00"), (START, "5.00")])

    full = calculate_testing_profit([sample_only, paid], sp_data=sp)
    result = build_operating_daily_same_source(
        [sample_only, paid], sp, by_day, cutoff=START, first_wfs=START
    )

    assert full["status"] == "scored"
    assert result["status"] == "scored"
    assert result["complete_calendar_days"] is True
    assert {row["date"] for row in result["rows"]} == {prior.isoformat(), START.isoformat()}
    assert result["totals"]["profit_usd"] == full["profit_usd"]
    assert result["totals"]["ad_spend_usd"] == full["ad_spend_usd"]


def test_source_dates_before_wfs_cannot_be_silently_discarded():
    before = mart_row(date(2026, 11, 13))
    result = build_operating_daily_same_source([before], None, [], cutoff=START, first_wfs=START)
    assert result["reason"] == "historical_period_conflicts_with_first_wfs"


def test_same_cutoff_saved_score_disagreement_blocks_proof():
    row = mart_row(START)
    sp, by_day = fake_sp([(START, "5")])
    score = calculate_testing_profit([row], sp_data=sp)
    saved = {
        "profit_source": "new_products_testing_profit_full_history_v2",
        "profit_calc_status": "scored",
        "data_cutoff_la": START.isoformat(),
        "profit_usd": "999",
        "roi": score["roi"],
        "gross_margin_pct": score["gross_margin_pct"],
        "sales_amount_usd": score["sales_amount_usd"],
        "ad_total_spend_usd": score["ad_spend_usd"],
    }
    result = build_operating_daily_same_source(
        [row], sp, by_day, cutoff=START, first_wfs=START, saved_facts=saved
    )
    assert result["reason"] == "saved_score_proof_disagrees_with_daily"


def test_same_cutoff_saved_score_equal_reconciles():
    row = mart_row(START)
    sp, by_day = fake_sp([(START, "5")])
    score = calculate_testing_profit([row], sp_data=sp)
    saved = {
        "profit_source": "new_products_testing_profit_full_history_v2",
        "profit_calc_status": "scored",
        "data_cutoff_la": START.isoformat(),
        **{
            key: score[key] for key in ("profit_usd", "roi", "gross_margin_pct", "sales_amount_usd")
        },
        "ad_total_spend_usd": score["ad_spend_usd"],
        "ad_spend_usd": "0",
    }
    result = build_operating_daily_same_source(
        [row], sp, by_day, cutoff=START, first_wfs=START, saved_facts=saved
    )
    assert result["status"] == "scored"
    assert result["score_comparison"] == "saved_score_reconciled"


def test_same_source_default_output_unchanged():
    row = mart_row(START)
    sp, _ = fake_sp([(START, "5")])
    default = calculate_testing_profit([row], sp_data=sp)
    with_components = calculate_testing_profit([row], sp_data=sp, include_components=True)
    assert "_components" not in default
    assert {k: v for k, v in with_components.items() if k != "_components"} == default


def test_two_msku_rows_same_day_group_and_reconcile():
    first = mart_row(START, units=1, orders=1, sales="24.99")
    second = mart_row(START, units=1, orders=1, sales="24.99")
    sp, by_day = fake_sp([(START, "5")])
    result = build_operating_daily_same_source(
        [first, second], sp, by_day, cutoff=START, first_wfs=START
    )
    assert result["status"] == "scored"
    assert len(result["rows"]) == 1
    assert Decimal(result["rows"][0]["sales_units"]) == Decimal("2")
    assert Decimal(result["rows"][0]["sales_orders"]) == Decimal("2")


def test_ad_only_day_still_has_negative_profit_without_fake_sales():
    first = mart_row(START)
    after = date(2026, 11, 15)
    sp, by_day = fake_sp([(START, "5"), (after, "3.20")])
    result = build_operating_daily_same_source([first], sp, by_day, cutoff=after, first_wfs=START)
    assert result["status"] == "scored"
    extra = result["rows"][0]
    assert extra["date"] == after.isoformat()
    assert extra["sales_units"] is None
    assert extra["sales_amount_usd"] is None
    assert Decimal(extra["ad_spend_usd"]) == Decimal("3.20")
    assert Decimal(extra["profit_usd"]) == Decimal("-3.20")
    assert extra["roi"] is None
    assert result["complete_calendar_days"] is False


def test_different_cutoff_not_claimed_to_equal_saved_score():
    row = mart_row(START)
    sp, by_day = fake_sp([(START, "5")])
    facts = {
        "profit_source": "new_products_testing_profit_full_history_v2",
        "profit_calc_status": "scored",
        "data_cutoff_la": "2026-11-13",
        "profit_usd": "999",
    }
    result = build_operating_daily_same_source(
        [row], sp, by_day, cutoff=START, first_wfs=START, saved_facts=facts
    )
    assert result["status"] == "scored"
    assert result["score_comparison"] == "not_comparable"


def test_refund_amount_does_not_change_testing_profit():
    row = mart_row(START)
    sp, _ = fake_sp([(START, "5")])
    before = calculate_testing_profit([row], sp_data=sp)
    row["refund_amount"] = "3999.00"
    after = calculate_testing_profit([row], sp_data=sp)
    assert before == after


def test_unverified_sp_currency_disallows_daily_financials():
    row = mart_row(START)
    result = build_operating_daily_same_source(
        [row],
        {"source_rows": 1, "incomplete_spend_rows": 1, "sp_spend": "5"},
        [{"day": START, "source_rows": 1, "incomplete_spend_rows": 1, "sp_spend": "5"}],
        cutoff=START,
        first_wfs=START,
    )
    assert result["status"] == "unverified"
    assert result["rows"] == []
    assert result["totals"] is None


def test_pre_first_wfs_sp_ads_counted_same_as_score():
    before_wfs = date(2026, 11, 13)
    row = mart_row(START)
    total_sp, daily_sp = fake_sp([(before_wfs, "3.20"), (START, "5")])
    result = build_operating_daily_same_source(
        [row], total_sp, daily_sp, cutoff=START, first_wfs=START
    )
    score = calculate_testing_profit([row], sp_data=total_sp)

    assert result["status"] == "scored"
    by_date = {r["date"]: r for r in result["rows"]}
    prelaunch = by_date[before_wfs.isoformat()]
    assert prelaunch["sales_units"] is None
    assert Decimal(prelaunch["ad_spend_usd"]) == Decimal("3.20")
    assert Decimal(prelaunch["profit_usd"]) == Decimal("-3.20")
    assert result["totals"]["profit_usd"] == score["profit_usd"]
    assert result["totals"]["ad_spend_usd"] == score["ad_spend_usd"]
