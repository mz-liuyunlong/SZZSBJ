"""Synthetic-only Listing grade demonstration; no database, API or business writes.

Use the canonical evaluation engine and in-memory financial days. This module
does not implement real Listing data adaptation or authorize automatic ratings.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.modules.listing_rule_config.evaluation import (
    FinancialDay,
    grade_listing,
    rating_cutoff_la,
)
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

# All sales and profits below are synthetic USD examples for UI/calculation review.
# A missing upstream proof is intentionally NOT equivalent to confirmed zero spend.
SCENARIOS: dict[str, tuple[str, str, bool, str]] = {
    "a": ("100", "20", True, "启动期"),
    "b": ("100", "12", True, "启动期"),
    "c": ("100", "7", True, "启动期"),
    "d": ("100", "2", True, "启动期"),
    "zero-sales-loss": ("0", "-5", True, "启动期"),
    "pending": ("100", "20", False, "启动期"),
    "excluded": ("100", "20", True, "清货期"),
}


def demo_result(scenario: str, *, cutoff: date) -> dict[str, object]:
    """Return a serializable grade result for fixed, explicitly synthetic days."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown synthetic scenario: {scenario}")
    sales, profit, confirmed, stage = SCENARIOS[scenario]
    config = ListingGradeRuleConfig()
    days = [
        FinancialDay(
            day=cutoff - timedelta(days=offset),
            sales=Decimal(sales),
            profit=Decimal(profit),
            cost_status="complete",
            upstream_confirmed=confirmed,
        )
        for offset in range(config.medium_days)
    ]
    result = grade_listing(cutoff=cutoff, stage=stage, days=days, config=config)

    def amount(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    return {
        "data_source": "SYNTHETIC_ONLY",
        "writes_performed": False,
        "rule_source": "in_code_default_config_not_saved_version",
        "scenario": scenario,
        "stage": stage,
        "cutoff_la": cutoff.isoformat(),
        "grade": result.grade,
        "reason": result.reason,
        "valid_days_short": result.valid_short,
        "valid_days_medium": result.valid_medium,
        "sales_short": amount(result.sales_short),
        "profit_short": amount(result.profit_short),
        "sales_medium": amount(result.sales_medium),
        "profit_medium": amount(result.profit_medium),
        "margin_short_percent": amount(result.margin_short),
        "margin_medium_percent": amount(result.margin_medium),
        "weighted_margin_percent": amount(result.weighted_margin),
        "invalid_dates": [day.isoformat() for day in result.invalid_dates],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Listing synthetic grade demo: never reads or writes a database."
    )
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="c")
    parser.add_argument(
        "--cutoff",
        type=date.fromisoformat,
        default=None,
        help="Los Angeles business cutoff YYYY-MM-DD; defaults to LA T-2.",
    )
    args = parser.parse_args()
    cutoff = args.cutoff or rating_cutoff_la(datetime.now(UTC))
    print(json.dumps(demo_result(args.scenario, cutoff=cutoff), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
