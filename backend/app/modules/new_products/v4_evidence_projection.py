"""Read-only projection for the committed PR337 V4 scoring evidence.

Do not reconstruct orders from score, do not infer mismatched mart sales, and do
not query the source warehouse in a GET request. All evidence originates from
the already-committed performance JSONB snapshot, with an explicit provenance.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .rules import DEFAULT_PARAMETERS
from .scoring import evaluate

_V4 = "PR337_SOURCE_REBUILD_V4"
_TOLERANCE = Decimal("0.015")


def _decimal(value: Any) -> Decimal | None:
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (str, int, float, Decimal))
    ):
        return None
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return result if result.is_finite() else None


def _integer(value: Any) -> int | None:
    number = _decimal(value)
    if number is None or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _score_match(a: Any, b: Any) -> bool:
    x, y = _decimal(a), _decimal(b)
    return bool(
        x is not None
        and y is not None
        and 0 <= x <= 10
        and 0 <= y <= 10
        and abs(x - y) <= _TOLERANCE
    )


def _date(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def _calculate(facts: dict[str, Any], dimension: str) -> Any:
    # Always reuse the actual core scoring evaluator. Missing market, ad and
    # profit ensure the function returns only independent dimension scores.
    snapshot = {
        "market_score": None,
        "ad_status": "unknown",
        "elapsed_days": 14,
        **facts,
    }
    result = evaluate(snapshot, {"confirmedScoring": DEFAULT_PARAMETERS, "weights": {}}, 0)
    return result["dimensions"].get(dimension)


def attach_v4_saved_evidence(row: dict[str, Any], perf: Any, coverage: dict[str, Any]) -> None:
    """Fill the existing `facts` response, never replace saved scores or write data."""
    if not isinstance(coverage, dict):
        return
    evaluation = row.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("observation_state") == "frozen":
        return
    saved = coverage.get("auto_dimension_scores")
    if not isinstance(saved, dict) or saved.get("scoring_provenance") != _V4:
        return
    if _integer(saved.get("rule_version")) != 0 or _integer(evaluation.get("rule_version")) != 0:
        return
    dimensions = evaluation.get("dimensions")
    facts = row.get("facts")
    if not isinstance(dimensions, dict) or not isinstance(facts, dict):
        return
    window_start = _date(getattr(perf, "metric_window_start_la", None))
    window_end = _date(getattr(perf, "metric_window_end_la", None))
    if window_start is None or window_end is None:
        return

    def same_window(proof: Any) -> bool:
        return bool(
            isinstance(proof, dict)
            and proof.get("source") == "fact_walmart_order_items"
            and proof.get("status") == "scored"
            and _integer(proof.get("rule_version")) == 0
            and proof.get("window_start_la") == window_start
            and proof.get("window_end_la") == window_end
        )

    # Speed and trust are independent. They use the *same* order-fact identity
    # but not the historical mart's order-count column. Preserve the mart
    # totals elsewhere for reporting / accounting; never overwrite the DB.
    speed = coverage.get("speed_history_full")
    if same_window(speed):
        first_day = _integer(speed.get("first_order_day"))
        orders = _integer(speed.get("effective_orders_14d"))
        original_mart_orders = _integer(getattr(perf, "sales_orders", None))
        if (
            first_day is not None
            and 1 <= first_day <= 14
            and orders is not None
            and orders > 0
            and _integer(speed.get("mart_orders")) == original_mart_orders
            and _integer(speed.get("order_fact_orders")) == orders
            and _score_match(speed.get("score"), dimensions.get("speed"))
        ):
            expected_speed = _calculate(
                {"first_order_day": first_day, "effective_orders_14d": orders}, "speed"
            )
            if _score_match(expected_speed, dimensions.get("speed")):
                facts["first_order_day"] = first_day
                facts["effective_orders_14d"] = orders
                facts["speed_evidence_source"] = "PR337_V4_VERIFIED_ORDER_FACT"

    trust = coverage.get("trust_history_full")
    if same_window(trust):
        units = _decimal(trust.get("valid_units_14d"))
        orders = _integer(trust.get("valid_orders_14d"))
        singles = _integer(trust.get("single_unit_orders_14d"))
        mart_units = _decimal(trust.get("mart_units"))
        original_mart_units = _decimal(getattr(perf, "sales_units", None))
        original_mart_orders = _integer(getattr(perf, "sales_orders", None))
        if (
            units is not None
            and units > 0
            and orders is not None
            and orders > 0
            and singles is not None
            and 0 <= singles <= orders
            and units >= orders
            and mart_units is not None
            and original_mart_units == mart_units
            and _integer(trust.get("mart_orders")) == original_mart_orders
            and _score_match(trust.get("score"), dimensions.get("trust"))
        ):
            expected_trust = _calculate(
                {
                    "valid_units_14d": units,
                    "valid_orders_14d": orders,
                    "single_unit_orders_14d": singles,
                },
                "trust",
            )
            if _score_match(expected_trust, dimensions.get("trust")):
                facts["valid_units_14d"] = str(units)
                facts["valid_orders_14d"] = orders
                facts["single_unit_orders_14d"] = singles
                facts["single_unit_orders_evidence"] = "PR337_V4_VERIFIED_ORDER_FACT"
                facts["trust_evidence_source"] = "fact_walmart_order_items"

    # A diagnostic field, not a business value: confirms API runtime is
    # projecting the same V4 generation as the production database.
    facts["auto_scoring_provenance"] = _V4
