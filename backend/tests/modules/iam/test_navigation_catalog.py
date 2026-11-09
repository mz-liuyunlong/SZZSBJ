"""A generated navigation contract supplies role-managed page definitions."""

import json
from pathlib import Path

from app.modules.iam.permission_catalog_v2 import ACTIONS, PERMISSION_DEFINITIONS, PERMISSION_KEYS


def test_generated_navigation_pages_are_grantable_in_role_management() -> None:
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[3] / "app/modules/iam/navigation_permissions.json"
        ).read_text(encoding="utf-8")
    )
    registered = {
        item.permission_key for item in PERMISSION_DEFINITIONS if item.permission_type == "page"
    }
    menu_keys = {
        page["permission_key"] for module in manifest["modules"] for page in module["pages"]
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


def test_role_catalog_exposes_missing_permissions_without_database_write(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from app.modules.iam.rbac_service import RbacService

    service = object.__new__(RbacService)
    service.repository = MagicMock()
    service.repository.list_permission_catalog_rows.return_value = []
    catalog = service.permission_catalog()
    actual = {
        page.permission_key
        for module in catalog.modules
        for page in module.pages
    }
    assert "page:finance:fx-rates:view" in actual
    assert "page:finance:cash-flow:view" in actual
    service.repository.register_permission_definitions.assert_not_called()


def test_role_save_registers_only_requested_known_permissions() -> None:
    from unittest.mock import MagicMock

    from app.modules.iam.rbac_service import RbacService

    service = object.__new__(RbacService)
    service.repository = MagicMock()
    # The key does not yet exist, then appears after registration.
    service.repository.existing_permission_keys.side_effect = [
        set(), {"page:finance:fx-rates:view"}
    ]
    result = service._validated_permission_keys(["page:finance:fx-rates:view"])
    assert result == ("page:finance:fx-rates:view",)
    definitions = service.repository.register_permission_definitions.call_args.args[0]
    assert [entry.permission_key for entry in definitions] == [
        "page:finance:fx-rates:view"
    ]
