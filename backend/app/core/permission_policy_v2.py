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
        "/api/user-table-views/product-management",
        "action:products:product-management:save-table-view",
        True,
    ),
    RequestPermissionRule(
        None, "/api/product-management/", "page:products:product-management:view"
    ),
    RequestPermissionRule(
        "GET",
        "/api/user-table-views/product-management",
        "page:products:product-management:view",
        True,
    ),
    RequestPermissionRule(
        "GET", "/api/listings/walmart/export", "action:products:listing-management:export", True
    ),
    RequestPermissionRule(
        "POST",
        "/api/listings/tags/batch-set",
        "action:products:listing-management:manage-tags",
        True,
    ),
    RequestPermissionRule(
        "POST", "/api/listings/tags", "action:products:listing-management:manage-tags", True
    ),
    RequestPermissionRule(
        "PATCH", "/api/listings/tags/", "action:products:listing-management:manage-tags"
    ),
    RequestPermissionRule(
        "DELETE", "/api/listings/tags/", "action:products:listing-management:manage-tags"
    ),
    RequestPermissionRule(
        "POST", "/api/listings/walmart/", "action:products:listing-management:archive"
    ),
    RequestPermissionRule(
        "PUT", "/api/listings/walmart/", "action:products:listing-management:edit-analysis-link"
    ),
    RequestPermissionRule(None, "/api/listings/", "page:products:listing-management:view"),
    RequestPermissionRule(
        "GET", "/api/sales/daily-sales/export", "action:sales:daily-sales:export", True
    ),
    RequestPermissionRule(None, "/api/sales/daily-sales", "page:sales:daily-sales:view"),
    RequestPermissionRule(
        "GET", "/api/sales/order-profit/export", "action:sales:order-profit:export", True
    ),
    RequestPermissionRule(None, "/api/sales/order-profit", "page:sales:order-profit:view"),
    RequestPermissionRule(
        None, "/api/data-pages/filter-options", "page:sales:daily-sales:view", True
    ),
    RequestPermissionRule(
        None, "/api/after-sales/refunds", "page:aftersales:refund-management:view"
    ),
    RequestPermissionRule(None, "/api/warehouse/wfs", "page:warehouse:wfs-fee-alert:view"),
    RequestPermissionRule(None, "/api/pmc/purchase", "page:pmc:purchase-board:view"),
    RequestPermissionRule(
        "POST", "/api/operations/plans/import", "action:operations:plan:import", True
    ),
    RequestPermissionRule("POST", "/api/operations/plans", "action:operations:plan:create", True),
    RequestPermissionRule("PATCH", "/api/operations/plans/", "action:operations:plan:edit"),
    RequestPermissionRule(None, "/api/operations/plans", "page:operations:plan:view"),
    RequestPermissionRule(
        "PATCH", "/api/integrations/sync-configs/", "action:data-center:task-center:configure"
    ),
    RequestPermissionRule(
        "POST", "/api/integrations/sync-configs/", "action:data-center:task-center:execute"
    ),
    RequestPermissionRule(
        "POST", "/api/integrations/sync-runs/", "action:data-center:task-center:execute"
    ),
    RequestPermissionRule(None, "/api/integrations/", "page:data-center:task-center:view"),
    RequestPermissionRule(
        "POST",
        "/api/business-rules/store-commissions/recalculate",
        "action:settings:fee-rules:recalculate",
        True,
    ),
    RequestPermissionRule(
        "POST", "/api/business-rules/store-commissions", "action:settings:fee-rules:edit", True
    ),
    RequestPermissionRule("PATCH", "/api/business-rules/", "action:settings:fee-rules:edit"),
    RequestPermissionRule(None, "/api/business-rules/", "page:settings:fee-rules:view"),
)


def permission_for_request(method: str, path: str, declared_permission: str) -> str:
    normalized_method = method.upper()
    for rule in _RULES:
        if rule.matches(normalized_method, path):
            if (
                rule.permission_key == "action:products:listing-management:archive"
                and path.endswith("/restore")
            ):
                return "action:products:listing-management:restore"
            return rule.permission_key
    return declared_permission
