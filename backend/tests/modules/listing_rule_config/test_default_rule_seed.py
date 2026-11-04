"""The frozen database seed must match the rule engine's V1 defaults."""

import importlib.util
from pathlib import Path

from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


def test_default_rule_seed_matches_engine_defaults() -> None:
    migration_path = (
        Path(__file__).parents[3] / "alembic/versions/20261104_0073_listing_grade_default_rule.py"
    )
    spec = importlib.util.spec_from_file_location("listing_default_seed", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_RULES == ListingGradeRuleConfig().model_dump(mode="json")
