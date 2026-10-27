"""Additional US Marketplace read operations from the official reference.

Only GET operations are included. Report creation, feed submission, pricing,
inventory updates, orders acknowledgement/shipping, refunds and Connect ads
are deliberately excluded from this read-only catalog.
"""

from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation


_OPERATIONS = (
    Operation(
        key="inventory_get",
        method="GET",
        path="/v3/inventory",
        fields=(
            Field("sku", "query", required=True),
            Field("shipNode", "query"),
        ),
        source="https://developer.walmart.com/us-marketplace/reference/getinventory",
    ),
    Operation(
        key="inventories_list",
        method="GET",
        path="/v3/inventories",
        fields=(Field("nextCursor", "query"),),
        source="https://developer.walmart.com/us-marketplace/reference/getmultinodeinventoryforallskuandallshipnodes",
    ),
    Operation(
        key="partner_profile_get",
        method="GET",
        path="/v3/settings/partnerprofile",
        fields=(),
        source="https://developer.walmart.com/us-marketplace/reference/getpartnerconfigurations",
    ),
    Operation(
        key="price_incentives_list",
        method="GET",
        path="/v3/price/incentives",
        fields=(
            Field("limit", "query", kind="integer", maximum=100),
            Field("offset", "query", kind="integer"),
            Field("sku", "query"),
            Field("incentiveStatus", "query"),
        ),
        source="https://developer.walmart.com/us-marketplace/reference/get_v3-price-incentives",
    ),
    Operation(
        key="report_requests_list",
        method="GET",
        path="/v3/reports/reportRequests",
        fields=(
            Field("reportType", "query", required=True),
            Field("reportVersion", "query"),
            Field("requestStatus", "query", enum=("RECEIVED", "INPROGRESS", "READY", "ERROR")),
            Field("src", "query", enum=("SC", "API", "Scheduler")),
            Field("requestSubmissionStartDate", "query"),
            Field("requestSubmissionEndDate", "query"),
        ),
        source="https://developer.walmart.com/us-marketplace/reference/getrequestsstatus",
    ),

    Operation(
        key="shipping_settings_get",
        method="GET",
        path="/v3/settings/shipping",
        fields=(),
        source="https://developer.walmart.com/us-marketplace/docs/shipping-and-fulfillment-settings-api-overview",
    ),
    Operation(
        key="shipping_carriers_list",
        method="GET",
        path="/v3/shipping/labels/carriers",
        fields=(),
        source="https://developer.walmart.com/us-marketplace/reference/getcarriers",
    ),
    Operation(
        key="report_request_status_get",
        method="GET",
        path="/v3/reports/reportRequests/{requestId}",
        fields=(Field("requestId", "path", required=True),),
        source="https://developer.walmart.com/us-marketplace/reference/getsinglerequeststatus",
    ),
)


def operations_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    known = frozenset(operation.key for operation in _OPERATIONS)
    if approved_keys - known:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
    return ContractRegistry(
        tuple(
            Operation(
                key=op.key,
                method=op.method,
                path=op.path,
                fields=op.fields,
                has_body=op.has_body,
                source=op.source,
                enabled=op.key in approved_keys,
                request_schema=op.request_schema,
                request_content_type=op.request_content_type,
                body_required=op.body_required,
                media_supported=op.media_supported,
                mutating=False,
            )
            for op in _OPERATIONS
        )
    )
