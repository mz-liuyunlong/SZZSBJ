from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_migration() -> ModuleType:
    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "20260923_0019_after_sales_reason_classification.py"
    )
    spec = importlib.util.spec_from_file_location(
        "after_sales_reason_classification_0019", migration
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_walmart_v1_seed_covers_current_exact_pairs() -> None:
    migration = _load_migration()
    exact_rules = migration.EXACT_RULES
    exact_descriptions = migration.EXACT_DESCRIPTION_RULES

    assert len(exact_rules) == 26
    assert len(exact_descriptions) == 25
    assert all(raw_code == raw_code.upper() for raw_code, *_ in exact_rules)

    known_pairs = {(raw_code, description) for raw_code, description, *_ in exact_rules}
    assert ("DEFECTIVE", "Defective/Broken") in known_pairs
    assert ("DEFECTIVE", "Missing parts or instructions") in known_pairs
    assert ("INCORRECT_ITEM", "Incorrect item received") in known_pairs
    assert ("INCORRECT_ITEM", "Missing Items from Box") in known_pairs
    assert ("OTHER", "Shipping box damaged") in known_pairs
    assert ("SHIPPING_BOX_DAMAGED", "Shipping box damaged") in known_pairs


def test_other_has_no_unsafe_code_default() -> None:
    migration = _load_migration()
    code_defaults = {row[0] for row in migration.CODE_DEFAULTS}
    assert "OTHER" not in code_defaults


def test_every_seed_rule_references_existing_dictionaries() -> None:
    migration = _load_migration()
    reason_codes = {row[0] for row in migration.REASONS}
    responsibility_codes = {row[0] for row in migration.RESPONSIBILITIES}

    for _, _, reason_code, responsibility_code, _ in migration.EXACT_RULES:
        assert reason_code in reason_codes
        assert responsibility_code in responsibility_codes

    for _, reason_code, responsibility_code, _ in migration.CODE_DEFAULTS:
        assert reason_code in reason_codes
        assert responsibility_code in responsibility_codes
