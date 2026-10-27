from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestPermissionRule:
    method: str | None
    path_prefix: str
    permission_key: str
    exact: bool = False

    def matches(self, method: str, path: str) -> bool:
        if self.method is not None and method != self.method:
            return False
        return path == self.path_prefix if self.exact else path.startswith(self.path_prefix)


_RULES: tuple[RequestPermissionRule, ...] = (
    RequestPermissionRule(
        "GET",
        "/api/products/skus",
        "page:products:product-management:view",
        True,
    ),
    RequestPermissionRule(
        "GET",
        "/api/products/skus/",
        "page:products:product-management:view",
    ),
    RequestPermissionRule(
        "GET",
        "/api/product-management/skus/export",
        "action:products:product-management:export",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/product-management/skus/export",
        "action:products:product-management:export",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/product-management/skus/recalculate-pricing",
        "action:products:product-management:recalculate-pricing",
        True,
    ),
    RequestPermissionRule(
        "PUT",
        "/api/product-management/pricing-rules",
        "action:products:product-management:update-pricing-rules",
        True,
    ),
    RequestPermissionRule(
        "PUT",
        "/api/user-table-views/product-management",
        "action:products:product-management:save-table-view",
        True,
    ),
    RequestPermissionRule(
        None,
        "/api/product-management/",
        "page:products:product-management:view",
    ),
    RequestPermissionRule(
        "GET",
        "/api/user-table-views/product-management",
        "page:products:product-management:view",
        True,
    ),
    RequestPermissionRule(
        "PUT",
        "/api/listings/rule-config",
        "action:products:listing-management:configure-rules",
        True,
    ),
    RequestPermissionRule(
        "GET",
        "/api/listings/walmart/export",
        "action:products:listing-management:export",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/listings/tags/batch-set",
        "action:products:listing-management:manage-tags",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/listings/tags",
        "action:products:listing-management:manage-tags",
        True,
    ),
    RequestPermissionRule(
        "PATCH",
        "/api/listings/tags/",
        "action:products:listing-management:manage-tags",
    ),
    RequestPermissionRule(
        "DELETE",
        "/api/listings/tags/",
        "action:products:listing-management:manage-tags",
    ),
    RequestPermissionRule(
        "POST",
        "/api/listings/walmart/",
        "action:products:listing-management:archive",
    ),
    RequestPermissionRule(
        "PUT",
        "/api/listings/walmart/",
        "action:products:listing-management:edit-analysis-link",
    ),
    RequestPermissionRule(
        "PATCH",
        "/api/listings/evaluation-followups/",
        "action:products:listing-management:manage-followups",
        True,
    ),
    RequestPermissionRule(None, "/api/listings/", "page:products:listing-management:view"),
    RequestPermissionRule(
        "GET",
        "/api/sales/daily-sales/export",
        "action:sales:daily-sales:export",
        True,
    ),
    RequestPermissionRule(None, "/api/sales/daily-sales", "page:sales:daily-sales:view"),
    RequestPermissionRule(
        "GET",
        "/api/sales/order-profit/export",
        "action:sales:order-profit:export",
        True,
    ),
    RequestPermissionRule(None, "/api/sales/order-profit", "page:sales:order-profit:view"),
    RequestPermissionRule(
        None,
        "/api/data-pages/filter-options",
        "page:sales:daily-sales:view",
        True,
    ),
    RequestPermissionRule(
        None,
        "/api/after-sales/refunds",
        "page:aftersales:refund-management:view",
    ),
    RequestPermissionRule(
        "POST",
        "/api/warehouse/wfs-fee-cases/sync-legacy-preview",
        "action:warehouse:wfs-fee-alert:sync-legacy",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/warehouse/wfs-fee-cases/sync-legacy-execute",
        "action:warehouse:wfs-fee-alert:sync-legacy",
        True,
    ),
    RequestPermissionRule(
        "GET",
        "/api/warehouse/wfs-fee-cases/legacy-compare",
        "action:warehouse:wfs-fee-alert:sync-legacy",
        True,
    ),
    RequestPermissionRule(
        "PUT",
        "/api/warehouse/wfs-fee-alerts/",
        "action:warehouse:wfs-fee-alert:follow",
    ),
    RequestPermissionRule(None, "/api/warehouse/wfs", "page:warehouse:wfs-fee-alert:view"),
    RequestPermissionRule(
        "POST",
        "/api/pmc/purchase/sku-cycles/",
        "action:pmc:purchase-board:override",
    ),
    RequestPermissionRule(None, "/api/pmc/purchase", "page:pmc:purchase-board:view"),
    RequestPermissionRule(None, "/api/pmc/domestic", "page:pmc:domestic-warehouse-board:view"),
    RequestPermissionRule(
        "POST",
        "/api/operations/plans/products/",
        "action:operations:plan:edit",
    ),
    RequestPermissionRule(
        "POST",
        "/api/operations/plans/import",
        "action:operations:plan:import",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/operations/plans",
        "action:operations:plan:create",
        True,
    ),
    RequestPermissionRule(
        "PATCH",
        "/api/operations/plans/",
        "action:operations:plan:edit",
    ),
    RequestPermissionRule(None, "/api/operations/plans", "page:operations:plan:view"),
    RequestPermissionRule(
        "PATCH",
        "/api/integrations/sync-configs/",
        "action:data-center:task-center:configure",
    ),
    RequestPermissionRule(
        "POST",
        "/api/integrations/sync-configs/",
        "action:data-center:task-center:execute",
    ),
    RequestPermissionRule(
        "POST",
        "/api/integrations/sync-runs/",
        "action:data-center:task-center:execute",
    ),
    RequestPermissionRule(
        "GET",
        "/api/integrations/walmart-monitor/targets",
        "integrations:walmart-monitor:read",
        True,
    ),
    RequestPermissionRule(None, "/api/integrations/", "page:data-center:task-center:view"),
    RequestPermissionRule(
        "POST",
        "/api/business-rules/store-commissions/recalculate",
        "action:settings:fee-rules:recalculate",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/business-rules/store-commissions/deactivate",
        "action:settings:fee-rules:edit",
        True,
    ),
    RequestPermissionRule(
        "POST",
        "/api/business-rules/store-commissions",
        "action:settings:fee-rules:edit",
        True,
    ),
    RequestPermissionRule(
        "PATCH",
        "/api/business-rules/",
        "action:settings:fee-rules:edit",
    ),
    RequestPermissionRule(None, "/api/business-rules/", "page:settings:fee-rules:view"),
)


