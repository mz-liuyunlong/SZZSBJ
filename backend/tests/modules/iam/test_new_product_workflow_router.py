from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from pydantic import ValidationError

from app.core.api import ApiError
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.main import create_app
from app.modules.new_product_workflow.router import (
    APPROVE,
    MarketWrite,
    ReviewWrite,
    RuleWrite,
    _identity,
    list_workflows,
)


def test_business_payloads_reject_invalid_scores_and_unplanned_optimization() -> None:
    with pytest.raises(ValidationError):
        MarketWrite(expected_version=0, score=11, reason="市场竞争严重失衡")
    with pytest.raises(ValidationError):
        ReviewWrite(expected_version=1, result="optimize", reason="需要调整广告词")


def test_rule_write_requires_complete_weighting() -> None:
    with pytest.raises(ValidationError):
        RuleWrite(
            expected_version=0,
            reason="希望调整新品评分",
            weights={"market": 20, "order": 30, "ads": 20, "profit": 25, "trust": 10},
            success_days=60,
            min_sales=200,
            min_margin=5,
            max_acos=35,
        )


def test_draft_approval_is_not_granted_by_page_view() -> None:
    principal = Principal(
        user_id="42",
        permissions=frozenset({"page:products:new-product-analysis:view"}),
    )
    with pytest.raises(ApiError) as error:
        require_permission(APPROVE)(principal)
    assert error.value.status_code == 403


def test_list_rejects_account_outside_principal_scope() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/api/new-products/workflows"})
    with pytest.raises(ApiError) as error:
        list_workflows(
            request=request,
            session=MagicMock(),
            _=Principal(user_id="42", permissions=frozenset()),
            accounts=frozenset({"account-a"}),
            source_account_ref="account-b",
            page=1,
            page_size=50,
        )
    assert error.value.status_code == 403


def test_unknown_sku_identity_fails_closed() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ApiError) as error:
        _identity(
            session,
            UUID("00000000-0000-0000-0000-000000000001"),
            frozenset({"account-a"}),
        )
    assert error.value.status_code == 404


def test_workflow_router_registered_without_exposing_real_purchase_execution() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/new-products/workflows" in paths
    assert "/api/new-products/workflows/{sku_id}/purchase-decision" in paths
    assert "/api/new-products/rules" in paths
    assert "/api/new-products/execute-purchase" not in paths
