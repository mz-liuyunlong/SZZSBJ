"""Overview rule parameters. Defaults = 8088 DEMO ``build_from_daily.py`` ``P``.

Persisted later as ``pmc_overview_rule_versions`` (version + effective date);
phase 1 is read-only (PRP pmc-overview D5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

RULE_VERSION_DEFAULT = "OVERVIEW-RULES-8088-20261102"


@dataclass(frozen=True)
class OverviewParams:
    # overview judgements
    min_supply_issue: int = 10
    over1: int = 120
    over2: int = 150
    sales_min_days: int = 14
    instock_min: int = 5
    domestic_days: int = 7
    domestic_min_qty: int = 10
    s1_days: int = 2
    s2_days: int = 7
    s3_fallback: int = 7
    # shared with replenishment (read-only reference, owned by pmc_replenishment)
    min_qty: int = 50
    cycle: int = 14
    cap_days: int = 30
    cap_qty: int = 300

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


# 8088 parameter key → field name (for loading DEMO snapshots in golden checks).
DEMO_KEY_MAP = {
    "minSupplyIssue": "min_supply_issue",
    "over1": "over1",
    "over2": "over2",
    "salesMinDays": "sales_min_days",
    "instockMin": "instock_min",
    "domesticDays": "domestic_days",
    "domesticMinQty": "domestic_min_qty",
    "s1Days": "s1_days",
    "s2Days": "s2_days",
    "s3Fallback": "s3_fallback",
    "minQty": "min_qty",
    "cycle": "cycle",
    "capDays": "cap_days",
    "capQty": "cap_qty",
}


def params_from_demo(demo: dict[str, int]) -> OverviewParams:
    return OverviewParams(
        **{field: demo[key] for key, field in DEMO_KEY_MAP.items() if key in demo}
    )
