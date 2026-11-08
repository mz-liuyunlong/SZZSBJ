"""A generated navigation contract supplies role-managed page definitions."""

import json
from pathlib import Path

from app.modules.iam.permission_catalog_v2 import ACTIONS, PERMISSION_DEFINITIONS, PERMISSION_KEYS


def test_generated_navigation_pages_are_grantable_in_role_management() -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[3] / "app/modules/iam/navigation_permissions.json")
        .read_text(encoding="utf-8")
    )
    registered = {
        item.permission_key
        for item in PERMISSION_DEFINITIONS
        if item.permission_type == "page"
    }
    menu_keys = {
        page["permission_key"]
        for module in manifest["modules"]
        for page in module["pages"]
    }
    assert menu_keys <= registered
    assert "page:finance:fx-rates:view" in menu_keys


def test_sensitive_operations_are_assignable_only_as_high_risk() -> None:
    expected = {
        "action:finance:cash-flow:import",
        "action:finance:cash-flow:void-import",
        "action:finance:cash-flow:edit-journal",
        "action:finance:cash-flow:sync-approvals",
        "action:finance:cash-flow:manage-accounts",
        "action:finance:fx-rates:sync",
        "action:settings:business-config:manage-connectors",
        "action:settings:business-config:manage-decodo",
        "action:settings:business-config:manage-notifications",
    }
    high_risk = {
        item.permission_key for item in PERMISSION_DEFINITIONS if item.risk_level == "high"
    }
    assert expected <= high_risk
    assert expected <= PERMISSION_KEYS
    assert len(ACTIONS) > 0