def permission_for_request(method: str, path: str, declared_permission: str) -> str:
    normalized_method = method.upper()
    if normalized_method == "GET" and path.startswith("/api/products/skus/"):
        suffix_permissions = {
            "/cost-history": "field:products:product-management:purchase-cost",
            "/sync-history": "action:products:product-management:view-sync-history",
            "/raw-lineage": "action:products:product-management:view-raw-lineage",
            "/operation-logs": "action:products:product-management:view-operation-logs",
        }
        for suffix, permission_key in suffix_permissions.items():
            if path.endswith(suffix):
                return permission_key
    if path == "/api/approvals" or path == "/api/approvals/summary":
        return "page:data-center:approval-workspace:view"
    if path.startswith("/api/approvals/"):
        if normalized_method == "POST" and path.endswith("/decision"):
            return "action:warehouse:wfs-fee-alert:archive-review"
        if normalized_method == "POST" and path.endswith("/supplement"):
            return "action:warehouse:wfs-fee-alert:archive-request"
        if normalized_method == "POST" and "/wfs-cases/" in path:
            return "action:warehouse:wfs-fee-alert:archive-request"
        if normalized_method == "GET":
            return "page:data-center:approval-workspace:view"

    if normalized_method == "POST" and path.startswith("/api/warehouse/wfs-fee-cases/"):
        if path.endswith("/follow"):
            return "action:warehouse:wfs-fee-alert:follow"
        if path.endswith("/archive-request"):
            return "action:warehouse:wfs-fee-alert:archive-request"
        if path.endswith("/archive-review"):
            return "action:warehouse:wfs-fee-alert:archive-review"
        if path.endswith("/mark-recovered"):
            return "action:warehouse:wfs-fee-alert:mark-recovered"

    if normalized_method == "POST" and path.startswith(
        "/api/pmc/domestic/packing-approval/pending/"
    ):
        if path.endswith("/approve"):
            return "action:pmc:domestic-warehouse-board:packing-approve"
        if path.endswith("/reject"):
            return "action:pmc:domestic-warehouse-board:packing-reject"
    if normalized_method == "POST" and path.startswith(
        "/api/pmc/domestic/packing-warehouse/orders/"
    ):
        actions = {
            "boxes": "packing-boxes-save",
            "done": "packing-done",
            "customs": "packing-customs",
            "notes": "packing-note",
            "unpacked": "packing-unpacked-dispose",
            "rebox": "packing-rebox",
            "supplemental-inbound": "packing-supplement-ib",
            "supplemental-sync": "packing-supplement-sync",
        }
        action = actions.get(path.rsplit("/", 1)[-1])
        if action:
            return "action:pmc:domestic-warehouse-board:" + action
    if normalized_method == "POST" and path == "/api/pmc/domestic/packing-approval/manual":
        return "action:pmc:domestic-warehouse-board:packing-manual-create"
    for rule in _RULES:
        if rule.matches(normalized_method, path):
            if (
                rule.permission_key == "action:products:listing-management:archive"
                and path.endswith("/restore")
            ):
                return "action:products:listing-management:restore"
            return rule.permission_key
    return declared_permission
