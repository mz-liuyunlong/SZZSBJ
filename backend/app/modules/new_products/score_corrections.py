"""Operator score corrections: immutable system baseline, versioned effective scores.

This module is pure: no database or external API access. All scores 0..10.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal

DIMENSIONS = ("speed", "ad", "profit", "trust")
ORDER = ("S", "A", "B", "C", "D", "Pass")
TWO = Decimal("0.01")
STORAGE = Decimal("0.0001")


def _dec(value):
    if value is None or isinstance(value, bool):
        raise ValueError("invalid score")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("invalid score")
    return number


def _apply_saved_risks(grade: str, evidence: dict) -> str:
    """Limit a corrected grade using the frozen, source-verified risk hits.

    A grade cap must remain active even if the ORIGINAL grade was below it.
    Reject malformed, contradictory or unverifiable saved risk records.
    """
    if not isinstance(evidence, dict):
        raise ValueError("missing frozen risk evidence")
    base = evidence.get("base_grade")
    effective = evidence.get("effective_grade")
    hits = evidence.get("risk_hits")
    selected = evidence.get("manual_selected")
    if (
        base not in ORDER[:5]
        or effective not in ORDER
        or not isinstance(hits, list)
        or not isinstance(selected, list)
    ):
        raise ValueError("invalid frozen risk evidence")
    limits = []
    selected_manual = set()
    for item in hits:
        if not isinstance(item, dict):
            raise ValueError("malformed frozen risk hit")
        limit = item.get("limit")
        if limit not in ("none", "B", "C", "D", "recommend_not_pass"):
            raise ValueError("invalid frozen risk limit")
        if item.get("source") not in ("system", "manual"):
            raise ValueError("invalid frozen risk source")
        if item["source"] == "manual":
            if not isinstance(item.get("name"), str):
                raise ValueError("invalid frozen manual risk")
            selected_manual.add(item["name"])
        limits.append(limit)
    if any(not isinstance(name, str) for name in selected):
        raise ValueError("invalid frozen manual selection")
    if set(selected) - {"无"} != selected_manual:
        raise ValueError("frozen manual risk selection does not match risk hits")

    def cap(current: str) -> str:
        for limit in limits:
            if limit == "recommend_not_pass":
                return "Pass"
            if limit in ORDER[:5] and ORDER.index(current) < ORDER.index(limit):
                current = limit
        return current

    if cap(base) != effective:
        raise ValueError("frozen risk result differs from evidence")
    if grade not in ORDER:
        raise ValueError("invalid proposed grade")
    return cap(grade)


def calculate_effective(
    system: dict, overrides: dict, config: dict, *, risk_evaluation: dict | None = None
) -> dict:
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
    if original_grade not in ORDER:
        raise ValueError("invalid system grade")
    if risk_evaluation is not None:
        if risk_evaluation.get("rule_version") != system.get("rule_version"):
            raise ValueError("frozen risk rule version changed")
        if original_grade != risk_evaluation.get("effective_grade"):
            raise ValueError("frozen risk baseline grade changed")
        selected = _apply_saved_risks(selected, risk_evaluation)
    else:
        # Legacy snapshots without a frozen risk block retain their old protection.
        original_total = _dec(system["total"]).quantize(TWO, rounding=ROUND_HALF_UP)
        unconstrained_original = band(original_total)
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


def resolved_system(evaluation: dict, system: dict, *, exact_total: bool = False) -> dict | None:
    """Resolve a baseline against an exact snapshot or a NUMERIC(10,4) read."""
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
        # NP_GRADE_CONFIRM_EXACT_PRECISION_V1: final JSONB snapshots retain exact precision.
        # Only persisted list reads use the PostgreSQL NUMERIC(10,4) scale.
        expected_total = _dec(system["total"])
        if not exact_total:
            expected_total = expected_total.quantize(STORAGE, rounding=ROUND_HALF_UP)
        if (
            evaluation.get("total") is None
            or evaluation.get("grade") != system.get("grade")
            or _dec(evaluation["total"]) != expected_total
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


def overlay(
    row: dict,
    block: dict,
    config: dict,
    *,
    risk_evaluation: dict | None = None,
    require_risk: bool = False,
) -> bool:
    """Use only a matching official snapshot; never invent a grade before market."""
    ev = row.get("evaluation")
    if not isinstance(ev, dict) or ev.get("observation_state") == "frozen":
        return False
    system = block.get("system")
    if require_risk and not isinstance(risk_evaluation, dict):
        return False
    if (
        not isinstance(system, dict)
        or type(block.get("revision")) is not int
        or block["revision"] < 0
        or not isinstance(block.get("history"), list)
        or not isinstance(block.get("overrides"), dict)
    ):
        return False
    try:
        resolved = resolved_system(ev, system)
        if resolved is None:
            return False
        changed = calculate_effective(
            resolved, block["overrides"], config, risk_evaluation=risk_evaluation
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return False
    ev["dimensions"] = deepcopy(changed["dimensions"])
    ev["total"] = changed["total"]
    ev["grade"] = changed["grade"]
    info = public_correction(block, system=resolved, effective=changed)
    row["score_correction"] = info
    row.setdefault("facts", {})["score_correction"] = info
    return True
