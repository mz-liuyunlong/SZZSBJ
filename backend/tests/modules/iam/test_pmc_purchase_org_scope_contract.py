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
    statement = repository._pending_plan_select(PendingPlanQuery(), frozenset({"ACCOUNT1"}))
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "dws_purchase_board.source_account_ref = dwd_purchase_plan.source_account_ref" in sql
    assert "dws_purchase_board.store_id = dwd_purchase_plan.store_id" in sql
    assert "dws_purchase_board.sku = dwd_purchase_plan.sku" in sql
    assert "dws_purchase_board.owner_uid IN ('owner-approved')" in sql
    assert "dwd_purchase_plan.store_id IS NOT NULL" in sql


def test_pmc_store_scope_filters_account_store_pair_in_board_sql() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"owner-approved"}),
        STORE_SCOPE_SESSION_KEY: frozenset({("ACCOUNT1", "S-01")}),
    }
    repository = PmcPurchaseReadRepository(session)
    statement = repository._board_select(
        BoardListQuery(), frozenset({"ACCOUNT1", "ACCOUNT2"}), date(2026, 11, 3)
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "('ACCOUNT1', 'S-01')" in sql
    assert "owner_uid IN ('owner-approved')" in sql
    assert "source_account_ref IN ('ACCOUNT1', 'ACCOUNT2')" in sql


def test_pmc_pending_plan_is_scoped_by_account_and_store_before_aggregation() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {STORE_SCOPE_SESSION_KEY: frozenset({("ACCOUNT1", "S-01")})}
    repository = PmcPurchaseReadRepository(session)
    statement = repository._pending_plan_select(
        PendingPlanQuery(), frozenset({"ACCOUNT1", "ACCOUNT2"})
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "('ACCOUNT1', 'S-01')" in sql
    assert "dwd_purchase_plan.source_account_ref" in sql
    assert "dwd_purchase_plan.store_id" in sql


def test_pmc_store_scope_is_installed_on_reviewed_read_routes_only() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/pmc/purchase/board",
        "headers": [],
    })
    session = MagicMock()
    session.info = {}
    principal = Principal(user_id="8", permissions=frozenset({"pmc:purchase:read"}))
    with (
        patch(
            "app.modules.pmc_purchase.router.resolve_business_owner_refs",
            return_value=frozenset({"owner-approved"}),
        ),
        patch(
            "app.modules.pmc_purchase.router.resolve_account_store_scope",
            return_value=frozenset({("ACCOUNT1", "S-01")}),
        ),
    ):
        require_pmc_purchase_org_scope(request, principal, session)
    assert session.info[STORE_SCOPE_SESSION_KEY] == frozenset({("ACCOUNT1", "S-01")})
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"owner-approved"})


def test_pmc_store_scope_disallows_unreviewed_sku_cycle_aggregation() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/pmc/purchase/sku-cycles",
        "headers": [],
    })
    session = MagicMock()
    session.info = {}
    principal = Principal(user_id="8", permissions=frozenset({"pmc:purchase:read"}))
    with (
        patch(
            "app.modules.pmc_purchase.router.resolve_business_owner_refs",
            return_value=None,
        ),
        patch(
            "app.modules.pmc_purchase.router.resolve_account_store_scope",
            return_value=frozenset({("ACCOUNT1", "S-01")}),
        ),
    ):
        with pytest.raises(ApiError) as error:
            require_pmc_purchase_org_scope(request, principal, session)
    assert error.value.status_code == 403
    assert STORE_SCOPE_SESSION_KEY not in session.info


def test_pmc_scoped_rows_hide_whole_order_and_cross_owner_cycle_fields() -> None:
    from datetime import datetime, timezone
    from decimal import Decimal
    from types import SimpleNamespace

    from app.modules.pmc_purchase.service import _board_row

    line = SimpleNamespace(
        order_sn="PO1",
        draft_no="draft-01",
        order_item_id="line-01",
        plan_sn="plan-own",
        plan_sns_json=["plan-own", "plan-other"],
        order_status=2,
        stage_code="S3",
        stage_start=None,
        stage_start_estimated=False,
        threshold_days=14,
        due_date=None,
        overdue_days=0,
        alert_due_since=None,
        store_id="store-01",
        store_name="Store One",
        store_attributed=True,
        sku="SKU1",
        product_name="Synthetic",
        item_id="item-01",
        source_lineage_json={"item_id_identities": []},
        item_id_source="unresolved",
        item_id_source_ref=None,
        item_id_matched_at=None,
        item_id_match_status="unresolved",
        msku=None,
        gtin=None,
        fulfillment_type=None,
        wfs_not_ready=None,
        owner_uid="owner-one",
        owner_name="Owner One",
        quantity_total=100,
        quantity_allocated=20,
        quantity_received=10,
        progress_ratio=Decimal("0.5"),
        remaining_quantity=10,
        order_date=None,
        order_create_date=None,
        plan_create_date=None,
        arrival_date=date(2026, 11, 3),
        arrival_receipt_order_sn="receipt-other",
        purchase_cycle_days=30,
        approval_cycle_days=3,
        sku_cycle_days=Decimal("28"),
        sku_cycle_source="samples",
        sku_cycle_sample_count=5,
        sku_cycle_unstable=True,
        unit_price=Decimal("5"),
        amount_allocated=Decimal("100"),
        amount_total=Decimal("500"),
        currency_code="USD",
        calculated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )
    limited = _board_row(line, scoped=True)
    assert limited.quantity_total is None
    assert limited.amount_total is None
    assert limited.amount_allocated == Decimal("100")
    assert limited.plan_sns == ["plan-own"]
    assert limited.arrival_receipt_order_sn is None
    assert limited.arrival_date is None
    assert limited.purchase_cycle_days is None
    assert limited.approval_cycle_days is None
    assert limited.sku_cycle.value_days is None
    assert limited.sku_cycle.unstable is None

    unrestricted = _board_row(line)
    assert unrestricted.quantity_total == 100
    assert unrestricted.amount_total == Decimal("500")
    assert unrestricted.plan_sns == ["plan-own", "plan-other"]
    assert unrestricted.sku_cycle.unstable is True


def test_pmc_scoped_aggregate_drilldowns_are_denied_before_read_service() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY
    from app.modules.pmc_purchase.router import list_board

    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/pmc/purchase/board",
        "headers": [],
    })
    session = MagicMock()
    session.info = {STORE_SCOPE_SESSION_KEY: frozenset({("ACCOUNT1", "S-01")})}
    query = BoardListQuery(summary_filter="unstable_sku")
    principal = Principal(user_id="8", permissions=frozenset({"pmc:purchase:read"}))
    with pytest.raises(ApiError) as error:
        list_board(request, query, session, principal, frozenset({"ACCOUNT1"}))
    assert error.value.status_code == 403
    session.execute.assert_not_called()
