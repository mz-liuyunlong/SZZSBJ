"""PMC purchase board enforces Feishu-reviewed owner bounds on SQL."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY
from app.modules.pmc_purchase.repository import PmcPurchaseReadRepository
from app.modules.pmc_purchase.router import require_pmc_purchase_org_scope
from app.modules.pmc_purchase.schemas import BoardListQuery


def test_board_query_is_restricted_by_owner_and_account() -> None:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"owner-approved"})}
    repository = PmcPurchaseReadRepository(session)
    statement = repository._board_select(
        BoardListQuery(), frozenset({"ACCOUNT1"}), __import__("datetime").date(2026, 11, 3)
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "owner_uid IN ('owner-approved')" in sql
    assert "source_account_ref IN ('ACCOUNT1')" in sql


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/api/pmc/purchase/board", True),
        ("GET", "/api/pmc/purchase/board/summary", False),
        ("GET", "/api/pmc/purchase/orders/PO123", False),
        ("GET", "/api/pmc/purchase/plans/pending", False),
        ("POST", "/api/pmc/purchase/sku-cycles/SKU1/overrides", False),
    ],
)
def test_restricted_org_cannot_use_unreviewed_purchase_routes(
    method: str, path: str, allowed: bool
) -> None:
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    session = MagicMock()
    session.info = {}
    principal = Principal(user_id="8", permissions=frozenset({"pmc:purchase:read"}))
    with patch(
        "app.modules.pmc_purchase.router.resolve_business_owner_refs",
        return_value=frozenset({"owner-approved"}),
    ):
        if allowed:
            require_pmc_purchase_org_scope(request, principal, session)
            assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"owner-approved"})
        else:
            with pytest.raises(ApiError) as error:
                require_pmc_purchase_org_scope(request, principal, session)
            assert error.value.status_code == 403
            assert ORG_OWNER_SCOPE_SESSION_KEY not in session.info
