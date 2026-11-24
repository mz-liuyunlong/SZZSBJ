"""Pure regression: persisted grade, score revision and risk cap checks."""
from copy import deepcopy

import pytest

from app.modules.new_products.score_corrections import calculate_effective, overlay, resolved_system

CONFIG = {
    "weights": {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10},
    "gradeBands": {"S": [9, 10], "A": [8, 8.99], "B": [7, 7.99],
                   "C": [6, 6.99], "D": [0, 5.99]},
}
BASE = {
    "rule_version": 2, "total": "6.873456789", "grade": "C",
    "dimensions": {"market": "7", "speed": "6.40", "ad": "9.46",
                   "profit": "4.02", "trust": "10.00"},
    "ad_excluded": False,
}


def test_saved_four_decimal_grade_does_not_hide_correction():
    baseline = deepcopy(BASE)
    block = {"revision": 2, "system": baseline,
             "overrides": {"profit": "9.02"}, "history": [],
             "effective": calculate_effective(baseline, {"profit": "9.02"}, CONFIG)}
    row = {"evaluation": deepcopy(BASE) | {"total": "6.8735", "observation_state": "scored"},
           "facts": {}}
    assert overlay(row, block, CONFIG)
    assert row["score_correction"]["revision"] == 2
    assert row["evaluation"]["dimensions"]["profit"] == "9.02"
    assert row["evaluation"]["grade"] == "A"


def test_real_score_change_is_not_silently_accepted():
    row = deepcopy(BASE)
    row["total"] = "6.8734"
    assert resolved_system(row, BASE) is None


def test_malformed_historical_snapshot_does_not_crash_listing():
    base = deepcopy(BASE)
    base["dimensions"]["profit"] = "NaN"
    block = {"revision": 7, "system": base,
             "overrides": {"profit": "9.02"}, "history": [],
             "effective": {"total": "8.1", "grade": "A", "dimensions": {}}}
    row = {"evaluation": deepcopy(BASE) | {"observation_state": "scored"},
           "facts": {}}
    assert overlay(row, block, CONFIG) is False


def test_missing_history_or_revision_is_not_displayed_as_saved():
    for change in ({"history": None}, {"revision": None}):
        block = {"revision": 3, "system": deepcopy(BASE),
                 "overrides": {}, "history": []} | change
        row = {"evaluation": deepcopy(BASE) | {"observation_state": "scored"},
               "facts": {}}
        assert overlay(row, block, CONFIG) is False
        assert "score_correction" not in row


def test_rule_mismatch_still_blocks_overlay():
    row = deepcopy(BASE)
    row["rule_version"] = 3
    assert resolved_system(row, BASE) is None


def test_cap_from_verified_baseline_never_becomes_a_higher_grade():
    base = deepcopy(BASE)
    base["total"] = "8.673456789"
    base["grade"] = "C"
    changed = calculate_effective(base, {"profit": "10.00"}, CONFIG)
    assert changed["grade"] == "C"


def test_explicit_pass_veto_cannot_be_bypassed():
    base = deepcopy(BASE)
    base["grade"] = "Pass"
    changed = calculate_effective(base, {"profit": "10.00"}, CONFIG)
    assert changed["grade"] == "Pass"


def test_decorated_page_exposes_revision_and_effective_grade(monkeypatch):
    from datetime import date
    from decimal import Decimal

    from app.modules.new_products import evaluation_workflow as workflow
    from app.modules.new_products import risk_display
    from app.modules.new_products.service import NewProductService

    monkeypatch.setattr(NewProductService, "_config", lambda self: (CONFIG, 2))
    monkeypatch.setattr(
        risk_display, "build_saved_risk_display", lambda *a, **kw: {"rules": []}
    )
    correction = {
        "revision": 3,
        "system": deepcopy(BASE),
        "overrides": {"profit": "9.02"},
        "effective": calculate_effective(BASE, {"profit": "9.02"}, CONFIG),
        "history": [{"revision": 3, "reason": "verified operator change"}],
    }
    row = {
        "a": "acct", "s": "store", "i": "item", "registry_id": "uuid",
        "grade": "C", "score": Decimal("6.8735"),
        "first_wfs_available_date_la": date(2026, 11, 1),
        "first_batch_sold_out_date_la": None,
        "sold_out_evidence_status": "unverified", "listing_date_la": None,
        "frozen_suggested_qty": None, "review_status": None, "review_id": None,
        "data_coverage_json": {
            "evaluation_grade_confirmation_v1": {"status": "pending"},
            "evaluation_final_snapshot": {
                "grade": "C", "total": BASE["total"],
                "dimensions": deepcopy(BASE["dimensions"]), "rule_version": 2,
                "market_score": 7,
                "risk_evaluation": {
                    **ROI_B,
                    "base_grade": "C",
                    "effective_grade": "C",
                },
            },
            "operator_score_correction_v1": correction,
        },
    }

    class FakeResult:
        def mappings(self):
            return self
        def all(self):
            return [row]

    class FakeSession:
        def execute(self, _stmt, _params):
            return FakeResult()

    def listing():
        return {"items": [{
            "listing": {"source_account_ref": "acct", "store_id": "store",
                        "item_id": "item", "first_wfs_available_date_la": "2026-11-01"},
            "evaluation": {"grade": None, "total": None, "rule_version": 2,
                           "dimensions": deepcopy(BASE["dimensions"]),
                           "observation_state": "calculated"},
            "facts": {}, "suggested_qty": None,
        }]}

    applied = workflow.decorate_page(FakeSession(), listing())["items"][0]
    assert applied["score_correction_revision"] == 3
    assert applied["score_correction_state"] == "applied"
    assert applied["score_correction"]["revision"] == 3
    assert applied["evaluation"]["dimensions"]["profit"] == "9.02"
    assert applied["evaluation"]["grade"] == "B"

    row["data_coverage_json"]["evaluation_final_snapshot"]["dimensions"]["profit"] = "4.05"
    stale = workflow.decorate_page(FakeSession(), listing())["items"][0]
    assert stale["score_correction_revision"] == 3
    assert stale["score_correction_state"] == "stale"
    assert stale.get("score_correction") is None
    assert stale["suggested_qty"] is None


