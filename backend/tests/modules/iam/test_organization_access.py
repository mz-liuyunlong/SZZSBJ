"""Organization scope authorization obeys wildcard-aware permission helpers."""

import pytest

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import authorized_department_ids


def test_organization_scope_allows_super_admin_without_query() -> None:
    class NoDbCalls:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("super admin must not need scope query")

    assert (
        authorized_department_ids(
            NoDbCalls(),
            Principal(user_id="1", permissions=frozenset({"*"})),
        )
        is None
    )


def test_missing_department_grant_requires_own_verified_owner_binding() -> None:
    from unittest.mock import MagicMock, patch

    from app.core.auth import Principal
    from app.modules.iam.organization_access import resolve_business_owner_refs

    session = MagicMock()
    session.execute.return_value.scalars.return_value = ["owner-self"]
    principal = Principal(user_id="42", permissions=frozenset())
    with patch(
        "app.modules.iam.organization_access.RbacRepository.resolve_user_data_scope",
        return_value=set(),
    ):
        owners = resolve_business_owner_refs(session, principal)
    assert owners == frozenset({"owner-self"})
    binding_sql = str(session.execute.call_args_list[0].args[0])
    assert "app_users" in binding_sql
    assert "iam_org_owner_bindings" in binding_sql


def test_missing_department_grant_without_owner_binding_fails_closed() -> None:
    from unittest.mock import MagicMock, patch

    from app.core.auth import Principal
    from app.modules.iam.organization_access import resolve_business_owner_refs

    session = MagicMock()
    session.execute.return_value.scalars.return_value = []
    principal = Principal(user_id="42", permissions=frozenset())
    with patch(
        "app.modules.iam.organization_access.RbacRepository.resolve_user_data_scope",
        return_value=set(),
    ):
        with pytest.raises(ApiError) as error:
            resolve_business_owner_refs(session, principal)
    assert error.value.status_code == 403


def test_reused_owner_uid_is_excluded_from_org_permissions() -> None:
    from unittest.mock import MagicMock

    from app.modules.iam.organization_access import verified_single_account_owner_refs

    session = MagicMock()
    # PostgreSQL will return only UIDs having exactly one nonempty source account.
    session.execute.return_value.scalars.return_value = ["owner-unique"]

    assert verified_single_account_owner_refs(
        session, frozenset({"owner-unique", "owner-reused"})
    ) == frozenset({"owner-unique"})
    query = str(session.execute.call_args.args[0])
    assert "COUNT(DISTINCT source_account_ref) = 1" in query
    assert "bool_and(nullif(btrim(source_account_ref), '') IS NOT NULL)" in query
    assert "mart_daily_sales_item_day" in query
    assert "dws_purchase_board" in query
    assert "mart_listing_management_current" in query


def test_only_ambiguous_owner_uid_denies_access_without_global_fallback() -> None:
    from unittest.mock import MagicMock, patch

    from app.modules.iam.organization_access import resolve_business_owner_refs

    session = MagicMock()
    session.execute.return_value.scalars.return_value = ["owner-reused"]
    with (
        patch(
            "app.modules.iam.organization_access.RbacRepository.resolve_user_data_scope",
            return_value=set(),
        ),
        patch(
            "app.modules.iam.organization_access.verified_single_account_owner_refs",
            return_value=frozenset(),
        ),
    ):
        with pytest.raises(ApiError) as error:
            resolve_business_owner_refs(
                session,
                Principal(user_id="42", permissions=frozenset()),
            )
    assert error.value.code == "DATA_SCOPE_DENIED"
    assert error.value.status_code == 403


def test_organization_scope_rejects_unknown_principal() -> None:
    with pytest.raises(ApiError) as error:
        authorized_department_ids(
            None,
            Principal(user_id="unrecognized", permissions=frozenset()),
        )
    assert error.value.status_code == 403
