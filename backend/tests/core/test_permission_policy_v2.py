from fastapi import Request

from app.core.auth import Principal
from app.core.permission_policy_v2 import permission_for_request
from app.core.permissions import require_permission


def _request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def test_product_and_listing_pages_have_distinct_permissions() -> None:
    assert (
        permission_for_request("GET", "/api/product-management/options", "products:read")
        == "page:products:product-management:view"
    )
    assert (
        permission_for_request("GET", "/api/listings/walmart", "products:read")
        == "page:products:listing-management:view"
    )


def test_daily_sales_and_order_profit_have_distinct_permissions() -> None:
    assert (
        permission_for_request("GET", "/api/sales/daily-sales", "sales:daily-sales:read")
        == "page:sales:daily-sales:view"
    )
    assert (
        permission_for_request("GET", "/api/sales/order-profit", "sales:daily-sales:read")
        == "page:sales:order-profit:view"
    )


def test_page_action_permissions_are_specific_to_page() -> None:
    assert (
        permission_for_request("POST", "/api/listings/tags", "products:read")
        == "action:products:listing-management:manage-tags"
    )
    assert (
        permission_for_request("GET", "/api/product-management/skus/export", "products:read")
        == "action:products:product-management:export"
    )


def test_wfs_case_actions_are_bound_to_their_page_actions() -> None:
    case_id = "00000000-0000-0000-0000-000000000001"
    assert (
        permission_for_request(
            "POST",
            f"/api/warehouse/wfs-fee-cases/{case_id}/follow",
            "warehouse:wfs-fee-alert:write",
        )
        == "action:warehouse:wfs-fee-alert:follow"
    )
    assert (
        permission_for_request(
            "POST",
            f"/api/warehouse/wfs-fee-cases/{case_id}/archive-review",
            "warehouse:wfs-fee-alert:review",
        )
        == "action:warehouse:wfs-fee-alert:archive-review"
    )
    assert (
        permission_for_request(
            "POST",
            "/api/warehouse/wfs-fee-cases/sync-legacy-execute",
            "warehouse:wfs-fee-alert:sync",
        )
        == "action:warehouse:wfs-fee-alert:sync-legacy"
    )


def test_require_permission_uses_request_specific_permission() -> None:
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset({"page:products:listing-management:view"}),
    )
    resolved = require_permission("products:read")(
        principal,
        _request("GET", "/api/listings/walmart"),
    )
    assert resolved is principal
