from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.pmc_replenishment.calculations import (
    ItemInput,
    MarginWindow,
    RecentPlan,
    ReplenishmentParams,
    SupplyBatch,
    add_days,
    box_round,
    calculate_item,
    round_half_up,
)

TODAY = date(2026, 11, 2)
P = ReplenishmentParams()


def item(**kw) -> ItemInput:
    base: dict = {
        "item_id": "100",
        "today": TODAY,
        "daily_sales": [10.0] * 90,
        "start_stock": [100.0] * 90,
        "wfs_available": 0,
        "lead_avg_days": 10.0,
        "box_qty": None,
    }
    base.update(kw)
    return ItemInput(**base)


def labels(result) -> list[str]:
    return [f.label for f in result.flags]


def test_round_half_up_matches_8088_math_round() -> None:
    assert round_half_up(2.5) == 3
    assert round_half_up(3.5) == 4
    assert round_half_up(-0.5) == 0
    assert add_days(TODAY, 0.5) == TODAY + timedelta(days=1)
    assert add_days(None, 3) is None


def test_daily_sales_uses_latest_30_instock_days_and_skips_low_opening_stock() -> None:
    sales = [1.0] * 60 + [20.0] * 30
    start = [100.0] * 60 + [100.0] * 20 + [4.0] * 10  # last 10 days opening stock < 5
    r = calculate_item(item(daily_sales=sales, start_stock=start), P)
    # 30 in-stock days: 20 at 20/day and 10 at 1/day
    assert r.instock_days_used == 30
    assert r.sales_in_window == 20 * 20 + 10 * 1
    assert r.daily_sales == pytest.approx(410 / 30)
    assert r.days_since_instock == 10
    assert r.lookback_span_days == 40
    assert "已断货 10 天" in labels(r)


def test_lead_time_source_falls_back_to_lingxing_then_default() -> None:
    assert calculate_item(item(lead_avg_days=12.0), P).lead_source == "real"
    lx = calculate_item(item(lead_avg_days=None, cg_delivery_days=20), P)
    assert (lx.lead_source, lx.lead_days) == ("lx", 20)
    fb = calculate_item(item(lead_avg_days=None, cg_delivery_days=0), P)
    assert (fb.lead_source, fb.lead_days) == ("fallback", 15)
    assert "采购交期无样本" in labels(fb)
    # L = approve 5 + lead + pack 7 + transport 30 + shelf 10
    assert fb.lead_total_days == 5 + 15 + 7 + 30 + 10


def test_suggest_is_ceiling_of_target_minus_supply() -> None:
    r = calculate_item(item(wfs_available=100), P)
    # target = 10 * (L 62 + R 14 + safety 0) = 760
    assert r.target == pytest.approx(760)
    assert r.supply == 100
    assert r.suggest == 660
    assert r.is_draft


def test_sellable_dates_per_supply_kind() -> None:
    batches = [
        SupplyBatch("receiving", 5),
        SupplyBatch("shipped", 5, arrival_date=TODAY - timedelta(days=20)),
        SupplyBatch("shipped", 5, arrival_date=TODAY + timedelta(days=3)),
        SupplyBatch("domestic", 5),
        SupplyBatch("po", 5, order_date=TODAY - timedelta(days=4)),
        SupplyBatch("po_pending", 5),
        SupplyBatch("plan", 5, created_date=TODAY - timedelta(days=1)),
    ]
    r = calculate_item(item(batches=batches), P)
    dates = [ln.sellable_date for ln in r.supply_lines]
    tail = 7 + 30 + 10
    assert dates == [
        TODAY,  # wfs
        TODAY,  # receiving
        TODAY,  # shipped, sellable date passed -> today, overdue
        TODAY + timedelta(days=13),  # arrival + shelf 10
        TODAY + timedelta(days=tail),
        TODAY + timedelta(days=6 + tail),  # order + lead 10 = today + 6
        TODAY + timedelta(days=10 + tail),
        TODAY + timedelta(days=4 + 10 + tail),  # created + approve 5 = today + 4
    ]
    assert r.supply_lines[2].overdue
    assert "已过可售日未上架" in labels(r)
    assert r.next_arrival_date == TODAY + timedelta(days=13)


