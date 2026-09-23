"""Business-rule tests for app.modules.pmc_purchase.calculations (rules v4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.pmc_purchase.calculations import (
    ArrivalResult,
    CycleSample,
    ManualBaseline,
    PlanShare,
    PurchaseThresholds,
    ReceiptEvent,
    allocate_by_plan_quantity,
    classify_order_stage,
    classify_plan_stage,
    compute_arrival,
    compute_sku_cycle,
    cycle_threshold_days,
    days_between,
    normalize_store_id,
    parse_itemid_remark,
    parse_provider_date,
    resolve_item_id,
    wfs_not_ready,
)

T = PurchaseThresholds()
TODAY = date(2026, 9, 21)


def _d(text: str) -> date:
    return date.fromisoformat(text)


# --- §1.1 / §3.2 / §7 provider values --------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-03 10:52:36", _d("2026-08-03")),
        ("2026-08-03", _d("2026-08-03")),
        ("  2026-08-03 23:59:59 ", _d("2026-08-03")),
        ("0000-00-00 00:00:00", None),
        ("", None),
        (None, None),
        ("not a date", None),
        (20260803, None),
    ],
)
def test_parse_provider_date_keeps_only_the_beijing_date(value: object, expected: object) -> None:
    assert parse_provider_date(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("110652398125259264", "110652398125259264"),
        (110652398125259264, "110652398125259264"),
        (" 12 ", "12"),
        ("0", None),
        (0, None),
        ("", None),
        (None, None),
        (True, None),
    ],
)
def test_normalize_store_id_is_string_and_zero_means_unattributed(
    value: object, expected: str | None
) -> None:
    assert normalize_store_id(value) == expected


def test_days_between_same_day_is_zero_and_missing_is_none() -> None:
    assert days_between(_d("2026-08-01"), _d("2026-08-01")) == 0
    assert days_between(_d("2026-08-01"), _d("2026-08-09")) == 8
    assert days_between(None, _d("2026-08-09")) is None
    assert days_between(_d("2026-08-09"), None) is None


# --- §5.1 ItemID attribution ---------------------------------------------------------


@pytest.mark.parametrize(
    ("remark", "expected"),
    [
        ("ITEMID:19051502014", "19051502014"),
        ("补货 ITEMID: 19051502014 急", "19051502014"),
        ("itemid:19051502014", "19051502014"),
        ("ITEMID:1905150201", None),  # ten digits
        ("ITEMID:190515020145", None),  # twelve digits
        ("ITEM ID 19051502014", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_itemid_remark_requires_exactly_eleven_digits(
    remark: object, expected: object
) -> None:
    assert parse_itemid_remark(remark) == expected


def test_resolve_item_id_priority_system_plan_over_remark_over_packing_slip() -> None:
    # Rules v4 §5.1 (Owner 2026-09-21): no manual source on the purchase board.
    assert (
        resolve_item_id(
            system_plan_item_id="22222222222",
            plan_remark_item_id="33333333333",
            packing_slip_item_id="44444444444",
        ).source
        == "from_system_plan"
    )
    assert (
        resolve_item_id(
            plan_remark_item_id="33333333333", packing_slip_item_id="44444444444"
        ).source
        == "from_plan_remark"
    )
    slip = resolve_item_id(packing_slip_item_id=" 44444444444 ")
    assert (slip.source, slip.item_id) == ("from_packing_slip", "44444444444")
    pending = resolve_item_id(plan_remark_item_id="", packing_slip_pending=True)
    assert (pending.source, pending.item_id) == ("pending_packing_slip", None)
    unresolved = resolve_item_id(plan_remark_item_id="  ")
    assert (unresolved.source, unresolved.item_id) == ("unresolved", None)


def test_resolve_item_id_has_no_manual_parameter() -> None:
    import inspect

    assert "manual_item_id" not in inspect.signature(resolve_item_id).parameters


# --- §5.6 WFS readiness ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "fulfillment_type", "expected"),
    [
        ("from_plan_remark", "1", False),
        ("from_packing_slip", "0", True),
        ("from_system_plan", "2", True),
        ("from_packing_slip", 2, True),
        ("from_plan_remark", None, None),
        ("from_plan_remark", "9", None),
        ("unresolved", "0", None),  # not checked when unattributed
        ("pending_packing_slip", "0", None),  # not checked while waiting for a slip
    ],
)
def test_wfs_not_ready_flags_only_attributed_non_wfs_listings(
    source: str, fulfillment_type: object, expected: bool | None
) -> None:
    assert wfs_not_ready(source, fulfillment_type) is expected  # type: ignore[arg-type]


# --- §5.2 merged purchase orders -------------------------------------------------------


def test_single_plan_takes_everything() -> None:
    [only] = allocate_by_plan_quantity(
        quantity=120, amount=Decimal("600.00"), plans=[PlanShare("P1", 100)]
    )
    assert (only.ratio, only.quantity, only.amount) == (Decimal("1.0000"), 120, Decimal("600.0000"))


def test_merged_order_splits_by_plan_quantity_with_exact_totals() -> None:
    parts = allocate_by_plan_quantity(
        quantity=100,
        amount=Decimal("333.33"),
        plans=[PlanShare("P1", 1), PlanShare("P2", 1), PlanShare("P3", 1)],
    )
    assert [p.quantity for p in parts] == [34, 33, 33]
    assert sum(p.quantity for p in parts) == 100
    assert sum(p.amount or 0 for p in parts) == Decimal("333.33")
    assert all(p.ratio == Decimal("0.3333") for p in parts)


def test_merged_order_ratio_follows_changed_total_quantity() -> None:
    # 采购员改过总量也按比例 (§5.2): plans 60/40, real quantity 80.
    parts = allocate_by_plan_quantity(
        quantity=80, amount=None, plans=[PlanShare("P1", 60), PlanShare("P2", 40)]
    )
    assert [(p.plan_sn, p.quantity, p.amount) for p in parts] == [
        ("P1", 48, None),
        ("P2", 32, None),
    ]


def test_merged_order_without_plan_quantities_splits_equally() -> None:
    parts = allocate_by_plan_quantity(
        quantity=5, amount=Decimal("10"), plans=[PlanShare("P1", None), PlanShare("P2", 0)]
    )
    assert [p.quantity for p in parts] == [3, 2]
    assert [p.amount for p in parts] == [Decimal("5.0000"), Decimal("5.0000")]


@pytest.mark.parametrize(
    "plans",
    [[], [PlanShare("P1", 1), PlanShare("P1", 2)], [PlanShare("", 1)]],
)
def test_allocation_rejects_empty_or_duplicate_plans(plans: list[PlanShare]) -> None:
    with pytest.raises(ValueError):
        allocate_by_plan_quantity(quantity=1, amount=None, plans=plans)


# --- §3 arrival and progress -----------------------------------------------------------


def test_arrival_is_first_receipt_reaching_half_of_order_quantity() -> None:
    result = compute_arrival(
        quantity_total=100,
        receipts=[
            ReceiptEvent(_d("2026-08-20"), 30, "R2"),
            ReceiptEvent(_d("2026-08-10"), 10, "R1"),
            ReceiptEvent(_d("2026-08-25"), 20, "R3"),
        ],
        thresholds=T,
    )
    # cumulative by date: 10 (08-10), 40 (08-20), 60 (08-25) → 50 reached on 08-25
    assert result.arrival_date == _d("2026-08-25")
    assert result.arrival_receipt_order_sn == "R3"
    assert result.quantity_received == 60
    assert result.progress_ratio == Decimal("0.6000")
    assert result.remaining_quantity == 40


def test_arrival_exactly_at_threshold_counts() -> None:
    result = compute_arrival(
        quantity_total=10, receipts=[ReceiptEvent(_d("2026-08-10"), 5)], thresholds=T
    )
    assert result.arrival_date == _d("2026-08-10")


def test_over_receipt_is_allowed_and_remaining_never_negative() -> None:
    result = compute_arrival(
        quantity_total=10, receipts=[ReceiptEvent(_d("2026-08-10"), 13)], thresholds=T
    )
    assert result.progress_ratio == Decimal("1.3000")
    assert result.remaining_quantity == 0


def test_no_receipts_or_zero_quantity() -> None:
    empty = compute_arrival(quantity_total=10, receipts=[], thresholds=T)
    assert empty.arrival_date is None and empty.progress_ratio == Decimal("0")
    zero = compute_arrival(
        quantity_total=0, receipts=[ReceiptEvent(_d("2026-08-10"), 1)], thresholds=T
    )
    assert zero.arrival_date is None and zero.progress_ratio is None


# --- §2 stages ---------------------------------------------------------------------------


def _arrival(received: int, total: int = 100, arrived: date | None = None) -> ArrivalResult:
    return ArrivalResult(
        quantity_total=total,
        quantity_received=received,
        progress_ratio=Decimal(received) / Decimal(total),
        arrival_date=arrived,
        arrival_receipt_order_sn=None,
        remaining_quantity=max(total - received, 0),
    )


def test_plan_stage_s1_pending_approval_two_days() -> None:
    r = classify_plan_stage(
        plan_status=121,
        plan_create_date=_d("2026-09-15"),
        first_seen_pending_date=None,
        has_purchase_order=False,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert r.stage_code == "S1"
    assert r.threshold_days == 2
    assert r.due_date == _d("2026-09-17")
    assert r.overdue_days == 4
    assert r.alert_due_since == _d("2026-09-18")


def test_plan_stage_s2_uses_first_seen_date_and_marks_estimate_when_missing() -> None:
    exact = classify_plan_stage(
        plan_status=2,
        plan_create_date=_d("2026-09-01"),
        first_seen_pending_date=_d("2026-09-16"),
        has_purchase_order=False,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert (exact.stage_code, exact.stage_start, exact.overdue_days, exact.start_estimated) == (
        "S2",
        _d("2026-09-16"),
        0,
        False,
    )
    estimated = classify_plan_stage(
        plan_status=2,
        plan_create_date=_d("2026-09-01"),
        first_seen_pending_date=None,
        has_purchase_order=False,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert estimated.start_estimated is True and estimated.overdue_days == 13


@pytest.mark.parametrize("status", [-3, 124, 122])
def test_plan_stage_void_or_rejected_is_s0(status: int) -> None:
    r = classify_plan_stage(
        plan_status=status,
        plan_create_date=_d("2026-09-01"),
        first_seen_pending_date=None,
        has_purchase_order=False,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert r.stage_code == "S0" and r.overdue_days == 0


def test_plan_converted_to_order_is_not_classified_as_plan_stage() -> None:
    r = classify_plan_stage(
        plan_status=2,
        plan_create_date=_d("2026-09-01"),
        first_seen_pending_date=None,
        has_purchase_order=True,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert r.stage_code == "S9"


def test_unattributed_store_never_overdue() -> None:
    r = classify_plan_stage(
        plan_status=121,
        plan_create_date=_d("2026-08-01"),
        first_seen_pending_date=None,
        has_purchase_order=False,
        store_attributed=False,
        today=TODAY,
        thresholds=T,
    )
    assert r.stage_code == "S1" and r.overdue_days == 0 and r.due_date is None


def test_order_stage_s2_pending_order_from_create_date() -> None:
    r = classify_order_stage(
        order_status=1,
        order_create_date=_d("2026-09-10"),
        order_date=None,
        arrival=_arrival(0),
        sku_cycle_days=None,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert (r.stage_code, r.threshold_days, r.overdue_days) == ("S2", 7, 4)


def test_order_stage_s3_uses_sku_cycle_or_default_seven() -> None:
    with_cycle = classify_order_stage(
        order_status=2,
        order_create_date=_d("2026-09-01"),
        order_date=_d("2026-09-05"),
        arrival=_arrival(0),
        sku_cycle_days=12,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert (with_cycle.stage_code, with_cycle.threshold_days, with_cycle.overdue_days) == (
        "S3",
        12,
        4,
    )
    default = classify_order_stage(
        order_status=2,
        order_create_date=_d("2026-09-01"),
        order_date=_d("2026-09-05"),
        arrival=_arrival(0),
        sku_cycle_days=None,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert (default.threshold_days, default.overdue_days) == (7, 9)


def test_order_stage_s4_partial_and_s9_when_arrived() -> None:
    partial = classify_order_stage(
        order_status=2,
        order_create_date=_d("2026-09-01"),
        order_date=_d("2026-09-05"),
        arrival=_arrival(20),
        sku_cycle_days=None,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert partial.stage_code == "S4"
    arrived = classify_order_stage(
        order_status=2,
        order_create_date=_d("2026-09-01"),
        order_date=_d("2026-09-05"),
        arrival=_arrival(60, arrived=_d("2026-09-15")),
        sku_cycle_days=None,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert arrived.stage_code == "S9" and arrived.overdue_days == 0


@pytest.mark.parametrize(("status", "code"), [(9, "S9"), (-1, "S0"), (77, "UNKNOWN")])
def test_order_stage_terminal_and_unknown(status: int, code: str) -> None:
    r = classify_order_stage(
        order_status=status,
        order_create_date=_d("2026-09-01"),
        order_date=_d("2026-09-05"),
        arrival=_arrival(0),
        sku_cycle_days=None,
        store_attributed=True,
        today=TODAY,
        thresholds=T,
    )
    assert r.stage_code == code and r.overdue_days == 0


# --- §4.2 / §4.4 SKU actual purchase cycle ----------------------------------------------


def _sample(sn: str, ordered: str, arrived: str, excluded: bool = False) -> CycleSample:
    return CycleSample(sn, _d(ordered), _d(arrived), manually_excluded=excluded)


def test_sku_cycle_averages_newest_five_valid_samples() -> None:
    samples = [
        _sample("O1", "2026-06-01", "2026-06-11"),  # 10, oldest → outside window
        _sample("O2", "2026-06-10", "2026-06-18"),  # 8
        _sample("O3", "2026-06-20", "2026-06-29"),  # 9
        _sample("O4", "2026-07-01", "2026-07-08"),  # 7
        _sample("O5", "2026-07-10", "2026-07-20"),  # 10
        _sample("O6", "2026-07-20", "2026-07-26"),  # 6
    ]
    r = compute_sku_cycle(samples=samples, baseline=None, lingxing_default_days=15, thresholds=T)
    assert r.source == "samples" and r.sample_count == 5
    assert r.value_days == Decimal("8.0000")  # (8+9+7+10+6)/5
    assert [c.purchase_order_sn for c in r.considered if not c.used] == ["O1"]
    assert r.considered[-1].exclusion == "outside_window"


def test_sku_cycle_auto_excludes_under_two_days_but_keeps_them_visible() -> None:
    samples = [
        _sample("O1", "2026-08-01", "2026-08-02"),  # 1 day → auto exclude
        _sample("O2", "2026-08-05", "2026-08-05"),  # 0 day → auto exclude
        _sample("O3", "2026-08-10", "2026-08-17"),  # 7
        _sample("O4", "2026-08-20", "2026-08-29"),  # 9
    ]
    r = compute_sku_cycle(samples=samples, baseline=None, lingxing_default_days=None, thresholds=T)
    assert r.value_days == Decimal("8.0000") and r.sample_count == 2
    excluded = {c.purchase_order_sn: c.exclusion for c in r.considered if not c.used}
    assert excluded == {"O1": "auto_short", "O2": "auto_short"}


def test_sku_cycle_manual_exclusion_and_fallback_to_lingxing_default() -> None:
    samples = [
        _sample("O1", "2026-08-10", "2026-08-17"),
        _sample("O2", "2026-08-20", "2026-08-29", excluded=True),
    ]
    r = compute_sku_cycle(samples=samples, baseline=None, lingxing_default_days=12, thresholds=T)
    assert r.source == "lingxing_default" and r.value_days == Decimal("12")
    assert [c.exclusion for c in r.considered] == ["manual", None]
    none = compute_sku_cycle(
        samples=samples, baseline=None, lingxing_default_days=None, thresholds=T
    )
    assert none.source == "no_baseline" and none.value_days is None


def test_manual_baseline_takes_one_slot_and_ignores_orders_before_it() -> None:
    # 例：基准 7，新单 5、9 → (7+5+9)/3 = 7
    baseline = ManualBaseline(value_days=7, set_on=_d("2026-08-15"))
    samples = [
        _sample("OLD", "2026-08-01", "2026-08-30"),  # before baseline → ignored
        _sample("N1", "2026-08-20", "2026-08-25"),  # 5
        _sample("N2", "2026-09-01", "2026-09-10"),  # 9
    ]
    r = compute_sku_cycle(
        samples=samples, baseline=baseline, lingxing_default_days=None, thresholds=T
    )
    assert r.source == "baseline_mix" and r.value_days == Decimal("7.0000")
    assert r.baseline_days == 7 and r.sample_count == 2
    assert (
        next(c for c in r.considered if c.purchase_order_sn == "OLD").exclusion == "before_baseline"
    )


def test_manual_baseline_alone_is_used_immediately() -> None:
    r = compute_sku_cycle(
        samples=[],
        baseline=ManualBaseline(9, _d("2026-09-01")),
        lingxing_default_days=3,
        thresholds=T,
    )
    assert r.source == "baseline_mix" and r.value_days == Decimal("9.0000")


def test_manual_baseline_holds_with_four_new_samples_and_is_evicted_by_the_fifth() -> None:
    # Rocky 2026-09-21: baseline + 4 new samples fill the window of 5; the 5th evicts it.
    baseline = ManualBaseline(value_days=7, set_on=_d("2026-08-01"))
    four = [
        _sample(f"N{i}", f"2026-08-{10 + i:02d}", f"2026-08-{18 + i:02d}") for i in range(4)
    ]  # four new valid samples, 8 days each
    held = compute_sku_cycle(
        samples=four, baseline=baseline, lingxing_default_days=None, thresholds=T
    )
    assert held.source == "baseline_mix" and held.baseline_days == 7
    assert held.sample_count == 4 and held.value_days == Decimal("7.8000")  # (7+8*4)/5

    five = [*four, _sample("N5", "2026-08-20", "2026-08-28")]
    evicted = compute_sku_cycle(
        samples=five, baseline=baseline, lingxing_default_days=None, thresholds=T
    )
    assert evicted.source == "samples" and evicted.baseline_days is None
    assert evicted.value_days == Decimal("8.0000") and evicted.sample_count == 5


def test_unstable_requires_five_samples_and_range_of_three_days() -> None:
    stable = [_sample(f"S{i}", f"2026-08-{1 + i:02d}", f"2026-08-{9 + i:02d}") for i in range(5)]
    assert (
        compute_sku_cycle(
            samples=stable, baseline=None, lingxing_default_days=None, thresholds=T
        ).unstable
        is False
    )
    spread = stable[:4] + [_sample("S9", "2026-08-20", "2026-08-31")]  # 11 vs 8 → range 3
    r = compute_sku_cycle(samples=spread, baseline=None, lingxing_default_days=None, thresholds=T)
    assert r.unstable is True and r.range_days == 3
    four_only = compute_sku_cycle(
        samples=spread[1:], baseline=None, lingxing_default_days=None, thresholds=T
    )
    assert four_only.unstable is False


def test_cycle_threshold_rounds_half_up() -> None:
    r = compute_sku_cycle(
        samples=[
            _sample("A", "2026-08-01", "2026-08-08"),  # 7
            _sample("B", "2026-08-10", "2026-08-18"),  # 8
        ],
        baseline=None,
        lingxing_default_days=None,
        thresholds=T,
    )
    assert r.value_days == Decimal("7.5000")
    assert cycle_threshold_days(r) == 8


# --- thresholds ------------------------------------------------------------------------


def test_thresholds_defaults_match_rules_v3_and_reject_invalid() -> None:
    assert (T.s1_approval_days, T.s2_pending_days, T.default_cycle_days) == (2, 7, 7)
    assert (T.arrival_ratio, T.auto_exclude_below_days, T.sample_window) == (Decimal("0.5"), 2, 5)
    assert (T.unstable_min_samples, T.unstable_range_days) == (5, 3)
    with pytest.raises(ValueError):
        PurchaseThresholds(arrival_ratio=Decimal("0"))
    with pytest.raises(ValueError):
        PurchaseThresholds(sample_window=0)
