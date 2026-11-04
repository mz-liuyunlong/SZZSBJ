"""PMC purchase board enforces Feishu-reviewed owner bounds on SQL."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY
from app.modules.pmc_purchase.repository import PmcPurchaseReadRepository
from app.modules.pmc_purchase.router import require_pmc_purchase_org_scope
from app.modules.pmc_purchase.schemas import BoardListQuery, PendingPlanQuery


def test_legacy_pmc_read_grant_resolves_to_canonical_page_permission() -> None:
    from app.core.permissions import has_permission

    principal = Principal(user_id="8", permissions=frozenset({"pmc:purchase:read"}))
    assert has_permission(principal, "page:pmc:purchase-board:view")


def test_board_query_is_restricted_by_owner_and_account() -> None:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"owner-approved"})}
    repository = PmcPurchaseReadRepository(session)
    statement = repository._board_select(
        BoardListQuery(), frozenset({"ACCOUNT1"}), date(2026, 11, 3)
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
        ("GET", "/api/pmc/purchase/board/summary", True),
        ("GET", "/api/pmc/purchase/orders/PO123", True),
        ("GET", "/api/pmc/purchase/plans/pending", True),
        ("GET", "/api/pmc/purchase/sku-cycles", False),
        ("GET", "/api/pmc/purchase/sku-cycles/SKU1/overrides", False),
        ("POST", "/api/pmc/purchase/sku-cycles/SKU1/overrides", False),
    ],
)
def test_restricted_org_cannot_use_unreviewed_purchase_routes(
    method: str, path: str, allowed: bool
) -> None:
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    session = MagicMock()
    session.info = {}
    principal = Principal(
        user_id="8",
        permissions=frozenset({"pmc:purchase:read", "pmc:purchase:override"}),
    )
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



def test_pending_plan_conversion_is_scoped_to_same_source_account() -> None:
    """A plan number from a different account cannot suppress a pending plan."""
    session = MagicMock()
    session.info = {}
    repository = PmcPurchaseReadRepository(session)
    statement = repository._pending_plan_select(
        PendingPlanQuery(), frozenset({"ACCOUNT1", "ACCOUNT2"})
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "dws_purchase_board.source_account_ref = dwd_purchase_plan.source_account_ref" in sql
    assert "dws_purchase_board.plan_sn = dwd_purchase_plan.plan_sn" in sql
    assert "NOT (EXISTS" in sql
    assert " NOT IN " not in sql


def test_pending_plan_owner_proof_requires_same_store_and_sku() -> None:
    """Historical owner evidence in another store must not authorize a plan."""
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"owner-approved"})}
    repository = PmcPurchaseReadRepository(session)
    statement = repository._pending_plan_select(
        PendingPlanQuery(), frozenset({"ACCOUNT1"})
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "dws_purchase_board.source_account_ref = dwd_purchase_plan.source_account_ref" in sql
    assert "dws_purchase_board.store_id = dwd_purchase_plan.store_id" in sql
    assert "dws_purchase_board.sku = dwd_purchase_plan.sku" in sql
    assert "dws_purchase_board.owner_uid IN ('owner-approved')" in sql
    assert "dwd_purchase_plan.store_id IS NOT NULL" in sql
