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


def test_runtime_api_and_field_permissions_are_discovered_without_grants() -> None:
    from app.core.auth import Principal
    from app.core.permission_policy_v2 import permission_for_request
    from app.core.permissions import has_permission
    from app.modules.iam.permission_catalog_v2 import (
        all_permission_definitions,
        register_runtime_permission_key,
    )

    action_key = permission_for_request(
        "POST", "/api/listings/tags", "page:products:listing-management:view"
    )
    principal = Principal(user_id="42", permissions=frozenset())
    assert not has_permission(principal, "action:ads:campaigns:pause")
    action = register_runtime_permission_key("action:ads:campaigns:pause")
    field = register_runtime_permission_key("field:finance:profit-center:net-profit")
    assert action_key == "action:products:listing-management:manage-tags"
    assert action is not None and action.risk_level == "high"
    assert field is not None and field.risk_level == "high"
    keys = {item.permission_key for item in all_permission_definitions()}
    assert action.permission_key in keys
    assert field.permission_key in keys


def test_wfs_case_actions_are_assignable() -> None:
    for action in (
        "follow",
        "archive-request",
        "archive-review",
        "mark-recovered",
    ):
        assert f"action:warehouse:wfs-fee-alert:{action}" in PERMISSION_KEYS


def test_new_page_and_its_action_are_discovered_together_without_grants() -> None:
    from app.core.auth import Principal
    from app.core.permissions import has_permission
    from app.modules.iam.permission_catalog_v2 import (
        all_permission_definitions,
        register_runtime_permission_key,
    )

    action_key = "action:operations:future-task-board:approve"
    action = register_runtime_permission_key(action_key)
    assert action is not None
    assert action.permission_type == "action"
    pages = {
        item.permission_key: item
        for item in all_permission_definitions()
        if item.page_key == "operations_future_task_board"
    }
    assert set(pages) == {
        "page:operations:future-task-board:view",
        action_key,
    }
    assert all(item.risk_level == "high" for item in pages.values())
    assert not has_permission(Principal(user_id="20", permissions=frozenset()), action_key)


def test_runtime_catalog_ignores_invalid_or_unknown_module_declarations() -> None:
    from app.modules.iam.permission_catalog_v2 import register_runtime_permission_key

    for key in (
        "action:unknown-module:future-page:approve",
        "page:operations:future-page:export",
        "action:operations:future_page:approve",
        "field:operations:future-page:private name",
    ):
        assert register_runtime_permission_key(key) is None
