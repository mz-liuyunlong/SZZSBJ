"""Organization scope authorization obeys wildcard-aware permission helpers."""

import pytest

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import authorized_department_ids


def test_organization_scope_allows_super_admin_without_query() -> None:
    class NoDbCalls:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("super admin must not need scope query")

    assert authorized_department_ids(
        NoDbCalls(),
        Principal(user_id="1", permissions=frozenset({"*"})),
    ) is None


def test_organization_scope_rejects_unknown_principal() -> None:
    with pytest.raises(ApiError) as error:
        authorized_department_ids(
            None,
            Principal(user_id="unrecognized", permissions=frozenset()),
        )
    assert error.value.status_code == 403
