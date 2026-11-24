"""US Marketplace Growth (Review Accelerator Program) read-semantic contract.

Walmart exposes the Review Accelerator item list as a POST that only pages through
the enrolled / eligible / completed items with ``scrollId``; it changes nothing on
the seller account. It is the single reviewed non-GET read (owner authorization
2026-11-24): fixed path, ``scrollId`` is the only query field, and the request body
is pinned to an empty JSON object so a caller can never smuggle a filter or a write.
Enrollment, opt-out and any other Growth write stay unregistered.
"""

from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation

REVIEW_ACCELERATOR_ITEMS_KEY = "review_accelerator_items"
REVIEW_ACCELERATOR_ITEMS_PATH = "/v3/growth/reviews-accelerator/items"
# The only request body the contract accepts: an empty object (no filters).
REVIEW_ACCELERATOR_EMPTY_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {},
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
)


def growth_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    known = frozenset(operation.key for operation in _OPERATIONS)
    if approved_keys - known:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
    return ContractRegistry(
        tuple(
            Operation(
                key=operation.key,
                method=operation.method,
                path=operation.path,
                fields=operation.fields,
                has_body=operation.has_body,
                source=operation.source,
                enabled=operation.key in approved_keys,
                request_schema=operation.request_schema,
                request_content_type=operation.request_content_type,
                body_required=operation.body_required,
                media_supported=operation.media_supported,
                mutating=operation.mutating,
                response_kind=operation.response_kind,
            )
            for operation in _OPERATIONS
        )
    )
