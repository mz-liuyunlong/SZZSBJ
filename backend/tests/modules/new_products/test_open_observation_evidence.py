"""PR337 regression: hydrate raw display evidence, never revise score snapshots."""

from copy import deepcopy

from app.modules.new_products.open_observation_evidence import (
    FIELDS,
    project_open_observation_evidence,
)


def test_active_product_hydrates_real_ad_and_trust_facts_without_changing_score():
    row = {
        "facts": {
            "ad_clicks": "4",
            "ad_orders": None,
            "ad_revenue_usd": None,
            "profit_usd": "4.50",
            "roi": "0.84",
            "gross_margin_pct": "23.85",
        },
        "evaluation": {
            "observation_state": "automatic_partial",
            "dimensions": {
                "speed": "4.30",
                "ad": "9.035653",
                "profit": "5.74",
                "trust": "4.30",
            },
        },
    }
    old_eval = deepcopy(row["evaluation"])
    evidence = {
        "ad_status": "active",
        "ad_spend_usd": "6.19",
        "ad_clicks": "13",
        "ad_orders": "1",
        "ad_revenue_usd": "20.99",
        "valid_units_14d": "1",
        "valid_orders_14d": "1",
        "single_unit_orders_14d": "1",
        "ad_latest_sync": None,
    }
    project_open_observation_evidence(row, evidence)
    assert row["evaluation"] == old_eval
    assert row["facts"]["ad_clicks"] == "13"
    assert row["facts"]["ad_orders"] == "1"
    assert row["facts"]["ad_revenue_usd"] == "20.99"
    assert row["facts"]["single_unit_orders_14d"] == "1"
    assert row["facts"]["profit_usd"] == "4.50"
    assert row["facts"]["roi"] == "0.84"
    assert row["facts"]["gross_margin_pct"] == "23.85"
    assert set(FIELDS).isdisjoint({"roi", "profit_usd", "gross_margin_pct"})


def test_missing_raw_facts_are_not_invented_from_saved_ad_score():
    row = {
        "facts": {"ad_orders": "2", "ad_revenue_usd": "50"},
        "evaluation": {"observation_state": "automatic_partial", "dimensions": {"ad": "9.04"}},
    }
    project_open_observation_evidence(row, {"ad_status": "unknown"})
    assert row["facts"]["ad_status"] == "unknown"
    assert row["facts"]["ad_orders"] is None
    assert row["facts"]["ad_revenue_usd"] is None
    assert row["evaluation"]["dimensions"]["ad"] == "9.04"


def test_frozen_product_never_hydrates_new_data():
    row = {
        "facts": {"ad_clicks": "4"},
        "evaluation": {"observation_state": "frozen", "dimensions": {"ad": "9.04"}},
    }
    before = deepcopy(row)
    project_open_observation_evidence(row, {"ad_clicks": "13"})
    assert row == before
