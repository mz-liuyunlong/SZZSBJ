"""Organization owner scopes must govern SQL and every DATA-PAGES endpoint."""

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
from app.modules.data_pages.router import (
    _ORG_SCOPED_READS,
    require_data_page_org_scope,
)
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY


def _session(owners=None):
    session = MagicMock()
    session.info = {} if owners is None else {ORG_OWNER_SCOPE_SESSION_KEY: frozenset(owners)}
    return session


def _sql(statement):
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_daily_sales_sql_requires_granted_owner() -> None:
    repository = DailySalesRepository(_session({"uid-reviewed"}))
    statement = repository._filtered_statement(
        account_refs=frozenset({"A1"}),
        start_date=None,
        end_date=None,
        platform=None,
        store_id=None,
        owner_ref=None,
        search_field="sku",
        keyword="",
    )
    sql = _sql(statement)
    assert "owner_ref IN ('uid-reviewed')" in sql
    assert "source_account_ref IN ('A1')" in sql


def test_listing_sql_requires_verified_owner_or_owner_uid_fallback() -> None:
    repository = ListingManagementRepository(_session({"uid-reviewed"}))
    statement = repository._filtered_listing_statement(
        account_refs=frozenset({"A1"}),
        store_id=None,
        owner_ref="",
        product_type="",
        status="",
        tag="",
        archive_status="",
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    sql = _sql(statement)
    assert "owner_uid IN ('uid-reviewed')" in sql
    assert "owner_uid IS NULL" in sql
    assert "owner_ref IN ('uid-reviewed')" in sql


def test_listing_archive_filter_options_uses_the_same_owner_scope() -> None:
    session = _session({"uid-reviewed"})
    session.execute.return_value.mappings.return_value.one.return_value = {
        "active_count": 1,
        "archived_count": 2,
    }
    repository = ListingManagementRepository(session)
    repository.archive_status_filter_options(frozenset({"A1"}))
    statement = session.execute.call_args.args[0]
    sql = _sql(statement)
    assert "owner_uid IN ('uid-reviewed')" in sql
    assert "owner_ref IN ('uid-reviewed')" in sql
    assert "source_account_ref IN ('A1')" in sql


def test_org_scope_permission_is_checked_before_scope_resolution() -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/sales/daily-sales", "headers": []}
    )
    principal = Principal(user_id="5", permissions=frozenset())
    session = _session()
    with patch("app.modules.data_pages.router.resolve_business_owner_refs") as resolver:
        with pytest.raises(ApiError) as error:
            require_data_page_org_scope(request, principal, session)
    assert error.value.status_code == 403
    assert error.value.code == "FORBIDDEN"
    resolver.assert_not_called()


def test_org_owner_scope_disallows_profit_aggregation() -> None:
    repository = OrderProfitRepository(_session({"uid-reviewed"}))
    with pytest.raises(ApiError) as error:
        repository._filtered_statement(
            account_refs=frozenset({"A1"}),
            start_date=None,
            end_date=None,
            store_id=None,
            search_field="sku",
            keyword="",
        )
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/listings/walmart/123/archive"),
        ("GET", "/api/sales/order-profit"),
        ("GET", "/api/sales/order-profit/export"),
        ("GET", "/api/listings/tags"),
    ],
)
def test_scoped_unreviewed_routes_fail_closed(method: str, path: str) -> None:
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    principal = Principal(
        user_id="5", permissions=frozenset({"products:read", "sales:daily-sales:read"})
    )
    session = _session()
    with patch(
        "app.modules.data_pages.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-reviewed"}),
    ):
        with pytest.raises(ApiError) as error:
            require_data_page_org_scope(request, principal, session)
    assert error.value.status_code == 403
    assert ORG_OWNER_SCOPE_SESSION_KEY not in session.info


@pytest.mark.parametrize("path", sorted(_ORG_SCOPED_READS))
def test_scoped_reviewed_routes_install_owner_filter(path: str) -> None:
    request = Request({"type": "http", "method": "GET", "path": path, "headers": []})
    permissions = {"products:read", "sales:daily-sales:read"}
    if path == "/api/sales/daily-sales/export":
        permissions.add("action:sales:daily-sales:export")
    if path == "/api/listings/walmart/export":
        permissions.add("action:products:listing-management:export")
    principal = Principal(user_id="5", permissions=frozenset(permissions))
    session = _session({"stale"})
    with patch(
        "app.modules.data_pages.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-reviewed"}),
    ):
        require_data_page_org_scope(request, principal, session)
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-reviewed"})


def test_read_permission_cannot_bypass_canonical_export_action() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sales/daily-sales/export",
            "headers": [],
        }
    )
    principal = Principal(user_id="5", permissions=frozenset({"sales:daily-sales:read"}))
    session = _session()
    with patch("app.modules.data_pages.router.resolve_business_owner_refs") as resolver:
        with pytest.raises(ApiError) as error:
            require_data_page_org_scope(request, principal, session)
    assert error.value.status_code == 403
    resolver.assert_not_called()


