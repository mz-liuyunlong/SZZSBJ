"""US Marketplace Insights (listing quality, unpublished items, Pro Seller) read contracts.

``insights_listing_quality_items`` is a POST query (filters in the body, nothing changes on
the account); it is listed in ``READ_SEMANTIC_NON_GET_KEYS``. Its filter body is an object
whose keys are restricted to the documented filter names.
"""

from __future__ import annotations

from app.integrations.walmart._catalog_base import enabled_registry
from app.integrations.walmart.contracts import ContractRegistry, Field, Operation

_DOC = "https://developer.walmart.com/us-marketplace/docs/"
_BOOL = ("true", "false")
LISTING_QUALITY_ITEMS_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "viewTrendingItems": {"type": "boolean"},
        "wfsFlag": {"type": "boolean"},
        "hasIssue": {"type": "boolean"},
        "inDemandIndicator": {"type": "boolean"},
        "skus": {"type": "array", "items": {"type": "string"}, "maxItems": 1000},
        "productTypes": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
        "brands": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
        "nextCursor": {"type": "string"},
    },
    "additionalProperties": False,
}

_OPERATIONS = (
    Operation(
        key="insights_listing_quality_score",
        method="GET",
        path="/v3/insights/items/listingQuality/score",
        fields=(
            Field("viewTrendingItems", "query", enum=_BOOL),
            Field("wfsFlag", "query", enum=_BOOL),
        ),
        source=_DOC + "get-sellers-listing-quality-score",
    ),
    Operation(
        key="insights_listing_quality_count",
        method="GET",
        path="/v3/insights/items/listingQuality/count",
        fields=(
            Field("viewTrendingItems", "query", enum=_BOOL),
            Field("wfsFlag", "query", enum=_BOOL),
            Field("hasIssue", "query", kind="integer"),
            Field("type", "query", enum=("brand", "category")),
            Field("inDemandIndicator", "query", enum=_BOOL),
            Field("limit", "query", kind="integer", maximum=1000),
            Field("offset", "query", kind="integer"),
        ),
        source="https://developer.walmart.com/us-marketplace/reference/getcategorieslist",
    ),
    Operation(
        key="insights_listing_quality_items",
        method="POST",
        path="/v3/insights/items/listingQuality/items",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=LISTING_QUALITY_ITEMS_BODY_SCHEMA,
        mutating=False,
        source="https://developer.walmart.com/us-marketplace/reference/itemsdetailsforlisting",
    ),
    Operation(
        key="insights_unpublished_counts",
        method="GET",
        path="/v3/insights/items/unpublished/counts",
        fields=(Field("fromDate", "query"),),
        source=_DOC + "get-unpublished-item-insights",
    ),
    Operation(
        key="insights_unpublished_items",
        method="GET",
        path="/v3/insights/items/unpublished/items",
        fields=(
            Field("fromDate", "query"),
            Field(
                "unpublishedReasonCode",
                "query",
                enum=(
                    "START_DATE",
                    "END_DATE",
                    "REASONABLE_PRICE_NOT_SATISFIED",
                    "PRIMARY_IMAGE_MISSING",
                    "NO_PRICE",
                ),
            ),
            Field("limit", "query", kind="integer", maximum=1000),
            Field("offset", "query", kind="integer"),
        ),
        source=_DOC + "get-unpublished-item-insights",
    ),
    Operation(
        key="insights_seller_incentives",
        method="GET",
        path="/v3/insights/sellerIncentives",
        fields=(),
        source=_DOC + "retrieve-pro-seller-tier-status-and-reward-details",
    ),
)


def insights_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(_OPERATIONS, approved_keys)
