"""Rule layer tests; expectations follow 8088 DEMO app.jsx (calcItem / computeAll)."""

from __future__ import annotations

from dataclasses import replace

from app.modules.pmc_overview.calculations import (
    DomesticBatchAge,
    ItemInput,
    RecentPlan,
    SupplyBatch,
    compute_all,
)
from app.modules.pmc_overview.rules import OverviewParams

TODAY = "2026-11-02"
P = OverviewParams()


def item(**kw) -> ItemInput:  # type: ignore[no-untyped-def]
    base = ItemInput(
        item_id="100",
        sku="SKU-A",
        daily=10.0,
        n30=30,
        oos_days=0,
        no_stock_90=False,
        tail_stock=False,
        max_start=500,
        supply=1000,
        wm_available=500,
        sellout="2027-01-31",
        gap_days=None,
        resume=None,
        next_date=None,
        lead_total=80.0,
        lead_avg=15.0,
        suggest=0,
        suggest_raw=0,
        cap_on=False,
        capped=False,
    )
    return replace(base, **kw)


def run(*items: ItemInput, mode: str = "demo_8088"):  # type: ignore[no-untyped-def]
    return compute_all(list(items), P, TODAY, mode)  # type: ignore[arg-type]


def test_normal_item_has_no_issue() -> None:
    (r,), kpi = run(item())
    assert r.main == "正常" and r.issues == [] and r.cover == 100 and r.over == "正常"
    assert kpi["normal"] == 1


def test_over_thresholds_120_150() -> None:
    (a, b, c), _ = run(
        item(item_id="1", supply=1200),
        item(item_id="2", supply=1210),
        item(item_id="3", supply=1510),
    )
    assert (a.over, b.over, c.over) == ("正常", "库存过剩", "严重过剩")
    assert c.main == "严重过剩"


def test_low_supply_suppresses_stock_issues_but_not_oos() -> None:
    (r,), _ = run(item(supply=9, wm_available=0, daily=1.0, sellout=TODAY))
    assert not r.stock_ok and r.over is None
    assert r.main == "已断货"


def test_few_instock_days_skip_over_and_stale() -> None:
    (r,), _ = run(item(n30=13, supply=5000))
    assert r.over is None and r.cover is None
    assert r.main == "有库存天数 13 天"


def test_stale_needs_14_instock_days_and_zero_sales() -> None:
    (r,), _ = run(item(daily=0.0, n30=20, sellout=None))
    assert r.stale and "滞销" in r.cats


def test_oos_when_wfs_below_instock_min() -> None:
    (r,), _ = run(item(wm_available=4, oos_days=3, next_date="2026-11-20"))
    assert r.oos and r.main == "已断货"
    assert "已断货 3 天" in r.issues[0].detail


def test_risk_gap_window_and_no_incoming_within_lead_time() -> None:
    (a, b), _ = run(
        item(item_id="1", sellout="2026-11-20", gap_days=5, resume="2026-11-25"),
        item(item_id="2", sellout="2026-12-01", gap_days=None, resume=None, lead_total=80),
    )
    assert a.risk and a.main == "断货风险"
    assert b.risk


def test_purchase_s1_s2_s3_flags() -> None:
    batches = (
        SupplyBatch(kind="plan", qty=100, created="2026-10-30", status="待审批", ref="PP1"),
        SupplyBatch(kind="plan", qty=100, created="2026-10-20", status="待采购", ref="PP2"),
        SupplyBatch(kind="po_pending", qty=50, order="2026-10-20", ref="PO1"),
        SupplyBatch(kind="po", qty=50, order="2026-10-01", ref="PO2"),
    )
    (r,), _ = run(item(batches=batches))
    assert [f.label for f in r.exec_flags] == ["采购计划待审批超时", "待采购超时", "待下单超时"]
    assert [f.label for f in r.sc_flags] == ["采购已下单未到货超期"]
    assert r.main == "采购已下单未到货超期"


def test_overdue_shipped_and_no_track_except_overseas() -> None:
    batches = (
        SupplyBatch(kind="shipped", qty=30, overdue=True, no_track=True),
        SupplyBatch(kind="shipped", qty=20, overdue=True, no_track=True, overseas_ship=True),
    )
    (r,), _ = run(item(batches=batches))
    labels = {f.label: f.detail for f in r.sc_flags}
    assert labels["已过预计可售日未上架"] == "50 件"
    assert labels["超期无物流轨迹"].startswith("30 件")
    assert "超期未上架" in r.cats


def test_domestic_over_7_days_needs_10_units() -> None:
    (a, b), _ = run(
        item(
            item_id="1", dom_rows=(DomesticBatchAge(age=8, qty=9), DomesticBatchAge(age=3, qty=100))
        ),
        item(
            item_id="2", dom_rows=(DomesticBatchAge(age=8, qty=6), DomesticBatchAge(age=12, qty=6))
        ),
    )
    assert not a.exec_flags and a.dom_max == 8
    assert b.exec_flags[0].label == "国内仓在仓超期" and b.dom_over_qty == 12


def test_overseas_goes_to_earliest_sellout_first() -> None:
    (a, b), kpi = run(
        item(item_id="1", sellout="2026-12-20", suggest=80, overseas_sku=100),
        item(item_id="2", sellout="2026-12-01", suggest=60, overseas_sku=100),
    )
    assert (b.overseas_alloc, a.overseas_alloc) == (60, 40)
    assert a.purchase == 40 and kpi["overseas"] == 2


def test_box_rounding_and_cap() -> None:
    (a, b), _ = run(
        item(item_id="1", suggest=130, box=50),
        item(item_id="2", suggest=300, box=40, cap_on=True),
    )
    assert a.boxed == 150  # remainder 30 >= 25 rounds up
    assert b.boxed == 280  # 320 > cap 300 → floor boxes


def test_draft_blocked_by_recent_plan_and_tags() -> None:
    (a, b), _ = run(
        item(
            item_id="1",
            suggest=100,
            plans_recent=(RecentPlan(plan="PP9", created="2026-10-25", qty=200),),
        ),
        item(item_id="2", suggest=100, tags=("历史产品",)),
    )
    assert not a.is_draft and a.draft_text.startswith("14 天内已有采购计划 PP9")
    assert not b.is_draft and b.main == "标签 历史产品"


def test_draft_mode_replenishment_uses_issued_draft_only() -> None:
    it = item(suggest=100)
    (demo,), _ = run(it)
    (repl,), _ = run(it, mode="replenishment")
    (issued,), _ = run(replace(it, draft_id="CG261102-001"), mode="replenishment")
    assert demo.is_draft and not repl.is_draft and issued.is_draft
    assert repl.draft_text.startswith("本轮未出草稿")


def test_listing_problem_ranks_first() -> None:
    (r,), kpi = run(item(listing="SYSTEM PROBLEM", wm_available=0))
    assert r.main == "Listing 异常" and kpi["listing_bad"] == 1
