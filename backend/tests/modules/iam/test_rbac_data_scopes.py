from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.iam.rbac_schemas import (
    DataScopeEntryWrite,
    UserDataScopeRead,
    UserDataScopeUpdateRequest,
)
from app.modules.iam.rbac_service import AuditContext, RbacService


def _service() -> tuple[RbacService, MagicMock]:
    service = RbacService(MagicMock(spec=Session))
    repository = MagicMock()
    repository.high_risk_permission_keys.return_value = set()
    service.repository = repository
    return service, repository


def test_user_scope_read_explains_user_override_and_role_fallback() -> None:
    service, repository = _service()
    repository.get_user.return_value = {"id": 41, "is_super_admin": False}
    repository.get_user_data_scopes.return_value = [
        {"scope_type": "source_account", "scope_value": "account-a"},
    ]
    repository.get_user_role_data_scopes.return_value = [
        {"scope_type": "source_account", "scope_value": "account-b"},
        {"scope_type": "store", "scope_value": "store-a"},
    ]

    result = service.user_data_scopes(41)

    assert [
        (item.scope_type, item.scope_value, item.source) for item in result.effective_items
    ] == [
        ("source_account", "account-a", "user"),
        ("store", "store-a", "role"),
    ]


def test_non_super_admin_cannot_grant_wildcard_scope() -> None:
    service, _repository = _service()
    actor = Principal(
        user_id="7",
        permissions=frozenset({"action:settings:user-management:configure-data-scope"}),
    )

    with pytest.raises(ApiError) as exc:
        service._assert_actor_can_grant_scopes(actor, (("source_account", "*"),))

    assert exc.value.status_code == 403


def test_non_super_admin_cannot_grant_scope_outside_own_effective_scope() -> None:
    service, repository = _service()
    repository.list_configured_source_account_refs.return_value = {"account-b"}
    repository.resolve_user_data_scope.return_value = {"account-a"}
    actor = Principal(
        user_id="7",
        permissions=frozenset({"action:settings:user-management:configure-data-scope"}),
    )

    with pytest.raises(ApiError) as exc:
        service._assert_actor_can_grant_scopes(actor, (("source_account", "account-b"),))

    assert exc.value.status_code == 403


def test_non_super_admin_cannot_read_protected_super_admin_scope() -> None:
    service, repository = _service()
    repository.get_user.return_value = {"id": 1, "is_super_admin": True}
    actor = Principal(
        user_id="7",
        permissions=frozenset({"action:settings:user-management:configure-data-scope"}),
    )

    with pytest.raises(ApiError) as exc:
        service.user_data_scopes(1, actor=actor)

    assert exc.value.status_code == 403


def test_super_admin_can_replace_user_scope_and_audit_change() -> None:
    service, repository = _service()
    repository.list_configured_source_account_refs.return_value = {"account-a"}
    repository.get_user.return_value = {"id": 41, "is_super_admin": False}
    repository.get_user_data_scopes.side_effect = [
        [],
        [{"scope_type": "source_account", "scope_value": "account-a"}],
    ]
    repository.get_user_role_data_scopes.return_value = []

    result = service.update_user_data_scopes(
        actor=Principal(user_id="1", permissions=frozenset({"*"})),
        user_id=41,
        payload=UserDataScopeUpdateRequest(
            items=[DataScopeEntryWrite(scope_type="source_account", scope_value="account-a")]
        ),
        audit=AuditContext(request_id="request-1", request_ip=None, user_agent=None),
    )

    repository.set_user_data_scopes.assert_called_once_with(
        user_id=41,
        scopes=(("source_account", "account-a"),),
    )
    repository.append_audit_event.assert_called_once()
    assert result.items[0].scope_value == "account-a"


