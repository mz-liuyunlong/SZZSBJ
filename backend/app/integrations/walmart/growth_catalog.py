"""US Marketplace Growth (Review Accelerator Program) read-semantic contract.

Walmart exposes the Review Accelerator item list as a POST that only pages through
the enrolled / eligible / completed items with ``scrollId``; it changes nothing on
the seller account. It is the single reviewed non-GET read (owner authorization
2026-11-24): fixed path, ``scrollId`` is the only query field, and the request body
is pinned to an empty JSON object so a caller can never smuggle a filter or a write.
Enrollment, opt-out and any other Growth write stay unregistered. The 2026-11-24 second
batch adds three more read-semantic POST queries (RAP categories, assortment
recommendations and their categorization counts), all probed OK on 2026-10-08.
"""

from __future__ import annotations

from app.integrations.walmart._catalog_base import enabled_registry
from app.integrations.walmart.contracts import ContractRegistry, Field, Operation

REVIEW_ACCELERATOR_ITEMS_KEY = "review_accelerator_items"
REVIEW_ACCELERATOR_ITEMS_PATH = "/v3/growth/reviews-accelerator/items"
# The only request body the contract accepts: an empty object (no filters).
REVIEW_ACCELERATOR_EMPTY_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_FILTER_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
        "nextCursor": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}, "maxItems": 200},
        "skus": {"type": "array", "items": {"type": "string"}, "maxItems": 1000},
        "itemIds": {"type": "array", "items": {"type": "string"}, "maxItems": 1000},
        "status": {"type": "string", "maxLength": 32},
    },
    "additionalProperties": False,
}

_OPERATIONS = (
    Operation(
        key=REVIEW_ACCELERATOR_ITEMS_KEY,
        method="POST",
        path=REVIEW_ACCELERATOR_ITEMS_PATH,
        fields=(Field("scrollId", "query"),),
        has_body=True,
        body_required=True,
        request_schema=REVIEW_ACCELERATOR_EMPTY_BODY_SCHEMA,
        mutating=False,
        source=(
            "https://developer.walmart.com/us-marketplace/reference/"
            "getitemsinreviewacceleratorprogram"
        ),
    ),
    # 2026-11-24 second batch (owner: open everything probed OK): three more read-semantic
    # POST queries in the Growth family. Bodies are filter / paging objects only.
    Operation(
        key="review_accelerator_categories",
        method="POST",
        path="/v3/growth/reviews-accelerator/categories",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_FILTER_BODY_SCHEMA,
        mutating=False,
        source="https://developer.walmart.com/us-marketplace/reference/getcategoriesinrap",
    ),
    Operation(
        key="assortment_recommendations",
        method="POST",
        path="/v3/growth/assortment/recommendations",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_FILTER_BODY_SCHEMA,
        mutating=False,
        source=(
            "https://developer.walmart.com/us-marketplace/reference/getassortmentrecommendations"
        ),
    ),
    Operation(
        key="assortment_categorization_counts",
        method="POST",
        path="/v3/growth/assortment/recommendations/categorization/counts",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_FILTER_BODY_SCHEMA,
        mutating=False,
        source=(
            "https://developer.walmart.com/us-marketplace/reference/"
            "getassortmentcategorizationcounts"
        ),
    ),
)


def growth_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(_OPERATIONS, approved_keys)
