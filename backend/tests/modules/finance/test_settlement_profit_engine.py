"""PRP §8 calculation on synthetic fixtures (pure, no database)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest

from app.modules.finance.settlement_profit.engine import (
    calculate_store_month,
    unmapped_store_rows,
)
from app.modules.finance.settlement_profit.inputs import (
    Adjustment,
    ReviewAcceleratorInput,
    ReviewAction,
    ReviewSnapshotItem,
    SettlementKind,
)
from app.modules.finance.settlement_profit.keys import (
    UNMAPPED_STORE_ID,
    content_hash,
    order_line_key,
)
from app.modules.finance.settlement_profit.money import allocate, bill_month_of
from app.modules.finance.settlement_profit.persistence import movement_fields, result_hash
from app.modules.finance.settlement_profit.rules import (
    OwnerItem,
    allocate_net_profit,
    review_accelerator_weights,
    review_unit_price,
)

from .settlement_fixtures import MONTH, REPORT, STORE, base_input, line, movement

T0 = datetime(2030, 2, 1, tzinfo=UTC)


def key(order: str, gtin: str = "G1") -> str:
    return order_line_key(STORE, REPORT, order, "1", gtin)


# ------------------------------------------------------------------ money


def test_allocate_largest_remainder_sums_exactly() -> None:
    parts = allocate(D("10.00"), {"a": D(1), "b": D(1), "c": D(1)})
    assert parts == {"a": D("3.34"), "b": D("3.33"), "c": D("3.33")}
    assert sum(allocate(D("-0.05"), {"a": D(3), "b": D(1)}).values()) == D("-0.05")
    assert sum(allocate(D("1.2345"), {"a": D(1), "b": D(2)}).values()) == D("1.2345")
    with pytest.raises(ValueError):
        allocate(D("1"), {"a": D(0)})


def test_bill_month_cutoff_is_fifth_of_next_month() -> None:
    assert bill_month_of(date(2030, 2, 5)) == date(2030, 1, 1)
    assert bill_month_of(date(2030, 2, 6)) == date(2030, 2, 1)
    assert bill_month_of(date(2030, 1, 3)) == date(2029, 12, 1)


# ------------------------------------------------------------------ reconcile


def test_store_month_reconciles_and_excludes_ad_and_wpc_lines() -> None:
    r = calculate_store_month(base_input())
    assert r.reconcile.settlement_total_usd == D("80.5000")
    assert r.reconcile.diff_usd == 0
    assert r.reconcile.status == "ok"
    assert r.blockers == []
    # ad daily 50 vs settlement ad charge -50 → 0 difference, not a failure
    assert r.reconcile.ad_daily_vs_settlement_diff_usd == 0
    # Lingxing head ¥28 / 7 = $4 vs WPC -5 → -1 difference, not a failure
    assert r.reconcile.inbound_freight_lx_vs_settlement_diff_usd == D("-1.0000")
    # ad subsidy goes to 其他业务收入, never into settlement profit
    assert r.other_income_usd == D("8.0000")
    assert all(not it.amounts.get("platform_subsidy_usd") for it in r.items.values())


def test_reconcile_failure_blocks_close() -> None:
    inp = base_input()
    order_line = line(SettlementKind.SALE, "5.00", "SYN-O9", gtin="G1", quantity=1)
    inp.settlement_lines.append(order_line)
    inp.fifo[("SYN-O9", "G1")] = inp.fifo[("SYN-O1", "G1")]
    r = calculate_store_month(inp)
    assert r.reconcile.status == "ok"  # every settlement dollar is accounted for
    # an amount override makes the order level differ from the settlement
    adj = Adjustment(
        "a1", key("SYN-O9"), "amount", {"column": "sales_amount_usd", "delta_usd": "4"}, T0
    )
    inp.adjustments.append(adj)
    r = calculate_store_month(inp)
    assert r.reconcile.status == "reconcile_failed"
    assert r.reconcile.diff_usd == D("-4.0000")
    assert "RECONCILE_FAILED" in r.blockers


# ------------------------------------------------------------------ allocation


def test_item_fees_go_to_items_then_orders_by_quantity() -> None:
    r = calculate_store_month(base_input())
    i1 = r.items["I1"]
    # WFS service 3.00 split 2:1 by fee detail GTIN weights
    assert i1.amounts.get("wfs_service_fee_usd") == D("-2.00")
    assert r.items["I2"].amounts.get("wfs_service_fee_usd") == D("-1.00")
    o1 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O1")
    o2 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O2")
    assert o1.amounts.get("wfs_service_fee_usd") + o2.amounts.get("wfs_service_fee_usd") == D(
        "-2.00"
    )
    assert o2.amounts.get("wfs_service_fee_usd") == D("-1.33")  # quantity 2 of 3
    # storage 2.00 split 3:1 by report share
    assert i1.amounts.get("storage_fee_usd") == D("-1.50")


def test_disposal_fee_counted_once_in_disposal_column() -> None:
    r = calculate_store_month(base_input())
    i1 = r.items["I1"]
    assert i1.disposal_loss_usd == D("1.00")
    # the disposal fee detail line does not also weight the WFS service fee
    total_service = sum(it.amounts.get("wfs_service_fee_usd") for it in r.items.values())
    assert total_service == D("-3.00")


def test_fee_detail_without_gtin_goes_to_unassigned() -> None:
    inp = base_input()
    inp.fee_details[1] = replace(inp.fee_details[1], gtin=None)
    r = calculate_store_month(inp)
    pending = [u for u in r.unassigned if u.source_kind == "item_fee_no_item"]
    assert [u.amount_usd for u in pending] == [D("-1.00")]
    assert r.reconcile.status == "unassigned_pending"
    assert r.reconcile.diff_usd == 0  # pending 待指定 counts in the order level total
    assert "UNASSIGNED_PENDING" in r.blockers


def test_missing_storage_report_goes_to_unassigned_and_latest_is_flagged() -> None:
    r = calculate_store_month(base_input(storage_report=None))
    assert [u.source_kind for u in r.unassigned] == ["storage_no_report"]
    inp = base_input()
    inp.storage_report = replace(inp.storage_report, is_latest_fallback=True)
    r = calculate_store_month(inp)
    assert ("STORAGE_REPORT_LATEST_PERIOD", "2030-01-01") in r.alerts


def test_assign_item_moves_unassigned_into_the_item() -> None:
    inp = base_input(storage_report=None)
    pending = calculate_store_month(inp).unassigned[0]
    inp.adjustments.append(Adjustment("a2", pending.line_key, "assign_item", {"item_id": "I2"}, T0))
    r = calculate_store_month(inp)
    assert r.unassigned[0].status == "assigned"
    assert r.items["I2"].amounts.get("storage_fee_usd") == D("-2.00")
    assert r.reconcile.status == "ok"


# ------------------------------------------------------------------ goods cost / FX


def test_goods_cost_and_missing_head() -> None:
    inp = base_input()
    inp.fifo[("SYN-O3", "G2")] = replace(inp.fifo[("SYN-O3", "G2")], head_cny=D("0"))
    r = calculate_store_month(inp)
    o3 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O3")
    assert o3.reasons == ["missing_head"]
    assert o3.review_status == "pending"
    o1 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O1")
    assert o1.goods_cost_usd == D("6.0000")  # (35 + 7) / 7
    assert o1.reasons == [] and o1.review_status == "auto"


def test_no_fifo_marks_both_reasons_and_cost_adjustment_fixes_it() -> None:
    inp = base_input()
    del inp.fifo[("SYN-O3", "G2")]
    r = calculate_store_month(inp)
    o3 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O3")
    assert o3.reasons == ["missing_purchase", "missing_head"]
    assert o3.cost_match_status == "unmatched"
    inp.adjustments.append(
        Adjustment("a3", key("SYN-O3", "G2"), "cost", {"purchase_cny": "14", "head_cny": "7"}, T0)
    )
    r = calculate_store_month(inp)
    o3 = next(o for o in r.order_lines if o.platform_order_no == "SYN-O3")
    assert o3.reasons == [] and o3.review_status == "adjusted"
    assert o3.goods_cost_usd == D("3.0000")


def test_fx_missing_has_no_fallback() -> None:
    r = calculate_store_month(base_input(fx_rate=None))
    assert r.fx_status == "missing"
    assert "FX_MISSING" in r.blockers
    o1 = r.order_lines[0]
    assert o1.goods_cost_usd is None and o1.gross_profit_usd is None
    assert o1.gross_profit_cny is None
    assert "fx_missing" in o1.reasons
    assert all(it.gross_profit_cny is None for it in r.items.values())


def test_review_after_change_goes_back_to_first_review() -> None:
    inp = base_input()
    k = key("SYN-O1")
    inp.review_actions.append(ReviewAction(k, "final", "pass", T0))
    r = calculate_store_month(inp)
    assert next(o for o in r.order_lines if o.line_key == k).review_status == "final_passed"
    later = datetime(2030, 2, 2, tzinfo=UTC)
    inp.adjustments.append(Adjustment("a4", k, "note", {"text": "x"}, later))
    r = calculate_store_month(inp)
    assert next(o for o in r.order_lines if o.line_key == k).review_status == "adjusted"


def test_revoked_adjustment_does_not_revive_an_older_review() -> None:
    """§8.9: 撤销已终审订单调整回到待初审 — the old final pass no longer counts."""
    inp = base_input()
    k = key("SYN-O1")
    inp.review_actions.append(ReviewAction(k, "final", "pass", T0))
    revoked_at = datetime(2030, 2, 3, tzinfo=UTC)
    inp.adjustment_changed_at[k] = revoked_at  # adjustment made, then revoked
    r = calculate_store_month(inp)
    line = next(o for o in r.order_lines if o.line_key == k)
    assert line.reasons == [] and line.review_status == "pending"
    # a review after the revoke counts again
    inp.review_actions.append(ReviewAction(k, "first", "pass", datetime(2030, 2, 4, tzinfo=UTC)))
    r = calculate_store_month(inp)
    assert next(o for o in r.order_lines if o.line_key == k).review_status == "first_passed"


# ------------------------------------------------------------------ inventory


def test_inventory_categories_and_alerts() -> None:
    inp = base_input(
        movements=[
            movement("LIQ"),
            movement("VDG", row_hash="h2"),
            movement("ZZZ_NEW", row_hash="h3"),
            movement("RFS", row_hash="h4"),
            movement("NEGATIVE_INVENTORY", row_hash="h5"),
        ]
    )
    r = calculate_store_month(inp)
    cats = {m.movement.row_hash: m.category for m in r.movements}
    assert cats == {
        "flow-hash-1": "loss",
        "h2": "unclassified",
        "h3": "unknown",
        "h4": "non_loss",
        "h5": "lx_adjust",
    }
    codes = {c for c, _ in r.alerts}
    assert {"INVENTORY_UNCLASSIFIED", "INVENTORY_UNKNOWN", "INVENTORY_LX_ADJUST"} <= codes
    # only the loss row hits profit: ¥70 / 7 = $10 goods value + $1 disposal fee
    assert r.items["I1"].disposal_loss_usd == D("11.0000")


def test_unmapped_store_loss_goes_to_unmapped_todo_and_blocks_every_store() -> None:
    moves = [
        movement("LIQ", store_id=None, row_hash="u1"),
        movement("RFS", store_id=None, row_hash="u2"),  # non-loss: no to-do
    ]
    rows = unmapped_store_rows(MONTH, moves, D("7"), [])
    assert [(r.store_id, r.source_kind, r.reason, r.status) for r in rows] == [
        (UNMAPPED_STORE_ID, "inventory_unmapped_store", "unmapped_store", "pending")
    ]
    assert rows[0].amount_cny == D("70") and rows[0].amount_usd == D("10.0000")
    assert rows[0].detail["store_code"] == "SC-1"
    # without FX the ¥ amount is kept and USD stays empty
    assert unmapped_store_rows(MONTH, moves, None, [])[0].amount_usd is None
    # any pending unmapped row blocks closing for all stores of that month (Rocky 2026-11-03)
    r = calculate_store_month(base_input(), month_has_unmapped_pending=True)
    assert r.reconcile.status == "unassigned_pending"
    assert "UNASSIGNED_PENDING" in r.blockers


def test_assign_store_moves_movement_into_that_store() -> None:
    moves = [movement("LIQ", store_id=None, row_hash="u1")]
    pending = unmapped_store_rows(MONTH, moves, D("7"), [])[0]
    adj = Adjustment("a5", pending.line_key, "assign_store", {"store_id": STORE}, T0)
    assigned = unmapped_store_rows(MONTH, moves, D("7"), [adj])[0]
    assert assigned.status == "assigned" and assigned.assigned_store_id == STORE
    r = calculate_store_month(base_input(movements=moves))
    m = r.movements[0]
    assert m.store_id == STORE and m.store_mapping_status == "manual_assigned"
    assert r.items["I1"].disposal_loss_usd == D("11.0000")


def test_loss_without_item_in_store_becomes_store_unassigned() -> None:
    r = calculate_store_month(base_input(movements=[movement("LIQ", gtin="G-UNKNOWN")]))
    assert [u.source_kind for u in r.unassigned] == ["inventory_unmapped_item"]
    assert r.unassigned[0].amount_cny == D("70")


# ------------------------------------------------------------------ review accelerator


def ra(current: dict[str, int] | None, previous: dict[str, int] | None, prices=None):
    return ReviewAcceleratorInput(
        current=None
        if current is None
        else tuple(ReviewSnapshotItem(i, n) for i, n in current.items()),
        previous=None
        if previous is None
        else tuple(ReviewSnapshotItem(i, n) for i, n in previous.items()),
        price_by_item=prices or {},
    )


def test_review_accelerator_unit_price_is_clamped() -> None:
    assert review_unit_price(D("10")) == D("10")  # 7.5 → 10
    assert review_unit_price(D("40")) == D("15.00")
    assert review_unit_price(D("200")) == D("30")


def test_review_accelerator_weights_by_delta_times_price() -> None:
    w = review_accelerator_weights(
        ra({"I1": 5, "I2": 3}, {"I1": 2, "I2": 4}, {"I1": D("40"), "I2": None}), {}
    )
    # I2's delta is negative → 0, so its missing price does not matter
    assert w.weights == {"I1": D("45.00"), "I2": D("0")}
    assert w.unassigned_reason is None


def test_review_accelerator_kept_sales_rules_and_no_other_fallback() -> None:
    sales = {"I1": D("90"), "I2": D("10")}
    first = review_accelerator_weights(ra({"I1": 1, "I2": 1}, None), sales)
    assert first.mode == "sales_first_period" and first.weights == {"I1": D("90"), "I2": D("10")}
    zero = review_accelerator_weights(ra({"I1": 1}, {"I1": 1}), sales)
    assert zero.mode == "sales_zero_delta" and zero.weights == {"I1": D("90")}
    missing = review_accelerator_weights(ra({"I1": 3}, {"I1": 1}, {"I1": None}), sales)
    assert missing.weights is None and missing.unassigned_reason == "price_missing"
    assert review_accelerator_weights(ra(None, None), sales).unassigned_reason == (
        "snapshot_missing"
    )


def test_review_accelerator_fee_spread_or_unassigned() -> None:
    inp = base_input()
    inp.settlement_lines.append(line(SettlementKind.REVIEW_ACCELERATOR, "-20.00"))
    inp.review_accelerator = ra(
        {"I1": 4, "I2": 2}, {"I1": 2, "I2": 0}, {"I1": D("20"), "I2": D("20")}
    )
    r = calculate_store_month(inp)
    assert r.items["I1"].amounts.get("review_accelerator_usd") == D("-10.00")
    assert r.reconcile.status == "ok"
    inp.review_accelerator = None
    r = calculate_store_month(inp)
    assert [(u.source_kind, u.reason) for u in r.unassigned] == [
        ("review_accelerator", "snapshot_missing")
    ]


# ------------------------------------------------------------------ 纯利


def test_net_profit_formula_example() -> None:
    items = [
        OwnerItem(("s", "a1"), "A", D("50"), D("1")),
        OwnerItem(("s", "b1"), "B", D("30"), D("1")),
        OwnerItem(("s", "c1"), "C", D("20"), D("1")),
        OwnerItem(("s", "x1"), "EXCLUDED", D("999"), D("1")),
    ]
    company_cost = D("85292") + D("15000") * 3
    net = allocate_net_profit(items, company_cost, D("15000"), ["EXCLUDED"])
    assert net.owners_in_n == ["A", "B", "C"]
    assert net.share_by_owner == {
        "A": D("57646.00"),
        "B": D("40587.60"),
        "C": D("32058.40"),
    }
    assert net.share_by_item is not None and net.share_by_item[("s", "x1")] == 0
    assert sum(net.share_by_owner.values()) == company_cost


def test_net_profit_blockers() -> None:
    missing = allocate_net_profit([OwnerItem(("s", "i"), None, D("1"), D("1"))], D("1"), D("0"), [])
    assert missing.blockers == ["OWNER_MISSING"] and missing.share_by_item is None
    zero = allocate_net_profit(
        [OwnerItem(("s", "i"), "A", D("5"), D("1")), OwnerItem(("s", "j"), "A", D("-5"), D("1"))],
        D("1"),
        D("0"),
        [],
    )
    assert zero.blockers == ["OWNER_SALES_ZERO"]
    pending = allocate_net_profit([OwnerItem(("s", "i"), "A", D("5"), D("1"))], None, D("0"), [])
    assert pending.share_by_item is None and pending.blockers == []  # 等资金流水上线


# ------------------------------------------------------------------ hash / idempotency


def test_same_input_same_result_hash() -> None:
    assert (
        result_hash(calculate_store_month(base_input()))[0]
        == result_hash(calculate_store_month(base_input()))[0]
    )


def test_content_hash_ignores_flow_id_and_run_ids_but_not_row_hash() -> None:
    base = {"a": D("1"), "source_flow_id": "x", "source_run_ids": ["r1"], "calc_version": 1}
    assert content_hash(base) == content_hash(
        {**base, "source_flow_id": "y", "source_run_ids": ["r2"], "calc_version": 7}
    )
    r1 = calculate_store_month(base_input(movements=[movement("LIQ")]))
    r2 = calculate_store_month(
        base_input(movements=[movement("LIQ", flow_id="00000000-0000-0000-0000-000000000009")])
    )
    assert result_hash(r1)[0] == result_hash(r2)[0]  # re-synced flow row, new id
    r3 = calculate_store_month(base_input(movements=[movement("LIQ", row_hash="changed")]))
    assert result_hash(r1)[0] != result_hash(r3)[0]
    assert "source_flow_id" not in movement_fields(r1.movements[0], r1)
