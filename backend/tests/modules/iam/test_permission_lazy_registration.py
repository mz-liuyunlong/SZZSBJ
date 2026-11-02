"""Declared permissions are discoverable but never granted without authorization."""

from unittest.mock import MagicMock

import pytest

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS
from app.modules.iam.rbac_service import RbacService


def _service():
    service = RbacService(MagicMock())
    service.repository.disabled_declared_permission_keys = MagicMock(return_value=set())
    return service


def _row(item):
    return {
        "permission_key": item.permission_key,
        "name": item.name,
        "description": item.description,
        "permission_type": item.permission_type,
        "module_key": item.module_key,
        "page_key": item.page_key,
        "action_key": item.action_key,
        "field_key": item.field_key,
        "risk_level": item.risk_level,
        "sort_order": item.sort_order,
    }


def test_catalog_displays_declared_keys_without_writing() -> None:
    service = _service()
    sample = next(x for x in PERMISSION_DEFINITIONS if x.permission_type == "page")
    service.repository.list_permission_catalog_rows = MagicMock(return_value=[_row(sample)])
    catalog = service.permission_catalog()
    page_keys = {page.permission_key for module in catalog.modules for page in module.pages}
    assert "page:settings:organization:view" in page_keys
    service.repository.register_declared_permissions.assert_not_called()


def test_missing_declared_key_validation_is_read_only() -> None:
    service = _service()
    key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    assert service._validated_permission_keys([key]) == (key,)
    service.repository.register_declared_permissions.assert_not_called()


def test_new_key_is_registered_after_authorized_grant() -> None:
    service = _service()
    key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(side_effect=[set(), set(), {key}])
    authorized = Principal(user_id="1", permissions=frozenset({"*"}))
    service._assert_actor_can_grant(authorized, (key,))
    service._register_missing_permissions((key,))
    service.repository.register_declared_permissions.assert_called_once_with({key})


def test_disabled_key_is_not_grantable_or_registered() -> None:
    service = _service()
    key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    service.repository.disabled_declared_permission_keys = MagicMock(return_value={key})
    with pytest.raises(ApiError) as error:
        service._validated_permission_keys([key])
    assert error.value.status_code == 422
    service.repository.register_declared_permissions.assert_not_called()


def test_nonadmin_cannot_grant_unregistered_high_risk_key() -> None:
    service = _service()
    key = next(item.permission_key for item in PERMISSION_DEFINITIONS if item.risk_level == "high")
    service.repository.high_risk_permission_keys = MagicMock(return_value=set())
    ordinary = Principal(user_id="2", permissions=frozenset({key}))
    with pytest.raises(ApiError) as error:
        service._assert_actor_can_grant(ordinary, (key,))
    assert error.value.status_code == 403
    service.repository.register_declared_permissions.assert_not_called()


def test_unrecognized_key_is_never_registered() -> None:
    service = _service()
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    with pytest.raises(ApiError) as error:
        service._validated_permission_keys(["action:fake:unknown:execute"])
    assert error.value.status_code == 422
    service.repository.register_declared_permissions.assert_not_called()


def test_failed_insert_does_not_allow_grant() -> None:
    service = _service()
    key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    with pytest.raises(ApiError) as error:
        service._register_missing_permissions((key,))
    assert error.value.status_code == 422