def test_unscoped_request_clears_stale_scope() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sales/daily-sales",
            "headers": [],
        }
    )
    principal = Principal(user_id="5", permissions=frozenset({"sales:daily-sales:read"}))
    session = _session({"stale"})
    with patch("app.modules.data_pages.router.resolve_business_owner_refs", return_value=None):
        require_data_page_org_scope(request, principal, session)
    assert ORG_OWNER_SCOPE_SESSION_KEY not in session.info


def test_daily_sales_store_grant_is_account_qualified_across_all_aggregations() -> None:
    """Daily Sales detail, summary, refunds, facets and export share one filter."""
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = _session({"owner-approved"})
    session.info[STORE_SCOPE_SESSION_KEY] = frozenset({("A1", "store-01")})
    repository = DailySalesRepository(session)
    statement = repository._filtered_statement(
        account_refs=frozenset({"A1", "A2"}),
        start_date=None,
        end_date=None,
        platform=None,
        store_id=None,
        owner_ref=None,
        search_field="sku",
        keyword="",
    )
    sql = _sql(statement)
    assert "source_account_ref IN ('A1', 'A2')" in sql
    assert "store_id" in sql
    assert "('A1', 'store-01')" in sql
    assert "owner_ref IN ('owner-approved')" in sql


def test_listing_store_grant_applies_before_summary_facets_and_export() -> None:
    """Listing data, summary, filter options and CSV reuse the same SQL."""
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = _session({"owner-approved"})
    session.info[STORE_SCOPE_SESSION_KEY] = frozenset({("A1", "store-01")})
    repository = ListingManagementRepository(session)
    statement = repository._filtered_listing_statement(
        account_refs=frozenset({"A1", "A2"}),
        store_id=None,
        owner_ref=None,
        product_type=None,
        status=None,
        tag=None,
        archive_status=None,
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    sql = _sql(statement)
    assert "('A1', 'store-01')" in sql
    assert "source_account_ref IN ('A1', 'A2')" in sql
    assert "owner_uid IN ('owner-approved')" in sql


@pytest.mark.parametrize(
    "value",
    ["store-01", "A1|", "|store-01", " A1|store-01", "A1| store-01", "A1|store|01"],
)
def test_unqualified_or_malformed_store_grants_fail_closed(value: str) -> None:
    from app.modules.iam.store_scope import parse_account_store

    with pytest.raises(ApiError) as error:
        parse_account_store(value)
    assert error.value.status_code == 403


def test_store_scope_uses_user_override_and_never_trusts_client_filter() -> None:
    from app.modules.iam.store_scope import resolve_account_store_scope

    session = _session()
    with patch(
        "app.modules.iam.store_scope.RbacRepository.resolve_user_data_scope",
        return_value={"A1|store-01", "A2|store-01"},
    ) as resolver:
        stores = resolve_account_store_scope(
            session,
            Principal(user_id="5", permissions=frozenset({"products:read"})),
        )
    assert stores == frozenset({("A1", "store-01"), ("A2", "store-01")})
    resolver.assert_called_once_with(user_id=5, scope_type="store")


def test_store_scope_blocks_unreviewed_listing_mutations_even_with_global_org() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/listings/walmart/synthetic-id/archive",
        "headers": [],
    })
    session = _session()
    with (
        patch("app.modules.data_pages.router.resolve_business_owner_refs", return_value=None),
        patch(
            "app.modules.data_pages.router.resolve_account_store_scope",
            return_value=frozenset({("A1", "store-01")}),
        ),
    ):
        with pytest.raises(ApiError) as error:
            require_data_page_org_scope(
                request,
                Principal(
                    user_id="5",
                    permissions=frozenset({
                        "products:read", "action:products:listing-management:archive"
                    }),
                ),
                session,
            )
    assert error.value.status_code == 403
    assert STORE_SCOPE_SESSION_KEY not in session.info



def test_scoped_order_profit_requires_complete_source_identity_and_sales_reconciliation() -> None:
    """A missing source row must not turn mixed-owner SKU totals into visible profit."""
    from app.modules.data_pages.repository import OrderProfitRepository
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({("A1", "owner-1")})
    }
    repo = OrderProfitRepository(session)
    statement = repo._filtered_statement(
        account_refs=frozenset({"A1", "A2"}),
        start_date=None,
        end_date=None,
        store_id=None,
        search_field="sku",
        keyword="",
    )
    sql = _sql(statement)
    assert "('A1', 'owner-1')" in sql
    assert "mart_daily_sales_item_day" in sql
    assert "jsonb_agg" in sql
    assert "store_ids_json" in sql
    assert "item_ids_json" in sql
    assert "sales_amount" in sql
    assert "sales_qty" in sql
    assert "order_count" in sql
    assert "gross_profit_amount" in sql
    assert "IS NOT DISTINCT FROM" in sql
    assert "EXISTS" in sql


def test_unscoped_order_profit_preserves_legacy_aggregation() -> None:
    from app.modules.data_pages.repository import OrderProfitRepository

    repo = OrderProfitRepository(_session())
    sql = _sql(repo._filtered_statement(
        account_refs=frozenset({"A1"}),
        start_date=None,
        end_date=None,
        store_id=None,
        search_field="sku",
        keyword="",
    ))
    assert "mart_order_profit_sku_day" in sql
    assert "jsonb_agg" not in sql
    assert "mart_daily_sales_item_day" not in sql
