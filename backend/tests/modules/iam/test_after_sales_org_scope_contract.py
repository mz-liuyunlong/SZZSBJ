"""Refund aggregates and drill-downs must share the same audited owner scope."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.after_sales.repository import AfterSalesRefundRepository
from app.modules.after_sales.router import require_refund_org_scope
from app.modules.after_sales.schemas import RefundBaseQuery
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY


def _query() -> RefundBaseQuery:
    return RefundBaseQuery(start_date=date(2026, 10, 1), end_date=date(2026, 10, 31))


def test_refund_and_sales_aggregation_filter_the_same_owner() -> None:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"uid-reviewed"})}
    repository = AfterSalesRefundRepository(session)
    refund_where, refund_params = repository._refund_where(_query(), frozenset({"A1"}))
    sales_where, sales_params = repository._sales_where(_query(), frozenset({"A1"}))
    assert "om.owner_ref = any(:org_owner_refs)" in refund_where
    assert "m.owner_ref = any(:org_owner_refs)" in sales_where
    assert refund_params["org_owner_refs"] == sales_params["org_owner_refs"] == ["uid-reviewed"]
    assert refund_params["accounts"] == sales_params["accounts"] == ["A1"]


def test_refund_product_summary_never_uses_other_owner_sales() -> None:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"uid-reviewed"})}
    session.execute.return_value.mappings.return_value.all.return_value = []
    repository = AfterSalesRefundRepository(session)
    repository.product_summary(_query(), frozenset({"A1"}), limit=10)
    sql = str(session.execute.call_args.args[0])
    params = session.execute.call_args.args[1]
    assert "om.owner_ref = any(:org_owner_refs)" in sql
    assert "m.owner_ref = any(:sales_org_owner_refs)" in sql
    assert params["sales_org_owner_refs"] == ["uid-reviewed"]


def test_refund_scope_is_installed_per_request() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/after-sales/refunds/items",
            "headers": [],
        }
    )
    principal = Principal(user_id="8", permissions=frozenset({"aftersales:refund-management:read"}))
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"stale"})}
    with patch(
        "app.modules.after_sales.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-reviewed"}),
    ):
        require_refund_org_scope(request, principal, session)
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-reviewed"})


def test_refund_scope_fails_closed_for_unprivileged_principal() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/after-sales/refunds/overview",
            "headers": [],
        }
    )
    principal = Principal(user_id="8", permissions=frozenset())
    session = MagicMock()
    session.info = {}
    with patch("app.modules.after_sales.router.resolve_business_owner_refs") as resolver:
        with pytest.raises(ApiError) as error:
            require_refund_org_scope(request, principal, session)
    assert error.value.status_code == 403
    resolver.assert_not_called()


def test_account_qualified_refunds_and_sales_share_exact_owner_pairs() -> None:
    import json

    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({
            ("ACCOUNT-1", "SHARED-UID"),
        })
    }
    repository = AfterSalesRefundRepository(session)
    refund_where, refund_params = repository._refund_where(
        _query(), frozenset({"ACCOUNT-1", "ACCOUNT-2"})
    )
    sales_where, sales_params = repository._sales_where(
        _query(), frozenset({"ACCOUNT-1", "ACCOUNT-2"})
    )
    assert any(
        "granted.source_account_ref = r.source_account_ref" in value
        and "granted.owner_ref = om.owner_ref" in value
        for value in refund_where
    )
    assert any(
        "granted.source_account_ref = m.source_account_ref" in value
        and "granted.owner_ref = m.owner_ref" in value
        for value in sales_where
    )
    expected = [{"source_account_ref": "ACCOUNT-1", "owner_ref": "SHARED-UID"}]
    assert json.loads(refund_params["account_owner_pairs"]) == expected
    assert json.loads(sales_params["account_owner_pairs"]) == expected


def test_account_qualified_refund_scope_is_applied_to_reviewed_reads() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/after-sales/refunds/items",
        "headers": [],
    })
    session = MagicMock()
    session.info = {}
    principal = Principal(
        user_id="8", permissions=frozenset({"aftersales:refund-management:read"})
    )
    with (
        patch(
            "app.modules.after_sales.router.resolve_business_account_owner_pairs",
            return_value=frozenset({("ACCOUNT-1", "SHARED-UID")}),
        ),
        patch("app.modules.after_sales.router.resolve_business_owner_refs") as legacy,
    ):
        require_refund_org_scope(request, principal, session)
    legacy.assert_not_called()
    assert session.info[ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY] == frozenset({
        ("ACCOUNT-1", "SHARED-UID")
    })
