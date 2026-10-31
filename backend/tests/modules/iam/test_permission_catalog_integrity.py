"""Prevent regressions in newly registered IAM page and action metadata."""

from app.modules.iam.permission_catalog_v2 import (
    PERMISSION_DEFINITIONS,
    PERMISSION_KEYS,
)


def test_permission_catalog_keys_are_unique_and_children_have_pages() -> None:
    keys = [item.permission_key for item in PERMISSION_DEFINITIONS]
    assert len(keys) == len(set(keys))
    pages = {item.page_key for item in PERMISSION_DEFINITIONS if item.permission_type == "page"}
    for item in PERMISSION_DEFINITIONS:
        assert item.permission_key
        assert item.page_key in pages
        assert item.permission_type in {"page", "action", "field"}
        assert item.risk_level in {"normal", "high"}


def test_organization_and_walmart_remote_are_registered() -> None:
    assert "page:settings:organization:view" in PERMISSION_KEYS
    assert "page:data-center:walmart-remote:view" in PERMISSION_KEYS
    assert "action:data-center:walmart-remote:execute" in PERMISSION_KEYS


def test_wfs_case_actions_are_assignable() -> None:
    for action in (
        "follow",
        "archive-request",
        "archive-review",
        "mark-recovered",
    ):
        assert f"action:warehouse:wfs-fee-alert:{action}" in PERMISSION_KEYS
