"""US Marketplace read-only operation catalog, grounded in official API docs.

Only explicitly approved operation keys can execute. This is not the complete
Walmart API catalog; it intentionally excludes all writes, feeds submission,
multipart upload and Walmart Connect advertising.
"""
from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation

_MARKETPLACE = (
    Operation(
        key="items_list",
        method="GET",
        path="/v3/items",
        fields=(
            Field("nextCursor", "query"),
            Field("sku", "query"),
            Field("offset", "query", kind="integer"),
            Field("limit", "query", kind="integer", maximum=50),
            Field("lifecycleStatus", "query", enum=("ACTIVE", "ARCHIVED", "RETIRED")),
            Field("publishedStatus", "query", enum=("PUBLISHED", "UNPUBLISHED")),
            Field("variantGroupId", "query"),
            Field("includeDetails", "query", kind="boolean"),
        ),
        source="https://developer.walmart.com/us-marketplace/docs/get-item-details",
    ),
    Operation(
        key="item_get",
        method="GET",
        path="/v3/items/{itemId}",
        fields=(
            Field("itemId", "path", required=True),
            Field("productIdType", "query", enum=("GTIN", "UPC", "EAN", "ISBN", "SKU", "ITEM_ID")),
        ),
        source="https://developer.walmart.com/us-marketplace/docs/get-item-details",
    ),
    Operation(
        key="items_search",
        method="GET",
        path="/v3/items/walmart/search",
        fields=(
            Field("query", "query"),
            Field("upc", "query"),
            Field("gtin", "query"),
            Field("limit", "query", kind="integer", maximum=50),
        ),
        source="https://developer.walmart.com/us-marketplace/docs/get-item-details",
    ),
    Operation(
        key="orders_list",
        method="GET",
        path="/v3/orders",
        fields=(
            Field("createdStartDate", "query", required=True),
            Field("createdEndDate", "query"),
            Field("fromExpectedShipDate", "query"),
            Field("toExpectedShipDate", "query"),
            Field("sku", "query"),
            Field("customerOrderId", "query"),
            Field("purchaseOrderId", "query"),
            Field("status", "query", enum=("Created", "Acknowledged", "Shipped", "Delivered", "Cancelled")),
            Field("limit", "query", kind="integer", maximum=200),
            Field("cursor", "query"),
        ),
        source="https://developer.walmart.com/us-marketplace/docs/retrieve-and-acknowledge-orders",
    ),
    Operation(
        key="orders_released",
        method="GET",
        path="/v3/orders/released",
        fields=(
            Field("limit", "query", kind="integer", maximum=100),
            Field("productInfo", "query", kind="boolean"),
            Field("shipNodeType", "query"),
            Field("replacementInfo", "query", kind="boolean"),
        ),
        source="https://developer.walmart.com/us-marketplace/docs/get-all-released-orders",
    ),
    Operation(
        key="order_get",
        method="GET",
        path="/v3/orders/{purchaseOrderId}",
        fields=(Field("purchaseOrderId", "path", required=True),),
        source="https://developer.walmart.com/us-marketplace/docs/retrieve-and-acknowledge-orders",
    ),
)


def marketplace_read_registry(
    *, approved_keys: frozenset[str] = frozenset()
) -> ContractRegistry:
    known = frozenset(operation.key for operation in _MARKETPLACE)
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
            )
            for op in _MARKETPLACE
        )
    )
