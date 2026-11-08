"""Regression coverage for newly registered RBAC navigation grants."""

from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS, PERMISSION_KEYS

NEW_PAGE_KEYS = {
    "page:finance:settlement-profit:view",
    "page:finance:balance-sheet:view",
    "page:finance:cash-flow:view",
    "page:finance:cost-exception:view",
    "page:finance:settings:view",
    "page:finance:data-import:view",
    "page:pmc:logistics:view",
    "page:data-center:walmart-remote:view",
}


def test_new_navigation_permissions_are_grantable_pages() -> None:
    actual = {
        item.permission_key
        for item in PERMISSION_DEFINITIONS
        if item.permission_type == "page" and item.risk_level == "normal"
    }
    assert NEW_PAGE_KEYS <= actual


def test_finance_fx_rates_stays_super_admin_only() -> None:
    assert "page:finance:fx-rates:view" not in PERMISSION_KEYS
