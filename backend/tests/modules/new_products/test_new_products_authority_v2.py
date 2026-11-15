"""New-products authority V2: no legacy DB writer or legacy score promotion."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.modules.new_products.pr337_daily_db import run_daily
from app.modules.new_products.pr337_daily_view import saved_daily_view
from app.modules.new_products.unified_publish import _save_one


def test_real_db_cannot_run_old_daily_writer():
    with pytest.raises(RuntimeError, match="LEGACY_PR337_DAILY_WRITER_RETIRED"):
        run_daily(Session(), apply=True)


def test_authority_v2_must_not_be_replaced_by_legacy_snapshot():
    fake = SimpleNamespace(
        data_coverage_json={
            "new_products_authority_v2": {"status": "ready"},
            "pr337_daily_verified_v1": {"version": "PR337_DAILY_PERSIST_V1"},
            "auto_dimension_scores": {"scoring_provenance": "PR337_DAILY_PERSIST_V1"},
        }
    )
    assert (
        saved_daily_view(
            {"evaluation": {"observation_state": "calculated"}}, (SimpleNamespace(), fake)
        )
        is False
    )


def test_independent_profit_exposes_verified_sample_quantity():
    from datetime import date

    from app.modules.new_products.testing_profit import calculate_testing_profit

    row = {
        "day": date(2026, 10, 23),
        "sales_qty": 20,
        "order_count": 20,
        "sales_amount": "400",
        "sales_currency_code": "USD",
        "sample_qty": 5,
        "cost_quantity": 25,
        "sem_ad_spend_amount": "8",
        "ad_spend_amount": "12",
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
    }
    value = calculate_testing_profit(
        [row], sp_data={"source_rows": 1, "incomplete_spend_rows": 0, "sp_spend": "30"}
    )
    assert value["status"] == "scored"
    assert value["sales_units"] == "20"
    assert value["sample_units"] == "5"
    assert value["sales_amount_usd"] == "400"


def test_authority_v2_corrects_existing_unapproved_score_and_profit():
    from datetime import date
    from decimal import Decimal
    from unittest.mock import MagicMock
    from uuid import uuid4

    target = MagicMock(spec=Session)
    registry = SimpleNamespace(id=uuid4())
    perf = SimpleNamespace(
        data_coverage_json={},
        process_status=None,
        score=Decimal("5.0"),
        grade="D",
        profit_usd=Decimal("-99"),
        roi=Decimal("-1"),
        profit_margin_pct=Decimal("-25"),
        first_order_date_la=None,
        ad_spend_usd=None,
        first_wfs_available_date_la=None,
        metric_window_start_la=None,
        metric_window_end_la=None,
    )
    market = SimpleNamespace(version=1)
    rule = SimpleNamespace(
        id=uuid4(),
        version=1,
        config_json={"weights": {"speed": 30, "ad": 20, "profit": 25, "trust": 10, "market": 15}},
    )
    # registry / frozen-decision / purchase / review / perf / market / rule
    target.scalar.side_effect = [registry, None, None, None, perf, market, rule]
    target.get.return_value = None
    profit = {
        "status": "scored",
        "policy": "returns_ignored_samples_excluded_sample_ads_included",
        "missing": [],
        "profit_usd": "62",
        "roi": "0.5167",
        "gross_margin_pct": "15.5",
        "sales_amount_usd": "400",
        "first_order_date": "2026-10-23",
        "ad_spend_usd": "38",
    }
    score = {
        "evaluation": {
            "dimensions": {
                "market": "7",
                "speed": "9.40",
                "ad": "10",
                "profit": "7.64",
                "trust": "9.91",
            },
            "total": "8.771",
            "grade": "A",
            "missing": [],
        },
        "facts": {"first_wfs_available_date_la": date(2026, 10, 20)},
        "profit": profit,
        "profit_ready": True,
        "rule_version": 1,
        "market_version": 1,
    }
    outcome = _save_one(
        target,
        ("source", "store", "20881463249"),
        {"status": "no_source_rows_unverified"},
        score,
        cutoff=date(2026, 11, 15),
    )
    assert outcome == "written"
    assert perf.sample_units is None
    assert perf.profit_usd == Decimal("62")
    assert perf.roi == Decimal("0.5167")
    assert perf.score == Decimal("8.771")
    assert perf.grade == "A"
    assert perf.data_coverage_json["new_products_authority_v2"]["status"] == "ready"
    assert perf.data_coverage_json["new_products_legacy_before_authority_v2"]["score"] == "5.0"
    assert perf.data_coverage_json["new_products_testing_profit_v2"]["policy"] == (
        "returns_ignored_samples_excluded_sample_ads_included"
    )
    assert perf.data_coverage_json["new_products_score_facts_v2"].get("sales_amount_usd") is None
    # The independent lifetime profit evidence preserves revenue explicitly;
    # existing 14-day SQL order columns must remain tied to their window.
    assert perf.data_coverage_json["new_products_testing_profit_v2"]["sales_amount_usd"] == "400"