def test_cap_applies_when_few_instock_days_and_box_rounding_stays_under_cap() -> None:
    start = [0.0] * 80 + [100.0] * 10
    r = calculate_item(item(start_stock=start, daily_sales=[50.0] * 90, box_qty=40), P)
    assert r.cap_on and r.capped
    assert r.suggest == 300
    assert r.boxed == 280  # 7 cartons; rounding up to 8 would exceed the cap
    assert "单次封顶 300" in labels(r)


def test_box_round_half_carton_rule() -> None:
    assert box_round(95, 40, cap_on=False, cap_qty=300) == 80  # 15 left < half carton
    assert box_round(120, 40, cap_on=False, cap_qty=300) == 120
    assert box_round(140, 40, cap_on=False, cap_qty=300) == 160
    assert box_round(10, 40, cap_on=False, cap_qty=300) == 40
    assert box_round(290, 400, cap_on=True, cap_qty=300) is None
    assert box_round(0, 40, cap_on=False, cap_qty=300) is None


def test_recent_plan_within_cycle_blocks_draft() -> None:
    plans = [
        RecentPlan("PP1", TODAY - timedelta(days=14)),
        RecentPlan("PP2", TODAY - timedelta(days=15)),
    ]
    r = calculate_item(item(plans_recent=plans), P)
    assert r.blocking_plans == ("PP1",)
    assert not r.is_draft
    assert "14 天内已有采购计划" in labels(r)


@pytest.mark.parametrize(
    ("kw", "flag"),
    [
        ({"tags": ["历史产品"]}, "标签 历史产品"),
        ({"listing_status": "SYSTEM PROBLEM"}, "Listing SYSTEM PROBLEM"),
        ({"archived": True}, "已归档 · 不出草稿"),
    ],
)
def test_excluded_items_get_no_draft(kw: dict, flag: str) -> None:
    r = calculate_item(item(**kw), P)
    assert not r.is_draft
    assert flag in labels(r)


def test_below_min_qty_is_not_a_draft() -> None:
    r = calculate_item(item(daily_sales=[0.5] * 90, wfs_available=10), P)
    assert 0 < r.suggest < 50
    assert r.below_min and not r.is_draft


def test_low_margin_flag_goes_first_and_does_not_change_quantity() -> None:
    base = calculate_item(item(), P)
    r = calculate_item(item(margin_30d=MarginWindow(3.0), margin_7d=MarginWindow(None)), P)
    assert labels(r)[0] == "低利润 · 建议不补"
    assert r.suggest == base.suggest and r.is_draft
    ok7 = calculate_item(item(margin_30d=MarginWindow(3.0), margin_7d=MarginWindow(8.0)), P)
    assert "低利润 · 建议不补" not in labels(ok7)


def test_no_stock_and_tail_stock_flags() -> None:
    none = calculate_item(item(start_stock=[0.0] * 90, daily_sales=[0.0] * 90), P)
    assert none.no_stock_90 and none.daily_sales == 0 and not none.is_draft
    assert "近 90 天无库存" in labels(none)
    tail = calculate_item(item(start_stock=[3.0] * 90, daily_sales=[0.0] * 90), P)
    assert tail.tail_stock
    assert "尾货 <5 件" in labels(tail)


def test_stockout_timeline_and_resume() -> None:
    batches = [SupplyBatch("shipped", 100, arrival_date=TODAY + timedelta(days=5))]
    r = calculate_item(item(wfs_available=25, batches=batches), P)
    # 25 on hand at 10/day -> negative on day 2; arrival sellable on day 15
    assert r.sellout_date == TODAY + timedelta(days=2)
    assert r.resume_date == TODAY + timedelta(days=15)
    assert r.gap_days == 13
    never = calculate_item(item(daily_sales=[0.0] * 90), P)
    assert never.sellout_date is None and never.gap_days == 0


def test_cycle_override_per_item() -> None:
    r = calculate_item(item(cycle_override_days=30), P)
    assert r.cycle_days == 30
    assert r.target == pytest.approx(10 * (62 + 30))
