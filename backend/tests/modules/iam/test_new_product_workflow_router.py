from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from pydantic import ValidationError

from app.core.api import ApiError
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.new_product_workflow.router import (
    APPROVE,
    DecisionWrite,
    LaunchDateWrite,
    MarketWrite,
    PurchaseWrite,
    ReviewWrite,
    RuleWrite,
    _identity,
    get_independent_purchase_plan,
    list_independent_purchase_plans,
    list_workflows,
    router,
)


def test_business_payloads_reject_invalid_scores_and_unplanned_optimization() -> None:
    with pytest.raises(ValidationError):
        MarketWrite(expected_version=0, score=11, reason="市场竞争严重失衡")
    with pytest.raises(ValidationError):
        ReviewWrite(expected_version=1, result="optimize", reason="需要调整广告词")


@pytest.mark.parametrize(
    "payload, values",
    [
        (MarketWrite, {"expected_version": 0, "score": 6, "reason": "      "}),
        (PurchaseWrite, {"expected_version": 1, "quantity": 10, "reason": "      "}),
        (DecisionWrite, {"expected_version": 1, "decision": "rejected", "note": "      "}),
        (
            ReviewWrite,
            {"expected_version": 1, "result": "observe", "reason": "      "},
        ),
        (
            LaunchDateWrite,
            {
                "expected_version": 1,
                "arrival_date": "2026-08-10",
                "sellable_date": "2026-08-12",
                "evidence": "      ",
            },
        ),
        (
            RuleWrite,
            {
                "expected_version": 0,
                "reason": "      ",
                "weights": {"market": 15, "order": 30, "ads": 20, "profit": 25, "trust": 10},
                "success_days": 60,
                "min_sales": 200,
                "min_margin": 0,
                "max_acos": 35,
            },
        ),
    ],
)
def test_audit_evidence_cannot_contain_only_whitespace(payload, values) -> None:
    with pytest.raises(ValidationError):
        payload(**values)


def test_future_dates_cannot_be_falsely_confirmed_as_actual() -> None:
    with pytest.raises(ValidationError):
        LaunchDateWrite(
            expected_version=1,
            arrival_date="2099-01-01",
            sellable_date="2099-01-02",
            evidence="未来日期尚未实际发生",
        )


def test_verified_launch_dates_require_evidence() -> None:
    with pytest.raises(ValidationError):
        LaunchDateWrite(
            expected_version=1,
            arrival_date="2026-08-10",
            sellable_date="2026-08-12",
            evidence="短",
        )


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


def test_purchase_plans_refuse_out_of_scope_account() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/api/new-products/purchase-plans"})
    with pytest.raises(ApiError) as error:
        list_independent_purchase_plans(
            request=request,
            session=MagicMock(),
            _=Principal(user_id="42", permissions=frozenset()),
            accounts=frozenset({"account-a"}),
            source_account_ref="account-b",
            page=1,
            page_size=50,
        )
    assert error.value.status_code == 403


def test_independent_plan_detail_is_not_visible_outside_account_scope() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/new-products/purchase-plans/test"}
    )
    with pytest.raises(ApiError) as error:
        get_independent_purchase_plan(
            request=request,
            plan_id=UUID("00000000-0000-0000-0000-000000000301"),
            session=session,
            _=Principal(user_id="reader", permissions=frozenset()),
            accounts=frozenset({"account-a"}),
        )
    assert error.value.status_code == 404
    query, params = session.execute.call_args.args
    assert "source_account_ref = ANY(:accounts)" in str(query)
    assert params["accounts"] == ["account-a"]


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
    paths = {route.path for route in router.routes}
    assert "/api/new-products/workflows" in paths
    assert "/api/new-products/workflows/{sku_id}/purchase-decision" in paths
    assert "/api/new-products/dashboard" in paths
    assert "/api/new-products/score-corrections" in paths
    assert "/api/new-products/workflows/{sku_id}/score-correction" in paths
    assert "/api/new-products/score-corrections/{correction_id}/decision" in paths
    assert "/api/new-products/rules/history" in paths
    assert "/api/new-products/purchase-plans" in paths
    assert "/api/new-products/purchase-plans/{plan_id}" in paths
    assert "/api/new-products/rules" in paths
    assert "/api/new-products/execute-purchase" not in paths