def test_super_admin_cannot_grant_unregistered_source_account() -> None:
    service, repository = _service()
    repository.list_configured_source_account_refs.return_value = {"account-a"}
    actor = Principal(user_id="1", permissions=frozenset({"*"}))

    with pytest.raises(ApiError) as exc:
        service._assert_actor_can_grant_scopes(
            actor,
            (("source_account", "unknown-account"),),
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"


def test_user_scope_api_requires_page_and_action(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="7",
        permissions=frozenset({"action:settings:user-management:configure-data-scope"}),
    )
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(app).get("/api/settings/rbac/users/41/data-scopes")
    assert response.status_code == 403

    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="7",
        permissions=frozenset(
            {
                "page:settings:user-management:view",
                "action:settings:user-management:configure-data-scope",
            }
        ),
    )
    monkeypatch.setattr(
        RbacService,
        "user_data_scopes",
        lambda *_args, **_kwargs: UserDataScopeRead(user_id=41),
    )
    response = TestClient(app).get("/api/settings/rbac/users/41/data-scopes")
    assert response.status_code == 200


def test_role_assignment_rejects_scope_outside_actor_even_with_target_override() -> None:
    service, repository = _service()
    repository.permissions_for_roles.return_value = {"page:synthetic:view"}
    repository.data_scopes_for_roles.return_value = {("source_account", "account-b")}
    repository.resolve_user_data_scope.return_value = {"account-a"}
    actor = Principal(user_id="7", permissions=frozenset({"page:synthetic:view"}))

    with pytest.raises(ApiError) as exc:
        service._assert_actor_can_assign_roles(actor, ("scoped-role",))

    assert exc.value.status_code == 403


def test_role_assignment_checks_combined_and_wildcard_scopes() -> None:
    service, repository = _service()
    repository.permissions_for_roles.return_value = {"page:synthetic:view"}
    repository.resolve_user_data_scope.return_value = {"account-a"}
    actor = Principal(user_id="7", permissions=frozenset({"page:synthetic:view"}))

    repository.data_scopes_for_roles.return_value = {
        ("source_account", "account-a"),
        ("source_account", "account-b"),
    }
    with pytest.raises(ApiError):
        service._assert_actor_can_assign_roles(actor, ("role-a", "role-b"))

    repository.data_scopes_for_roles.return_value = {("source_account", "*")}
    with pytest.raises(ApiError):
        service._assert_actor_can_assign_roles(actor, ("wildcard-role",))


def test_non_super_admin_cannot_assign_role_with_high_risk_permission() -> None:
    service, repository = _service()
    repository.permissions_for_roles.return_value = {"action:synthetic:high-risk"}
    repository.high_risk_permission_keys.return_value = {"action:synthetic:high-risk"}
    actor = Principal(
        user_id="7",
        permissions=frozenset({"action:synthetic:high-risk"}),
    )

    with pytest.raises(ApiError) as exc:
        service._assert_actor_can_assign_roles(actor, ("high-risk-role",))

    assert exc.value.status_code == 403


def test_role_options_include_data_scope_assignability() -> None:
    service, repository = _service()
    repository.list_role_options.return_value = [
        {
            "role_key": "account-a-role",
            "name": "Account A",
            "description": None,
            "is_system": False,
        },
        {
            "role_key": "account-b-role",
            "name": "Account B",
            "description": None,
            "is_system": False,
        },
    ]
    repository.permissions_for_roles.return_value = {"page:synthetic:view"}
    repository.data_scopes_for_roles.side_effect = [
        {("source_account", "account-a")},
        {("source_account", "account-b")},
    ]
    repository.resolve_user_data_scope.return_value = {"account-a"}

    result = service.user_role_options(
        Principal(user_id="7", permissions=frozenset({"page:synthetic:view"}))
    )

    assert [item.assignable for item in result] == [True, False]


def test_super_admin_can_assign_role_with_wildcard_scope() -> None:
    service, repository = _service()
    service._assert_actor_can_assign_roles(
        Principal(user_id="1", permissions=frozenset({"*"})),
        ("admin",),
    )
    repository.permissions_for_roles.assert_not_called()
