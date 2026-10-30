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
    assert (
        permission_for_request("GET", "/api/products/skus", "products:read")
        == "page:products:product-management:view"
    )


def test_product_detail_actions_use_canonical_permissions() -> None:
    product_id = "00000000-0000-0000-0000-000000000001"
    assert (
        permission_for_request(
            "GET",
            f"/api/products/skus/{product_id}/raw-lineage",
            "products:raw_lineage:read",
        )
        == "action:products:product-management:view-raw-lineage"
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
    assert (
        permission_for_request(
            "PUT",
            "/api/product-management/pricing-rules",
            "products:pricing_rules:update",
        )
        == "action:products:product-management:update-pricing-rules"
    )
    assert (
        permission_for_request(
            "POST",
            "/api/business-rules/store-commissions/deactivate",
            "business-rules:write",
        )
        == "action:settings:fee-rules:edit"
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


def test_domestic_batch_board_uses_the_page_permission() -> None:
    assert (
        permission_for_request(
            "GET",
            "/api/pmc/domestic/batches",
            "pmc:domestic-batch:read",
        )
        == "page:pmc:domestic-warehouse-board:view"
    )


def test_method_specific_writes_are_not_reduced_to_page_view() -> None:
    assert (
        permission_for_request(
            "POST",
            "/api/pmc/purchase/sku-cycles/SKU-1/overrides",
            "pmc:purchase:override",
        )
        == "action:pmc:purchase-board:override"
    )
    assert (
        permission_for_request(
            "POST",
            "/api/operations/plans/products/00000000-0000-0000-0000-000000000001/clearance",
            "operations:plan:write",
        )
        == "action:operations:plan:edit"
    )


def test_approval_routes_separate_page_request_and_review_permissions() -> None:
    approval_id = "00000000-0000-0000-0000-000000000001"
    assert (
        permission_for_request("GET", "/api/approvals", "approvals:workbench:read")
        == "page:data-center:approval-workspace:view"
    )
    assert (
        permission_for_request(
            "POST",
            f"/api/approvals/{approval_id}/decision",
            "page:data-center:approval-workspace:view",
        )
        == "action:warehouse:wfs-fee-alert:archive-review"
    )
    assert (
        permission_for_request(
            "POST",
            f"/api/approvals/{approval_id}/supplement",
            "page:data-center:approval-workspace:view",
        )
        == "action:warehouse:wfs-fee-alert:archive-request"
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


def test_listing_write_routes_require_action_permissions() -> None:
    examples = (
        (
            "POST",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000001/archive",
            "action:products:listing-management:archive",
        ),
        (
            "POST",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000001/restore",
            "action:products:listing-management:restore",
        ),
        ("POST", "/api/listings/tags/batch-set", "action:products:listing-management:manage-tags"),
        (
            "DELETE",
            "/api/listings/tags/00000000-0000-0000-0000-000000000001",
            "action:products:listing-management:manage-tags",
        ),
        (
            "PUT",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000001/gpt-analysis",
            "action:products:listing-management:edit-analysis-link",
        ),
    )
    for method, path, required in examples:
        assert permission_for_request(method, path, "products:read") == required
