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


def test_org_owner_scope_disallows_profit_aggregation() -> None:
    repository = OrderProfitRepository(_session({"uid-reviewed"}))
    with pytest.raises(PermissionError, match="not yet audited"):
        repository._filtered_statement(
            account_refs=frozenset({"A1"}),
            start_date=None,
            end_date=None,
            store_id=None,
            search_field="sku",
            keyword="",
        )


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
    principal = Principal(user_id="5", permissions=frozenset({"products:read"}))
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
    principal = Principal(user_id="5", permissions=frozenset({"products:read"}))
    session = _session({"stale"})
    with patch(
        "app.modules.data_pages.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-reviewed"}),
    ):
        require_data_page_org_scope(request, principal, session)
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-reviewed"})


def test_unscoped_request_clears_stale_scope() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sales/daily-sales",
            "headers": [],
        }
    )
    principal = Principal(user_id="5", permissions=frozenset({"products:read"}))
    session = _session({"stale"})
    with patch("app.modules.data_pages.router.resolve_business_owner_refs", return_value=None):
        require_data_page_org_scope(request, principal, session)
    assert ORG_OWNER_SCOPE_SESSION_KEY not in session.info
