"""Apply configured manual/system risks at formal market-score publication.

Only verified saved risk evidence may influence a final grade. No DB access.
"""

from datetime import date
from typing import Any

from .risk_conditions import RANK, assess_risks, normalize_risk_rules
from .risk_display import build_saved_risk_display


def resolve_final_risks(
    *,
    coverage: dict[str, Any],
    config: dict[str, Any],
    rule_version: int,
    base_grade: str,
    manual_selected: list[str] | None,
    cutoff: date | None,
    first_wfs: date | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if base_grade not in RANK:
        raise ValueError("NP_RISK_BASE_GRADE_INVALID")
    if cutoff is None or first_wfs is None:
        raise ValueError("NP_RISK_BUSINESS_WINDOW_UNVERIFIED")
    if not isinstance(config.get("riskConditions"), list):
        raise ValueError("NP_RISK_PUBLISHED_CONFIGURATION_REQUIRED")
    if not isinstance(manual_selected, list) or not manual_selected:
        raise ValueError("NP_RISK_MANUAL_SELECTION_REQUIRED")

    selected = list(manual_selected)
    for a, b in (
        ("ROI低（Pass）", "ROI低（评级上限）"),
        ("季节性（一般）", "季节性（强）"),
    ):
        if a in selected and b in selected:
            raise ValueError("NP_RISK_CONFLICTING_MANUAL_SELECTION")

    rules = normalize_risk_rules(config["riskConditions"])
    manual = assess_risks(
        base_grade=base_grade,
        facts={},
        manual_selected=selected,
        risk_rules=rules,
    )
    display = build_saved_risk_display(
        coverage,
        rules,
        cutoff_la=cutoff,
        first_wfs=first_wfs,
        rule_version=rule_version,
    )
    unverified = [
        x["code"] for x in display["rules"] if x["enabled"] and x["status"] == "unverified"
    ]
    if unverified:
        raise ValueError("NP_RISK_SYSTEM_EVIDENCE_UNVERIFIED:" + ",".join(unverified))

    hits = [dict(x) for x in manual["risk_hits"] if x["source"] == "manual"]
    system_hits = [x for x in display["rules"] if x["enabled"] and x["status"] == "hit"]
    hits.extend(
        {
            "code": x["code"],
            "name": x["name"],
            "source": "system",
            "limit": x["limit"],
            "observed": x["basis"],
        }
        for x in system_hits
    )

    grade = base_grade
    recommend_not_pass = False
    for hit in hits:
        limit = hit["limit"]
        if limit == "recommend_not_pass":
            recommend_not_pass = True
        elif limit in RANK and RANK[grade] < RANK[limit]:
            grade = limit
    if recommend_not_pass:
        grade = "Pass"

    frozen_display = {
        **display,
        "grade_cap_applied": bool(system_hits),
    }
    record = {
        "rule_version": rule_version,
        "base_grade": base_grade,
        "effective_grade": grade,
        "risk_hits": hits,
        "recommend_not_pass": recommend_not_pass,
        "manual_selected": selected,
        "system_evidence_cutoff_la": cutoff.isoformat(),
        "operator_decision": None,
    }
    return record, frozen_display
