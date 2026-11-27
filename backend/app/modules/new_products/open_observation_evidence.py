"""Read-only view evidence for active new products; saved scores remain unchanged."""

from __future__ import annotations

from typing import Any

FIELDS = (
    "ad_status",
    "ad_spend_usd",
    "ad_clicks",
    "ad_orders",
    "ad_revenue_usd",
    "ad_latest_sync",
    "valid_units_14d",
    "valid_orders_14d",
    "single_unit_orders_14d",
)


def project_open_observation_evidence(row: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Use actual scoped 14-day facts for display; never fabricate or re-score."""
    if row.get("evaluation", {}).get("observation_state") == "frozen":
        return
    facts = row["facts"]
    for name in FIELDS:
        # Missing fields stay missing, not inferred from a saved dimension score.
        facts[name] = evidence.get(name)
