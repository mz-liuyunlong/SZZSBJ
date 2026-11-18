"""Operator score corrections: immutable system baseline, versioned effective scores.

This module is pure: no database or external API access. All scores 0..10.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

DIMENSIONS = ("speed", "ad", "profit", "trust")
ORDER = ("S", "A", "B", "C", "D", "Pass")
TWO = Decimal("0.01")


def _dec(value):
    if value is None or isinstance(value, bool):
        raise ValueError("invalid score")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("invalid score")
    return number


def calculate_effective(system: dict, overrides: dict, config: dict) -> dict:
    """Calculate from saved dimensions; never recompute or rewrite original evidence."""
    dimensions = deepcopy(system["dimensions"])
    if not isinstance(dimensions, dict):
        raise ValueError("missing system dimensions")
    for name, value in overrides.items():
        if name not in DIMENSIONS:
            raise ValueError("invalid dimension")
        number = _dec(value)
        if not Decimal("0") <= number <= Decimal("10") or number != number.quantize(TWO):
            raise ValueError("invalid corrected score")
        if dimensions.get(name) is None:
            raise ValueError("missing verified dimension")
        dimensions[name] = str(number)
    if system.get("total") is None or system.get("grade") is None:
        return {"dimensions": dimensions, "total": None, "grade": None}
    weights = config["weights"]
    active = ["market", *DIMENSIONS]
    if system.get("ad_excluded"):
        active.remove("ad")
    numerator = Decimal("0")
    denominator = Decimal("0")
    for key in active:
        if dimensions.get(key) is None:
            raise ValueError("unverified dimension")
        weight = _dec(weights[key])
        numerator += _dec(dimensions[key]) * weight
        denominator += weight
    if denominator <= 0:
        raise ValueError("invalid scoring weights")
    total = (numerator / denominator).quantize(TWO, rounding=ROUND_HALF_UP)

    def band(value):
        for name in ORDER[:5]:
            low, high = config["gradeBands"][name]
            if _dec(low) <= value <= _dec(high):
                return name
        raise ValueError("uncovered score band")

    selected = band(total)
    original_grade = system["grade"]
    original_total = _dec(system["total"]).quantize(TWO, rounding=ROUND_HALF_UP)
    unconstrained_original = band(original_total)
    if original_grade not in ORDER:
        raise ValueError("invalid system grade")
    # Preserve existing risk / veto constraints. Corrections cannot bypass them.
    if original_grade == "Pass":
        selected = "Pass"
    elif ORDER.index(original_grade) > ORDER.index(unconstrained_original):
        selected = ORDER[max(ORDER.index(selected), ORDER.index(original_grade))]
    return {"dimensions": dimensions, "total": str(total), "grade": selected}


def public_correction(block: dict, *, system=None, effective=None) -> dict:
    return deepcopy(
        {
            "revision": block["revision"],
            "system": system if system is not None else block["system"],
            "effective": effective if effective is not None else block["effective"],
            "history": block["history"],
        }
    )


def resolved_system(evaluation: dict, system: dict) -> dict | None:
    """Attach a later formal market result to a pre-market immutable auto baseline."""
    if evaluation.get("rule_version") != system.get("rule_version"):
        return None
    published = evaluation.get("dimensions")
    if not isinstance(published, dict):
        return None
    if system.get("total") is not None:
        for dimension in DIMENSIONS:
            value = system["dimensions"].get(dimension)
            current = published.get(dimension)
            if (value is None) != (current is None):
                return None
            if value is not None and _dec(value) != _dec(current):
                return None
    if system.get("total") is not None:
        if (
            evaluation.get("total") is None
            or evaluation.get("grade") != system.get("grade")
            or _dec(evaluation["total"]) != _dec(system["total"])
        ):
            return None
        return deepcopy(system)
    official = deepcopy(system)
    official["dimensions"] = deepcopy(published)
    if evaluation.get("total") is not None and evaluation.get("grade") is not None:
        official["total"] = evaluation["total"]
        official["grade"] = evaluation["grade"]
        official["ad_excluded"] = bool(evaluation.get("ad_excluded", False))
    return official


def overlay(row: dict, block: dict, config: dict) -> bool:
    """Use only a matching official snapshot; never invent a grade before market."""
    ev = row.get("evaluation")
    if not isinstance(ev, dict) or ev.get("observation_state") == "frozen":
        return False
    system = block.get("system")
    if not isinstance(system, dict):
        return False
    resolved = resolved_system(ev, system)
    if resolved is None:
        return False
    try:
        changed = calculate_effective(resolved, block["overrides"], config)
    except (KeyError, ValueError, ArithmeticError):
        return False
    ev["dimensions"] = deepcopy(changed["dimensions"])
    ev["total"] = changed["total"]
    ev["grade"] = changed["grade"]
    info = public_correction(block, system=resolved, effective=changed)
    row["score_correction"] = info
    row.setdefault("facts", {})["score_correction"] = info
    return True
