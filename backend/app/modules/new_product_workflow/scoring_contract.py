"""New-product scoring contract: confirmed procurement bands vs candidate grades.

Candidate thresholds from the historical spreadsheets are NOT an owner-approved
formal contract. Never turn a draft preview into a binding purchase decision.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Confirmed by the business owner; upper/lower bounds are inclusive.
CONFIRMED_PURCHASE_BANDS: dict[str, tuple[int, int]] = {
    "S": (400, 600),
    "A": (300, 500),
    "B": (200, 400),
    "C": (150, 250),
    "D": (0, 0),
    "Pass": (0, 0),
}
# Historical example 7.85 => B by a candidate formula, while the source
# operator assigned C. This is evidence of an unresolved policy, not a
# reason to secretly change the grade or override the human decision.
CANDIDATE_GRADE_FLOORS: tuple[tuple[str, float], ...] = (
    ("S", 9.0),
    ("A", 8.0),
    ("B", 7.0),
    ("C", 6.0),
    ("D", 0.0),
)
MIN_LISTING_DAYS_FOR_MARKET_REVIEW = 30


def candidate_grade(score: float | None) -> str | None:
    if score is None or score < 0 or score > 10:
        return None
    return next((grade for grade, floor in CANDIDATE_GRADE_FLOORS if score >= floor), None)


def normalized_purchase_bands(rules: dict[str, Any] | None) -> dict[str, tuple[int, int]]:
    raw = (rules or {}).get("purchase_bands")
    if raw is None:
        return dict(CONFIRMED_PURCHASE_BANDS)
    if not isinstance(raw, dict) or set(raw) != set(CONFIRMED_PURCHASE_BANDS):
        raise ValueError("purchase bands require S/A/B/C/D/Pass")
    bands: dict[str, tuple[int, int]] = {}
    for grade, pair in raw.items():
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("each purchase band needs inclusive low and high")
        low, high = pair
        if not isinstance(low, int) or isinstance(low, bool):
            raise ValueError("purchase low must be a whole number")
        if not isinstance(high, int) or isinstance(high, bool):
            raise ValueError("purchase high must be a whole number")
        if low < 0 or low > high:
            raise ValueError("invalid purchase quantity band")
        if grade in ("D", "Pass") and (low, high) != (0, 0):
            raise ValueError("D and Pass cannot produce procurement")
        if (low, high) != CONFIRMED_PURCHASE_BANDS[grade]:
            raise ValueError("confirmed purchase bands require owner approval to change")
        bands[grade] = (low, high)
    return bands


def purchase_preview(
    grade: str | None, demand_qty: int | None, rules: dict[str, Any] | None = None
) -> dict[str, Any]:
    """No suggested quantity without a reliable forecast and final grade."""
    bands = normalized_purchase_bands(rules)
    if grade not in bands:
        return {"status": "awaiting_grade", "suggested_qty": None, "range": None}
    low, high = bands[grade]
    if grade in ("D", "Pass"):
        return {"status": "no_procurement", "suggested_qty": 0, "range": [0, 0]}
    if demand_qty is None or demand_qty < 0:
        return {
            "status": "awaiting_verified_demand",
            "suggested_qty": None,
            "range": [low, high],
        }
    return {
        "status": "candidate_not_formal",
        "suggested_qty": min(high, max(low, int(demand_qty))),
        "range": [low, high],
    }


def quantity_exception(
    quantity: int, grade: str | None, rules: dict[str, Any] | None = None
) -> bool | None:
    bands = normalized_purchase_bands(rules)
    if grade not in bands:
        return None
    low, high = bands[grade]
    return quantity < low or quantity > high


def market_review_readiness(
    listing_business_date: date | None, *, today_la: date
) -> dict[str, Any]:
    if listing_business_date is None:
        return {"status": "listing_date_unverified", "elapsed_days": None}
    elapsed = (today_la - listing_business_date).days
    if elapsed < 0:
        return {"status": "listing_date_invalid", "elapsed_days": elapsed}
    return {
        "status": "ready_for_market_review"
        if elapsed >= MIN_LISTING_DAYS_FOR_MARKET_REVIEW
        else "observation_not_yet_30_days",
        "elapsed_days": elapsed,
    }


def formal_policy_gate(rules: dict[str, Any] | None) -> dict[str, Any]:
    """A saved draft alone cannot authorize official grade/ROI/penalties."""
    policy = rules or {}
    blockers = []
    if policy.get("formal_contract_approved") is not True:
        blockers.append("formal_contract_not_approved")
    if not policy.get("scoring_golden_cases_verified"):
        blockers.append("golden_cases_not_reconciled")
    if not policy.get("roi_investment_basis_approved"):
        blockers.append("roi_investment_basis_unapproved")
    if not policy.get("penalty_veto_contract_approved"):
        blockers.append("penalties_and_veto_not_approved")
    return {
        "status": "blocked" if blockers else "eligible_for_formal_review",
        "blockers": blockers,
        "historical_grade_conflict": "YC00738 candidate B vs recorded manual C",
        "auto_publish": False,
    }
