"""ODS → DWD builder tests (Gate 3 G3-B part 1): de-dup, normalisation, merged split."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.modules.pmc_purchase.dwd_builder import (
    DWD_BUILDER_VERSION,
    build_dwd,
    build_orders,
    build_plans,
    build_receipt_lines,
    latest_versions,
    receipt_events_by_order,
)

RUN_1 = UUID("00000000-0000-0000-0000-00000000c001")
RUN_2 = UUID("00000000-0000-0000-0000-00000000c002")
T1 = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)


@dataclass
class _Row:
    run_id: UUID
    observed_at: datetime
    payload_json: dict[str, object] = field(default_factory=dict)
    source_account_ref: str = "primary"
    id: UUID = field(default_factory=uuid4)
    raw_request_ref_id: UUID = field(default_factory=uuid4)


@dataclass
class Plan(_Row):
    plan_sn: str = "P1"
    status: int | None = 2
    create_time: str | None = "2026-08-03 10:52:36"
    expect_arrive_time: str | None = None
    sid: str | None = "110652398125259264"
    sku: str | None = "SKU-A"
    product_name: str | None = "Widget"
    quantity_plan: int | None = 100
    remark: str | None = None
    plan_remark: str | None = None
    is_aux: int | None = 0
    is_combo: int | None = 0


@dataclass
class Order(_Row):
    order_sn: str = "PO1"
    status: int | None = 2
    order_time: str | None = "2026-08-05 12:00:00"
    create_time: str | None = "2026-08-04 09:00:00"
    quantity_total: int | None = 100
    quantity_receive: int | None = 0
    quantity_real: int | None = 100
    amount_total: Decimal | None = Decimal("500.0000")
    purchase_currency: str | None = "CNY"
    purchase_rate: Decimal | None = Decimal("1")
    shipping_price: Decimal | None = None
    other_fee: Decimal | None = None


@dataclass
class Item(_Row):
    order_sn: str = "PO1"
    item_id: str = "L1"
    line_ordinal: int = 0
    plan_sn: str | None = "P1"
    sid: str | None = "110652398125259264"
    sku: str | None = "SKU-A"
    product_name: str | None = "Widget"
    quantity_plan: int | None = 100
    quantity_real: int | None = 100
    quantity_receive: int | None = 0
    price: Decimal | None = Decimal("5.0000")
    amount: Decimal | None = Decimal("500.0000")
    expect_arrive_time: str | None = None
    is_delete: int | None = 0
    remark: str | None = None


@dataclass
class Receipt(_Row):
    order_sn: str = "R1"
    business_order_sn: str | None = "PO1"
    status: int | None = 1
    receive_time: str | None = "2026-08-20 18:29:09"
    update_time: str | None = "2026-08-20 18:29:09"


@dataclass
class ReceiptItem(_Row):
    receipt_order_sn: str = "R1"
    line_ordinal: int = 0
    order_item_id: str | None = "L1"
    sku: str | None = "SKU-A"
    product_receive_num: int | None = 60


# --- de-duplication ------------------------------------------------------------------


def test_latest_version_prefers_newer_provider_update_time_then_observed_at() -> None:
    old = Plan(RUN_1, T2, payload_json={"update_time": "2026-08-05 14:33:13"}, status=2)
    new = Plan(RUN_2, T1, payload_json={"update_time": "2026-08-26 10:20:30"}, status=-2)
    chosen, superseded = latest_versions([old, new], lambda r: r.plan_sn)
    assert chosen[("primary", "P1")] is new and superseded == 1

    a = Plan(RUN_1, T1, status=2)  # no update_time in payload
    b = Plan(RUN_2, T2, status=-2)
    chosen, _ = latest_versions([a, b], lambda r: r.plan_sn)
    assert chosen[("primary", "P1")] is b  # later observation wins on a tie


def test_versions_are_scoped_per_source_account() -> None:
    a = Plan(RUN_1, T1, source_account_ref="primary")
    b = Plan(RUN_1, T1, source_account_ref="secondary")
    chosen, superseded = latest_versions([a, b], lambda r: r.plan_sn)
    assert len(chosen) == 2 and superseded == 0


# --- plans -------------------------------------------------------------------------------


def test_plans_normalised_and_aux_combo_excluded() -> None:
    plans = [
        Plan(RUN_1, T1, plan_sn="P1", remark="补货 ITEMID: 19051502014"),
        Plan(RUN_1, T1, plan_sn="P2", sid="0", plan_remark="ITEMID:19051502099"),
        Plan(RUN_1, T1, plan_sn="P3", is_aux=1),
        Plan(RUN_1, T1, plan_sn="P4", is_combo=1),
    ]
    rows, counts = build_plans(plans)
    assert counts == {"seen": 4, "kept": 2, "excluded": 2, "superseded": 0}
    p1, p2 = rows
    assert p1.create_date.isoformat() == "2026-08-03"  # type: ignore[union-attr]
    assert p1.store_id == "110652398125259264" and p1.store_attributed
    assert p1.remark_item_id == "19051502014"
    assert p2.store_id is None and not p2.store_attributed
    assert p2.remark_item_id == "19051502099"  # falls back to plan_remark


# --- orders and lines ----------------------------------------------------------------------


def test_single_plan_line_keeps_quantity_and_amount_and_inherits_plan_itemid() -> None:
    plans_by_sn = {
        p.plan_sn: p for p in build_plans([Plan(RUN_1, T1, remark="ITEMID:19051502014")])[0]
    }
    orders, lines, counts = build_orders([Order(RUN_1, T1)], [Item(RUN_1, T1)], plans_by_sn)
    [order], [line] = orders, lines
    assert order.order_date.isoformat() == "2026-08-05"  # type: ignore[union-attr]
    assert order.line_count == 1
    assert (line.plan_sn, line.plan_count, line.is_merged) == ("P1", 1, False)
    assert (line.quantity_allocated, line.amount_allocated) == (100, Decimal("500.0000"))
    assert line.allocation_ratio == Decimal("1.0000")
    assert line.remark_item_id == "19051502014" and line.plan_found
    assert counts["lines_split_from_merged"] == 0


def test_merged_line_is_split_across_plans_by_plan_quantity() -> None:
    plans, _ = build_plans(
        [
            Plan(RUN_1, T1, plan_sn="P1", quantity_plan=60, remark="ITEMID:11111111111"),
            Plan(RUN_1, T1, plan_sn="P2", quantity_plan=40, remark="ITEMID:22222222222"),
        ]
    )
    item = Item(
        RUN_1,
        T1,
        plan_sn="P1",
        quantity_real=80,
        amount=Decimal("400.0000"),
        payload_json={"relation_purchase_plan": [{"plan_sn": "P2"}, {"plan_sn": "P1"}]},
    )
    _, lines, counts = build_orders([Order(RUN_1, T1)], [item], {p.plan_sn: p for p in plans})
    assert [(ln.plan_sn, ln.quantity_allocated, ln.amount_allocated) for ln in lines] == [
        ("P1", 48, Decimal("240.0000")),
        ("P2", 32, Decimal("160.0000")),
    ]
    assert all(ln.is_merged and ln.plan_count == 2 for ln in lines)
    assert [ln.remark_item_id for ln in lines] == ["11111111111", "22222222222"]
    assert counts["lines_split_from_merged"] == 2 and counts["lines_kept"] == 2


def test_line_referencing_unknown_plan_is_kept_and_counted() -> None:
    item = Item(RUN_1, T1, plan_sn="P-MISSING", remark="ITEMID:33333333333")
    _, [line], counts = build_orders([Order(RUN_1, T1)], [item], {})
    assert line.plan_sn == "P-MISSING" and line.plan_found is False
    assert line.remark_item_id == "33333333333"  # line remark as a fallback
    assert counts["lines_plan_missing"] == 1


def test_line_without_any_plan_and_deleted_line_and_sid_zero() -> None:
    items = [
        Item(RUN_1, T1, item_id="L1", plan_sn=None, sid="0"),
        Item(RUN_1, T1, item_id="L2", line_ordinal=1, is_delete=1),
    ]
    _, lines, counts = build_orders([Order(RUN_1, T1)], items, {})
    [line] = lines
    assert line.plan_sn is None and line.plan_count == 0 and not line.store_attributed
    assert counts["lines_without_plan"] == 1
    assert counts["lines_deleted"] == 1
    assert counts["store_unattributed_lines"] == 1


def test_lines_follow_the_chosen_header_version() -> None:
    # Run 1 delivered PO1 with two lines; run 2 (newer) delivers it with one line.
    orders = [
        Order(RUN_1, T1, payload_json={"update_time": "2026-08-10 00:00:00"}),
        Order(RUN_2, T2, payload_json={"update_time": "2026-08-20 00:00:00"}, status=9),
    ]
    items = [
        Item(RUN_1, T1, item_id="L1"),
        Item(RUN_1, T1, item_id="L2", line_ordinal=1),
        Item(RUN_2, T2, item_id="L1", quantity_real=90),
    ]
    [order], lines, counts = build_orders(orders, items, {})
    assert order.status == 9 and order.source.run_id == RUN_2
    assert [(ln.order_item_id, ln.quantity_real) for ln in lines] == [("L1", 90)]
    assert counts["orders_superseded"] == 1 and counts["lines_superseded"] == 2


# --- receipts ------------------------------------------------------------------------------


def test_receipt_lines_deduped_and_linked_to_known_order_lines() -> None:
    receipts = [
        Receipt(RUN_1, T1, payload_json={"update_time": "2026-08-20 18:29:09"}),
        Receipt(RUN_2, T2, payload_json={"update_time": "2026-08-21 09:00:00"}),
    ]
    items = [
        ReceiptItem(RUN_1, T1, product_receive_num=50),
        ReceiptItem(RUN_2, T2, product_receive_num=60),
        ReceiptItem(RUN_2, T2, line_ordinal=1, order_item_id="L-UNKNOWN"),
        ReceiptItem(RUN_2, T2, line_ordinal=2, order_item_id=None),
    ]
    rows, counts = build_receipt_lines(receipts, items, {"L1"})
    [row] = rows
    assert row.quantity == 60 and row.source.run_id == RUN_2
    assert row.receive_date.isoformat() == "2026-08-20"  # type: ignore[union-attr]
    assert counts == {"seen": 2, "kept": 1, "superseded": 1, "lines_kept": 1, "lines_unlinked": 2}


def test_receipt_events_are_grouped_per_purchase_order() -> None:
    result = build_dwd(
        ods_plans=[Plan(RUN_1, T1)],
        ods_orders=[Order(RUN_1, T1)],
        ods_items=[Item(RUN_1, T1)],
        ods_receipts=[
            Receipt(RUN_1, T1, order_sn="R1", receive_time="2026-08-20 18:29:09"),
            Receipt(RUN_1, T1, order_sn="R2", receive_time="2026-08-25 08:00:00"),
        ],
        ods_receipt_items=[
            ReceiptItem(RUN_1, T1, receipt_order_sn="R1", product_receive_num=30),
            ReceiptItem(RUN_1, T1, receipt_order_sn="R2", product_receive_num=30),
        ],
    )
    events = receipt_events_by_order(result.receipt_lines, result.lines)
    assert [(e.receive_date.isoformat(), e.quantity) for e in events[("primary", "PO1")]] == [
        ("2026-08-20", 30),
        ("2026-08-25", 30),
    ]
    assert result.builder_version == DWD_BUILDER_VERSION
    assert "plans_kept=1" in result.report.as_message()
    assert result.report.receipt_lines_kept == 2
