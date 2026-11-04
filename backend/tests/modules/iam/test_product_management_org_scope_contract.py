"""Product Management must filter all reviewed read models by audited owner UID."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY
from app.modules.product_management.repository import ProductManagementRepository
from app.modules.product_management.router import require_product_management_org_scope


def _session(owner_refs=None):
    session = MagicMock()
    session.info = (
        {} if owner_refs is None else {ORG_OWNER_SCOPE_SESSION_KEY: frozenset(owner_refs)}
    )
    return session


def test_product_list_and_summary_sql_uses_owner_uid() -> None:
    repository = ProductManagementRepository(_session({"uid-verified"}))
    statement = repository._filtered_projection(
        account_refs=frozenset({"SHOP1"}),
        sku=None,
        sku_batch=(),
        product_name=None,
        category=None,
        internal_tag=None,
        product_grade=None,
        calculation_status=None,
        org_owner_refs=repository.org_owner_refs,
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "owner_uid IN ('uid-verified')" in sql
    assert "source_account_ref IN ('SHOP1')" in sql


@pytest.mark.parametrize(
    ("method", "path", "permitted"),
    [
        ("GET", "/api/product-management/skus", True),
        ("GET", "/api/product-management/skus/summary", True),
        ("GET", "/api/product-management/skus/export", True),
        ("GET", "/api/product-management/skus/00000000-0000-0000-0000-000000000001", True),
        (
            "GET",
            "/api/product-management/skus/00000000-0000-0000-0000-000000000001/pricing-breakdown",
            True,
        ),
        ("GET", "/api/product-management/options", True),
        ("GET", "/api/product-management/pricing-rules", False),
        ("POST", "/api/product-management/skus/export", True),
    ],
)
def test_product_routes_fail_closed_when_scoped(method: str, path: str, permitted: bool) -> None:
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    principal = Principal(
        user_id="8",
        permissions=frozenset(
            {"products:read", "products:export"}
            if path == "/api/product-management/skus/export"
            else {"products:read"}
        ),
    )
    session = _session()
    with patch(
        "app.modules.product_management.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-verified"}),
    ):
        if permitted:
            require_product_management_org_scope(request, principal, session)
            assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-verified"})
        else:
            with pytest.raises(ApiError) as error:
                require_product_management_org_scope(request, principal, session)
            assert error.value.status_code == 403
            assert ORG_OWNER_SCOPE_SESSION_KEY not in session.info


def test_read_grant_does_not_allow_product_export() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/product-management/skus/export",
            "headers": [],
        }
    )
    principal = Principal(user_id="8", permissions=frozenset({"products:read"}))
    session = _session()
    with patch("app.modules.product_management.router.resolve_business_owner_refs") as resolver:
        with pytest.raises(ApiError) as error:
            require_product_management_org_scope(request, principal, session)
    assert error.value.status_code == 403
    resolver.assert_not_called()


def test_account_owner_pairs_apply_to_product_list_summary_and_export_sql() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({
            ("SHOP1", "shared-uid"),
        }),
    }
    repository = ProductManagementRepository(session)
    statement = repository._filtered_projection(
        account_refs=frozenset({"SHOP1", "SHOP2"}),
        sku=None,
        sku_batch=(),
        product_name=None,
        category=None,
        internal_tag=None,
        product_grade=None,
        calculation_status=None,
        account_owner_pairs=repository.account_owner_pairs,
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "('SHOP1', 'shared-uid')" in sql
    assert "dwd_lingxing_sku_identity_index.source_account_ref" in sql
    assert "owner_uid" in sql


def test_account_owner_pairs_filter_product_facets_by_exact_account() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({("SHOP1", "shared-uid")}),
    }
    repo = ProductManagementRepository(session)
    for query in (repo.list_owner_options, repo.list_developer_options, repo.list_source_tag_options):
        session.execute.return_value.all.return_value = []
        query(frozenset({"SHOP1", "SHOP2"}))
        sql = str(session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        ))
        assert "('SHOP1', 'shared-uid')" in sql


def test_product_router_prefers_reviewed_account_owner_pair_over_legacy_uid() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/product-management/skus",
        "headers": [],
    })
    session = _session()
    principal = Principal(user_id="8", permissions=frozenset({"products:read"}))
    with (
        patch(
            "app.modules.product_management.router.resolve_business_account_owner_pairs",
            return_value=frozenset({("SHOP1", "shared-uid")}),
        ),
        patch("app.modules.product_management.router.resolve_business_owner_refs") as legacy,
    ):
        require_product_management_org_scope(request, principal, session)
    legacy.assert_not_called()
    assert session.info[ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY] == frozenset({
        ("SHOP1", "shared-uid")
    })