# A grade cap must survive even when the ORIGINAL score did not need capping.
ROI_B = {
    "rule_version": 2,
    "base_grade": "B",
    "effective_grade": "B",
    "risk_hits": [{
        "source": "manual", "name": "ROI低（评级上限）",
        "code": "roi_low", "limit": "B", "observed": None,
    }],
    "manual_selected": ["ROI低（评级上限）"],
}


def test_roi_cap_survives_operator_correction():
    baseline = deepcopy(BASE)
    baseline["dimensions"]["market"] = "10"
    baseline["total"] = "7.3170"
    baseline["grade"] = "B"
    revised = calculate_effective(
        baseline, {"profit": "9.02"}, CONFIG, risk_evaluation=ROI_B
    )
    assert revised["total"] == "8.57"
    assert revised["grade"] == "B"
    assert calculate_effective(baseline, {"profit": "9.02"}, CONFIG)["grade"] == "A"


def test_roi_cap_limits_grade_when_initial_grade_was_c():
    baseline = deepcopy(BASE)
    baseline["total"] = "6.8735"
    baseline["grade"] = "C"
    c_risk = {**ROI_B, "base_grade": "C", "effective_grade": "C"}
    revised = calculate_effective(
        baseline, {"profit": "9.02"}, CONFIG, risk_evaluation=c_risk
    )
    assert revised["grade"] == "B"


def test_roi_cap_applies_to_loaded_saved_overlay():
    baseline = deepcopy(BASE)
    baseline["dimensions"]["market"] = "10"
    baseline["total"] = "7.3170"
    baseline["grade"] = "B"
    saved = {
        "revision": 2,
        "system": baseline,
        "overrides": {"profit": "9.02"},
        "history": [],
    }
    row = {"evaluation": {**deepcopy(baseline), "observation_state": "scored"}, "facts": {}}
    assert overlay(row, saved, CONFIG, risk_evaluation=ROI_B, require_risk=True)
    assert row["evaluation"]["total"] == "8.57"
    assert row["evaluation"]["grade"] == "B"


def test_missing_risk_snapshot_fails_closed_for_pending():
    baseline = deepcopy(BASE)
    row = {"evaluation": {**deepcopy(baseline), "observation_state": "scored"}, "facts": {}}
    saved = {"revision": 1, "system": baseline, "overrides": {}, "history": []}
    assert not overlay(row, saved, CONFIG, require_risk=True)


def test_malformed_risk_evidence_cannot_bypass_grade_cap():
    baseline = deepcopy(BASE)
    baseline["dimensions"]["market"] = "10"
    baseline["total"] = "7.3170"
    baseline["grade"] = "B"
    for malformed in (
        {**ROI_B, "risk_hits": []},
        {
            **ROI_B,
            "risk_hits": [
                {"source": "manual", "name": "ROI低（评级上限）", "limit": "bogus"}
            ],
        },
        {**ROI_B, "effective_grade": "A"},
        {**ROI_B, "rule_version": 999},
    ):
        with pytest.raises(ValueError):
            calculate_effective(
                baseline, {"profit": "9.02"}, CONFIG, risk_evaluation=malformed
            )


def test_strictest_saved_cap_wins():
    baseline = deepcopy(BASE)
    baseline["dimensions"]["market"] = "10"
    baseline["total"] = "7.3170"
    baseline["grade"] = "C"
    strict = {
        **ROI_B, "effective_grade": "C",
        "risk_hits": [
            *ROI_B["risk_hits"],
            {"source": "system", "name": "毛利率过低", "code": "low_margin", "limit": "C"},
        ],
    }
    revised = calculate_effective(baseline, {"profit": "9.02"}, CONFIG, risk_evaluation=strict)
    assert revised["grade"] == "C"
