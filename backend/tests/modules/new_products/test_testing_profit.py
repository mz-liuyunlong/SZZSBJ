"""Testing-profit policy cases. No database, HTTP, or Git access."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

from app.modules.new_products import rules
from app.modules.new_products.testing_profit import (
    FinalDecision,
    calculate_testing_profit,
)
from app.modules.new_products.testing_profit_projection import (
    closed_list_row,
)
from app.modules.new_products.testing_profit_projection import (
    testing_profit_dimension as calculate_profit_dimension,
)


def day(**changes):
    base = {
        "day": date(2026, 10, 23),
        "sales_qty": 20,
        "order_count": 20,
        "sales_amount": "400",
        "sales_currency_code": "USD",
        "sample_qty": 5,
        "cost_quantity": 25,
        "ad_spend_amount": "12",
        "sem_ad_spend_amount": "8",
        "ad_spend_currency_code": "USD",
        "commission_rate": "0.15",
        "purchase_cost_total_usd": "100",
        "first_leg_cost_total_usd": "50",
        "storage_fee_total_amount": "25",
        "wfs_fee_total_amount": "150",
        "wfs_fee_actual_total_amount": "125",
        "wfs_fee_expected_total_amount": "125",
        "wfs_low_price_surcharge_amount": "0",
        "calculation_warnings_json": [],
        "refund_amount": "250",
        "return_qty": "10",
        "gross_profit_amount": "-999",
    }
    base.update(changes)
    return base


def ad(spend="30", count=1):
    return {"source_rows": count, "incomplete_spend_rows": 0, "sp_spend": spend}


def test_refunds_never_reduce_sales_or_recalculate_at_refund_commission():
    with_refunds = calculate_testing_profit([day()], sp_data=ad())
    no_refunds = calculate_testing_profit([day(refund_amount="0", return_qty="0")], sp_data=ad())
    assert with_refunds == no_refunds
    assert with_refunds["status"] == "scored"
    assert with_refunds["sales_units"] == "20"
    assert with_refunds["sales_orders"] == "20"
    assert with_refunds["sales_amount_usd"] == "400"
    # 400-(80 purchase+40 firstleg+20 storage+100 WFS+60 commission+38 ads)
    assert Decimal(with_refunds["profit_usd"]) == Decimal("62")


def test_sample_only_day_keeps_advertising_but_no_sale_or_materials():
    sample_only = day(
        day=date(2026, 10, 19),
        sales_qty=0,
        order_count=0,
        sales_amount="0",
        sample_qty=5,
        cost_quantity=5,
        purchase_cost_total_usd="20",
        first_leg_cost_total_usd="10",
        wfs_fee_expected_total_amount="30",
        storage_fee_total_amount="5",
        sem_ad_spend_amount="7",
    )
    normal = day()
    value = calculate_testing_profit([sample_only, normal], sp_data=ad("30"))
    assert value["status"] == "scored"
    assert value["first_order_date"] == "2026-10-23"
    assert value["sales_units"] == "20"
    assert Decimal(value["ad_spend_usd"]) == Decimal("45")
    assert Decimal(value["profit_usd"]) == Decimal("55")


def test_actual_wfs_preferred_for_normal_orders_only():
    value = calculate_testing_profit(
        [
            day(
                sample_qty=0,
                cost_quantity=20,
                wfs_fee_actual_total_amount="88",
                wfs_fee_expected_total_amount="70",
                wfs_low_price_surcharge_amount="2",
            )
        ],
        sp_data=ad("0", count=0),
    )
    assert value["status"] == "scored"
    # 400-(100+50+25+90+60+8 SEM+12 fallback SP)
    assert Decimal(value["profit_usd"]) == Decimal("55")


def test_mixed_actual_wfs_requires_expected_basis():
    value = calculate_testing_profit([day(wfs_fee_expected_total_amount=None)], sp_data=ad())
    assert value["status"] == "partial"
    assert value["profit_usd"] is None
    assert "sample_wfs_split_unavailable" in value["missing"]


def test_disputed_samples_fail_closed():
    value = calculate_testing_profit(
        [day(calculation_warnings_json=["sample_exceeds_salestat_pending_review"])],
        sp_data=ad(),
    )
    assert "sample_evidence_disputed" in value["missing"]
    assert value["roi"] is None


def test_ad_cost_exists_before_first_normal_order():
    value = calculate_testing_profit(
        [
            day(
                day=date(2026, 10, 19),
                sales_qty=0,
                order_count=0,
                sales_amount=0,
                sample_qty=3,
                cost_quantity=3,
                sem_ad_spend_amount="11",
            ),
            day(day=date(2026, 10, 25), sample_qty=0, cost_quantity=20),
        ],
        sp_data=ad("45"),
    )
    assert value["first_order_date"] == "2026-10-25"
    assert Decimal(value["ad_spend_usd"]) == Decimal("64")


def test_no_normal_sale_no_fabricated_profit_or_first_order():
    value = calculate_testing_profit(
        [day(sales_qty=0, order_count=0, sales_amount=0, sample_qty=5, cost_quantity=5)],
        sp_data=ad("5"),
    )
    assert value["status"] == "partial"
    assert value["profit_usd"] is None
    assert value["first_order_date"] is None
    assert value["ad_spend_usd"] == "13"


def test_score_uses_existing_60_40_weights():
    config = {"confirmedScoring": {"profit": rules.DEFAULT_PARAMETERS["profit"]}}
    value = calculate_testing_profit([day()], sp_data=ad())
    answer = calculate_profit_dimension(value, config)
    assert answer is not None
    assert Decimal("0") <= Decimal(answer) <= Decimal("10")


def test_closed_result_uses_saved_snapshot_without_live_recalculation():
    original = {
        "facts": {"profit_usd": "19", "gross_margin_pct": "7", "elapsed_days": 9},
        "evaluation": {"dimensions": {"profit": "6.4"}, "total": "8.1", "grade": "A"},
    }
    snapshot = deepcopy(original)
    final = FinalDecision("\u6253\u54c1\u6210\u529f", {"score": snapshot})
    row = closed_list_row(
        {"first_wfs_available_date_la": "2026-10-01"}, None, final, date(2026, 11, 13)
    )
    assert row["facts"]["profit_usd"] == "19"
    assert row["facts"]["elapsed_days"] == 9
    assert row["evaluation"]["dimensions"]["profit"] == "6.4"
    assert row["evaluation"]["total"] == "8.1"
    assert row["tracking_decision"] == "\u6253\u54c1\u6210\u529f"
    assert original == snapshot


def test_current_final_result_blocks_even_without_snapshot():
    from app.modules.new_products.testing_profit import load_final_decisions

    class Data:
        def mappings(self):
            return [
                {
                    "account": "acct",
                    "store": "store",
                    "item": "item",
                    "final_result": "\u6253\u54c1\u5931\u8d25",
                    "final_result_snapshot_json": None,
                    "final_result_at": None,
                    "legacy_decision": None,
                    "legacy_decided_at": None,
                    "legacy_facts": None,
                }
            ]

    class Session:
        def execute(self, statement, params):
            assert "wanted" in params
            return Data()

    result = load_final_decisions(Session(), [("acct", "store", "item")])
    assert result[("acct", "store", "item")].result == "\u6253\u54c1\u5931\u8d25"
    assert result[("acct", "store", "item")].snapshot is None
