"""Read-only integration for current and final-locked PR337 testing results."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .persisted_projection import merge_persisted_page_row
from .scoring import up, weighted
from .testing_profit import FinalDecision, decimal_value

WEIGHTED_DIMENSIONS = ("speed", "ad", "profit", "trust")


def attach_testing_profit_facts(facts: dict[str, Any], result: dict[str, Any] | None) -> None:
    if result is None:
        return
    for field in (
        "profit_usd",
        "roi",
        "gross_margin_pct",
        "sales_amount_usd",
        "sales_units",
        "sales_orders",
        "ad_spend_usd",
        "first_order_date",
        "sp_ad_spend_usd",
        "sem_ad_spend_usd",
    ):
        if field == "first_order_date" and result.get(field) is None:
            continue
        facts[field] = result.get(field)
    facts["profit_source"] = "new_products_testing_profit_full_history_v2"
    facts["profit_calc_status"] = result["status"]
    facts["profit_calc_missing"] = list(result.get("missing", []))
    # No sample order can create a first order. Retain 14-day speed quantity
    # denominators for the pre-existing speed rule, without converting lifetime
    # sales orders into artificial 14-day orders.
    first = facts.get("first_order_date")
    wfs = facts.get("first_wfs_available_date_la")
    if isinstance(first, str) and isinstance(wfs, (str, date)):
        try:
            first_date = date.fromisoformat(first)
            wfs_date = date.fromisoformat(wfs) if isinstance(wfs, str) else wfs
            facts["first_order_day"] = (first_date - wfs_date).days + 1
        except (ValueError, TypeError):
            facts["first_order_day"] = None


def testing_profit_dimension(result: dict[str, Any] | None, config: dict[str, Any]) -> str | None:
    if result is None or result.get("status") != "scored":
        return None
    parameters = config["confirmedScoring"]["profit"]
    roi = decimal_value(result["roi"])
    margin = decimal_value(result["gross_margin_pct"])
    if roi is None or margin is None:
        return None
    score = weighted(
        [
            (
                up(roi, decimal_value(parameters["roiZero"]), decimal_value(parameters["roiFull"])),
                decimal_value(parameters["roiWeight"]),
            ),
            (
                up(
                    margin,
                    decimal_value(parameters["marginZero"]),
                    decimal_value(parameters["marginFull"]),
                ),
                decimal_value(parameters["marginWeight"]),
            ),
        ]
    )
    return str(score)


def update_list_profit(
    row: dict[str, Any], result: dict[str, Any] | None, config: dict[str, Any]
) -> None:
    if result is None:
        return
    attach_testing_profit_facts(row["facts"], result)
    evaluation = row["evaluation"]
    dimensions = evaluation["dimensions"]
    dimensions["profit"] = testing_profit_dimension(result, config)
    # Recalculate only the automatic subtotal/coverage, not the manually
    # approved market result, final grade, or final tracking decision.
    total = Decimal(0)
    covered = Decimal(0)
    for dimension in WEIGHTED_DIMENSIONS:
        value = decimal_value(dimensions.get(dimension))
        if value is not None:
            weight = decimal_value(config["weights"][dimension])
            total += value * weight / 100
            covered += weight
    evaluation["automatic_points"] = str(total)
    evaluation["covered_weight_pct"] = str(covered)
    if result.get("status") != "scored":
        missing = evaluation.setdefault("missing", [])
        if "Testing profit insufficient" not in missing:
            missing.append("Testing profit insufficient")
    elif "Testing profit insufficient" in evaluation.get("missing", []):
        evaluation["missing"].remove("Testing profit insufficient")


def _unwrap_frozen_score(final: FinalDecision) -> dict[str, Any] | None:
    snap = final.snapshot
    if not isinstance(snap, dict):
        return None
    result = snap.get("score") if isinstance(snap.get("score"), dict) else snap
    if isinstance(result.get("facts"), dict) and isinstance(result.get("evaluation"), dict):
        return result
    return None


def lock_closed_row(
    row: dict[str, Any],
    final: FinalDecision,
    matched: Any,
    today: date,
) -> None:
    """Never read or recompute live profit for a completed item."""
    merge_persisted_page_row(row, matched, today)
    score = _unwrap_frozen_score(final)
    if score is not None:
        row["facts"] = deepcopy(score["facts"])
        row["evaluation"] = deepcopy(score["evaluation"])
    elif matched is not None and matched[1] is not None:
        # Old terminal records with no final score snapshot may show *only*
        # persisted values. Do not try to repair them using new live data.
        perf = matched[1]
        if getattr(perf, "score", None) is not None:
            row["evaluation"]["total"] = str(perf.score)
        if getattr(perf, "grade", None) is not None:
            row["evaluation"]["grade"] = perf.grade
    elif final.legacy_facts is not None:
        row["facts"] = deepcopy(final.legacy_facts)
        row["facts"].pop("__test_final_score_v2", None)

    # Do not let an old persisted projection increment elapsed days to today.
    start = row["facts"].get("first_wfs_available_date_la")
    stop = None
    if final.decided_at is not None:
        stop = final.decided_at.astimezone(ZoneInfo("America/Los_Angeles")).date()
    if score is not None:
        # Preserve the complete final score snapshot exactly as approved.
        pass
    elif start and stop:
        try:
            day = date.fromisoformat(start) if isinstance(start, str) else start
            row["facts"]["elapsed_days"] = max(0, (stop - day).days + 1)
        except (ValueError, TypeError):
            row["facts"]["elapsed_days"] = None
    else:
        row["facts"]["elapsed_days"] = None
    row["tracking_decision"] = final.result
    row["facts"]["data_status"] = "frozen"
    row["facts"]["profit_calc_status"] = "frozen"
    row["evaluation"]["observation_state"] = "frozen"
    row["system_recommendation"] = {
        "value": "Closed",
        "reasons": ["Successful or failed testing is permanently frozen"],
    }


def closed_list_row(
    listing: dict[str, Any], matched: Any, final: FinalDecision, today: date
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "listing": listing,
        "facts": {"first_wfs_available_date_la": listing.get("first_wfs_available_date_la")},
        "evaluation": {
            "rule_version": 0,
            "total": None,
            "grade": None,
            "dimensions": {
                "market": None,
                "speed": None,
                "ad": None,
                "profit": None,
                "trust": None,
            },
            "missing": ["Final snapshot has no stored evaluation"],
            "observation_state": "frozen",
        },
        "market_reason": None,
        "market_version": 0,
        "purchase_status": None,
        "purchase_id": None,
        "tracking_decision": final.result,
        "tracking_reason": None,
        "system_recommendation": {"value": "Closed", "reasons": []},
        "suggested_qty": None,
    }
    lock_closed_row(row, final, matched, today)
    return row


def closed_score(
    key: tuple[str, str, str], matched: Any, final: FinalDecision, today: date
) -> dict[str, Any]:
    row = closed_list_row(
        {"source_account_ref": key[0], "store_id": key[1], "item_id": key[2]},
        matched,
        final,
        today,
    )
    return {
        "identity": {"source_account_ref": key[0], "store_id": key[1], "item_id": key[2]},
        "facts": row["facts"],
        "evaluation": row["evaluation"],
        "rule_source": "frozen_snapshot",
        "rule_version": row["evaluation"].get("rule_version", 0),
    }
