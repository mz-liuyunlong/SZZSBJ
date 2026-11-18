"""Business invariants for direct operator corrections; no DB dependency."""

from decimal import Decimal

import pytest
from app.modules.new_products.score_corrections import calculate_effective, overlay

CONFIG = {
    "weights": {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10},
    "gradeBands": {"S": [9, 10], "A": [8, 8.99], "B": [7, 7.99], "C": [6, 6.99], "D": [0, 5.99]},
}
BASE = {
    "total": "6.80",
    "grade": "C",
    "rule_version": 3,
    "dimensions": {"market": "8.0", "speed": "4.60", "ad": "7.0", "profit": "8.00", "trust": "8.2"},
    "ad_excluded": False,
}


def test_original_remains_immutable_and_grade_changes():
    from copy import deepcopy

    base = deepcopy(BASE)
    new = calculate_effective(base, {"speed": "8.00"}, CONFIG)
    assert BASE == base
    assert new["dimensions"]["speed"] == "8.00"
    assert Decimal(new["total"]) > Decimal("6.80")


def test_pass_veto_never_bypassed():
    base = dict(BASE, grade="Pass")
    new = calculate_effective(base, {"speed": "10.00"}, CONFIG)
    assert new["grade"] == "Pass"


def test_risk_cap_never_bypassed():
    base = dict(BASE, grade="C", total="8.60")
    new = calculate_effective(base, {"speed": "10.00"}, CONFIG)
    assert new["grade"] == "C"


@pytest.mark.parametrize("value", ["-1", "11", "NaN", "1.234", None])
def test_invalid_scores_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        calculate_effective(BASE, {"speed": value}, CONFIG)


def test_overlay_preserves_base_in_score_correction():
    from copy import deepcopy

    original = deepcopy(BASE)
    block = {
        "revision": 1,
        "system": original,
        "overrides": {"speed": "8.00"},
        "effective": calculate_effective(original, {"speed": "8.00"}, CONFIG),
        "history": [{"actor_id": "operator"}],
    }
    row = {"evaluation": deepcopy(BASE) | {"observation_state": "scored"}, "facts": {}}
    assert overlay(row, block, CONFIG)
    assert row["score_correction"]["system"]["dimensions"]["speed"] == "4.60"
    assert row["evaluation"]["dimensions"]["speed"] == "8.00"


def test_before_market_operator_can_correct_without_inventing_grade():
    from copy import deepcopy

    pending = deepcopy(BASE)
    pending["total"] = None
    pending["grade"] = None
    pending["dimensions"]["market"] = None
    changed = calculate_effective(pending, {"speed": "8.00"}, CONFIG)
    assert changed["total"] is None
    assert changed["grade"] is None
    block = {
        "revision": 1,
        "system": pending,
        "overrides": {"speed": "8.00"},
        "effective": changed,
        "history": [],
    }
    row = {
        "evaluation": deepcopy(pending) | {"observation_state": "automatic_partial"},
        "facts": {},
    }
    assert overlay(row, block, CONFIG)
    assert row["evaluation"]["dimensions"]["speed"] == "8.00"
    row2 = {"evaluation": deepcopy(BASE) | {"observation_state": "scored"}, "facts": {}}
    assert overlay(row2, block, CONFIG)
    assert row2["evaluation"]["total"] is not None
    assert row2["score_correction"]["system"]["total"] == "6.80"


def test_open_scores_update_without_losing_operator_override():
    from copy import deepcopy

    pending = deepcopy(BASE)
    pending["total"] = None
    pending["grade"] = None
    pending["dimensions"]["market"] = None
    block = {
        "revision": 1,
        "system": pending,
        "overrides": {"speed": "8.00"},
        "effective": calculate_effective(pending, {"speed": "8.00"}, CONFIG),
        "history": [],
    }
    newer = deepcopy(pending)
    newer["dimensions"]["trust"] = "9.00"
    row = {"evaluation": newer | {"observation_state": "calculated"}, "facts": {}}
    assert overlay(row, block, CONFIG)
    assert row["evaluation"]["dimensions"]["speed"] == "8.00"
    assert row["evaluation"]["dimensions"]["trust"] == "9.00"


def test_overlay_fails_closed_on_stale_total_or_frozen():
    block = {
        "revision": 1,
        "system": BASE,
        "overrides": {"speed": "8.00"},
        "effective": calculate_effective(BASE, {"speed": "8.00"}, CONFIG),
        "history": [],
    }
    for change in ({"total": "7.50"}, {"observation_state": "frozen"}):
        row = {"evaluation": dict(BASE, observation_state="scored") | change, "facts": {}}
        assert not overlay(row, block, CONFIG)
