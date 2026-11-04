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
            {"products:read", "products:export"} if method == "POST" else {"products:read"}
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
