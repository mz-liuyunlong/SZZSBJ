"""Legacy qualified dimensions enforce authorization before aggregates or exports."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.data_pages.repository import (
    DailySalesRepository,
    ListingManagementRepository,
    OrderProfitRepository,
)
from app.modules.data_pages.router import require_data_page_org_scope
from app.modules.iam.explicit_item_scope import (
    PRODUCT_SCOPE_SESSION_KEY,
    SKU_SCOPE_SESSION_KEY,
    resolve_explicit_identity_scope,
)
from app.modules.iam.explicit_owner_scope import (
    OWNER_SCOPE_SESSION_KEY,
    resolve_explicit_owner_scope,
)


def _session(scopes=None):
    session = MagicMock()
    session.info = scopes or {}
    return session


def _sql(statement):
    return str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))


def _sales_statement(session):
    return DailySalesRepository(session)._filtered_statement(
        account_refs=frozenset({"A1", "A2"}),
        start_date=None, end_date=None, platform=None,
        store_id=None, owner_ref=None, search_field="sku", keyword="",
    )


def _listing_statement(session):
    return ListingManagementRepository(session)._filtered_listing_statement(
        account_refs=frozenset({"A1", "A2"}),
        store_id=None, owner_ref=None, product_type=None, status=None,
        tag=None, archive_status=None, summary_filter="total",
        search_field="sku", keyword="", batch_values="",
    )


@pytest.mark.parametrize(("key", "identity_column"), [
    (SKU_SCOPE_SESSION_KEY, "local_sku"),
    (PRODUCT_SCOPE_SESSION_KEY, "item_id"),
    (OWNER_SCOPE_SESSION_KEY, "owner_ref"),
])
def test_daily_sales_scopes_are_account_qualified(key, identity_column):
    session = _session({key: frozenset({("A1", "same-id")})})
    sql = _sql(_sales_statement(session))
    assert "('A1', 'same-id')" in sql
    assert identity_column in sql
    assert "source_account_ref" in sql


@pytest.mark.parametrize(("key", "identity_column"), [
    (SKU_SCOPE_SESSION_KEY, "local_sku"),
    (PRODUCT_SCOPE_SESSION_KEY, "item_id"),
    (OWNER_SCOPE_SESSION_KEY, "owner_uid"),
])
def test_listing_and_facets_use_account_qualified_scope(key, identity_column):
    session = _session({key: frozenset({("A1", "same-id")})})
    sql = _sql(_listing_statement(session))
    assert "('A1', 'same-id')" in sql
    assert identity_column in sql
    assert "source_account_ref" in sql

    session.execute.return_value.mappings.return_value.one.return_value = {
        "active_count": 0, "archived_count": 0
    }
    ListingManagementRepository(session).archive_status_filter_options(
        frozenset({"A1", "A2"})
    )
    facet_sql = _sql(session.execute.call_args.args[0])
    assert "('A1', 'same-id')" in facet_sql


@pytest.mark.parametrize("key", [SKU_SCOPE_SESSION_KEY, OWNER_SCOPE_SESSION_KEY])
def test_profit_requires_complete_authorized_sku_source(key):
    session = _session({key: frozenset({("A1", "same-id")})})
    statement = OrderProfitRepository(session)._filtered_statement(
        account_refs=frozenset({"A1", "A2"}),
        start_date=None, end_date=None, store_id=None,
        search_field="sku", keyword="",
    )
    sql = _sql(statement)
    assert "('A1', 'same-id')" in sql
    assert "IS NOT DISTINCT FROM" in sql
    assert "jsonb_agg" in sql


@pytest.mark.parametrize(("scope_type", "resolver"), [
    ("sku", resolve_explicit_identity_scope),
    ("product", resolve_explicit_identity_scope),
    ("owner", resolve_explicit_owner_scope),
])
def test_unqualified_legacy_grants_deny_instead_of_widening(scope_type, resolver):
    session = _session()
    principal = Principal(user_id="8", permissions=frozenset({"products:read"}))
    with patch(
        "app.modules.iam.rbac_repository.RbacRepository.resolve_user_data_scope",
        return_value={"shared-uid"},
    ):
        with pytest.raises(ApiError) as denied:
            if scope_type == "owner":
                resolver(session, principal)
            else:
                resolver(session, principal, scope_type=scope_type)
    assert denied.value.status_code == 403


def test_data_page_rejects_restricted_unsafe_listing_mutations():
    request = Request({
        "type": "http", "path": "/api/listings/walmart/synthetic/archive",
        "method": "POST", "headers": [],
    })
    principal = Principal(user_id="8", permissions=frozenset({
        "products:read", "action:products:listing-management:archive",
    }))
    session = _session()
    with (
        patch("app.modules.data_pages.router.resolve_business_account_owner_pairs", return_value=None),
        patch("app.modules.data_pages.router.resolve_business_owner_refs", return_value=None),
        patch("app.modules.data_pages.router.resolve_account_store_scope", return_value=None),
        patch("app.modules.data_pages.router.resolve_explicit_owner_scope", return_value=None),
        patch("app.modules.data_pages.router.resolve_explicit_identity_scope", side_effect=[
            frozenset({("A1", "SKU1")}), None,
        ]),
    ):
        with pytest.raises(ApiError) as denied:
            require_data_page_org_scope(request, principal, session)
    assert denied.value.status_code == 403
