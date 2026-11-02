"""New permissions are discoverable before persistence and never silently granted."""

from unittest.mock import MagicMock

import pytest

from app.core.api import ApiError
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS
from app.modules.iam.rbac_service import RbacService


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
    service = RbacService(MagicMock())
    sample = next(x for x in PERMISSION_DEFINITIONS if x.permission_type == "page")
    service.repository.list_permission_catalog_rows = MagicMock(return_value=[_row(sample)])
    service.repository.disabled_declared_permission_keys = MagicMock(return_value=set())
    catalog = service.permission_catalog()
    page_keys = {
        page.permission_key for module in catalog.modules for page in module.pages
    }
    assert "page:settings:organization:view" in page_keys
    service.repository.register_declared_permissions.assert_not_called()


def test_new_declared_key_is_registered_only_on_role_save() -> None:
    service = RbacService(MagicMock())
    permission_key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(
        side_effect=[set(), {permission_key}]
    )
    validated = service._validated_permission_keys([permission_key])
    assert validated == (permission_key,)
    service.repository.register_declared_permissions.assert_called_once_with({permission_key})


def test_disabled_key_cannot_be_reenabled_during_role_save() -> None:
    service = RbacService(MagicMock())
    key = "page:settings:organization:view"
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    with pytest.raises(ApiError) as error:
        service._validated_permission_keys([key])
    assert error.value.status_code == 422


def test_unrecognized_key_is_never_registered() -> None:
    service = RbacService(MagicMock())
    service.repository.existing_permission_keys = MagicMock(return_value=set())
    with pytest.raises(ApiError) as error:
        service._validated_permission_keys(["action:fake:unknown:execute"])
    assert error.value.status_code == 422
    service.repository.register_declared_permissions.assert_not_called()
