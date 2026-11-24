"""Pure new-product assessment eligibility: never use orders as a listing-date proxy.

A background observation is not a published assessment. Actual publication needs
verified source evidence and one of three authorized triggers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

PASS = frozenset({"S", "A", "B", "C"})
FAIL = frozenset({"D", "Pass"})


def day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def fourteen_days(first_positive_wfs: date | None, cutoff_la: date) -> bool:
    return bool(first_positive_wfs and first_positive_wfs <= cutoff_la - timedelta(days=13))


def valid_sold_out(verified: Any, day_value: Any, first: date | None, cutoff: date) -> bool:
    last = day(day_value)
    return bool(verified == "verified" and last and first and first <= last <= cutoff)


def eligible(
    *, first_wfs: date | None, cutoff: date, sold_status: Any, sold_day: Any, manual: bool = False
) -> tuple[bool, str]:
    if first_wfs is None or first_wfs > cutoff:
        return False, "WFS_FIRST_STOCK_NOT_VERIFIED"
    if manual:
        return True, "manual"
    if fourteen_days(first_wfs, cutoff):
        return True, "auto_14d"
    if valid_sold_out(sold_status, sold_day, first_wfs, cutoff):
        return True, "auto_sold_out"
    return False, "OBSERVATION_IN_PROGRESS"


def evaluation_status(
    *, listing_date: Any, first_wfs: Any, coverage: dict | None, grade: Any, total: Any
) -> str:
    if grade is not None and total is not None:
        confirmation = (
            coverage.get("evaluation_grade_confirmation_v1")
            if isinstance(coverage, dict) else None
        )
        if isinstance(confirmation, dict) and confirmation.get("status") == "pending":
            return "待等级确认"
        record = coverage.get("operator_assessment_v1") if isinstance(coverage, dict) else None
        if isinstance(record, dict) and record.get("decision") == "passed":
            return "测评通过"
        if isinstance(record, dict) and record.get("decision") == "failed":
            return "测评未通过"
        return "待测评确认"
    if not (day(listing_date) or day(first_wfs)):
        return "待到货"
    coverage = coverage if isinstance(coverage, dict) else {}
    trigger = coverage.get("evaluation_formal_trigger")
    auto = coverage.get("auto_dimension_scores")
    if (
        isinstance(trigger, dict)
        and trigger.get("status") == "completed"
        and isinstance(auto, dict)
    ):
        return "待市场评分"
    return "测评中"
