"""Account-qualified owner binding and SQL isolation contract in PR #287."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.core.auth import Principal
from app.modules.data_pages.repository import DailySalesRepository, ListingManagementRepository
from app.modules.iam.organization_access import (
    ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY,
    resolve_business_account_owner_pairs,
)
from app.modules.pmc_purchase.repository import PmcPurchaseReadRepository
from app.modules.pmc_purchase.schemas import BoardListQuery, PendingPlanQuery


def _sql(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _session() -> MagicMock:
    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({
            ("ACCOUNT-1", "UID-SHARED"),
        }),
    }
    return session


def test_daily_sales_owner_uid_is_qualified_by_account() -> None:
    repository = DailySalesRepository(_session())
    sql = _sql(repository._filtered_statement(
        account_refs=frozenset({"ACCOUNT-1", "ACCOUNT-2"}),
        start_date=None, end_date=None, platform=None, store_id=None,
        owner_ref=None, search_field="sku", keyword="",
    ))
    assert "('ACCOUNT-1', 'UID-SHARED')" in sql
    assert "mart_daily_sales_item_day.source_account_ref" in sql
    assert "mart_daily_sales_item_day.owner_ref" in sql


def test_listing_owner_resolution_is_qualified_by_source_account() -> None:
    repository = ListingManagementRepository(_session())
    sql = _sql(repository._filtered_listing_statement(
        account_refs=frozenset({"ACCOUNT-1", "ACCOUNT-2"}),
        store_id=None, owner_ref=None, product_type=None, status=None, tag=None,
        archive_status=None, summary_filter="total", search_field="sku",
        keyword="", batch_values="",
    ))
    assert "('ACCOUNT-1', 'UID-SHARED')" in sql
    assert "owner_uid" in sql
    assert "mart_listing_management_current.source_account_ref" in sql


def test_pmc_board_owner_lookup_is_qualified_by_account() -> None:
    repo = PmcPurchaseReadRepository(_session())
    sql = _sql(repo._board_select(
        BoardListQuery(), frozenset({"ACCOUNT-1", "ACCOUNT-2"}), date(2026, 11, 4),
    ))
    assert "('ACCOUNT-1', 'UID-SHARED')" in sql
    assert "dws_purchase_board.owner_uid" in sql


def test_pmc_plan_ownership_proof_requires_account_store_sku_and_owner() -> None:
    repo = PmcPurchaseReadRepository(_session())
    sql = _sql(repo._pending_plan_select(
        PendingPlanQuery(), frozenset({"ACCOUNT-1", "ACCOUNT-2"}),
    ))
    assert "('ACCOUNT-1', 'UID-SHARED')" in sql
    assert "dws_purchase_board.store_id = dwd_purchase_plan.store_id" in sql
    assert "dws_purchase_board.sku = dwd_purchase_plan.sku" in sql


def test_direct_feishu_user_with_account_bindings_has_exact_pair_scope() -> None:
    session = MagicMock()
    session.execute.return_value = [("ACCOUNT-1", "UID-SHARED")]
    with patch(
        "app.modules.iam.organization_access.RbacRepository.resolve_user_data_scope",
        return_value=set(),
    ):
        pairs = resolve_business_account_owner_pairs(
            session, Principal(user_id="17", permissions=frozenset()),
        )
    assert pairs == frozenset({("ACCOUNT-1", "UID-SHARED")})
    sql_text = str(session.execute.call_args.args[0])
    assert "b.source_account_ref" in sql_text
    assert "b.owner_ref" in sql_text
    assert "u.id = :user_id" in sql_text
    assert "e.last_seen_run_id" in sql_text


def test_account_qualified_binding_rejects_unverified_source_owner_pair() -> None:
    from app.core.api import ApiError
    from app.modules.iam.organization_account_owner_router import (
        AccountOwnerBindingWrite,
        bind_account_owner,
    )

    session = MagicMock()
    session.execute.return_value.scalar.return_value = False
    request = Request({"type": "http", "method": "PUT", "path": "/api/settings/organization/account-owner-bindings/account-2/shared-uid", "headers": []})
    with pytest.raises(ApiError) as denied:
        bind_account_owner(
            request, "ACCOUNT-2", "UID-SHARED",
            AccountOwnerBindingWrite(feishu_open_id="ou-test"),
            Principal(user_id="1", permissions=frozenset({"*"})), session,
        )
    assert denied.value.status_code == 422
    session.commit.assert_not_called()
