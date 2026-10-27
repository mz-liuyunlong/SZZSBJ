"""US Marketplace Returns API read-only contracts.

Return approval, rejection and refund operations are deliberately excluded:
they have financial/customer impact and require a separately reviewed write gate.
"""
from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation


_OPERATIONS = (
    Operation(
        key="returns_list",
        method="GET",
        path="/v3/returns",
        fields=(
            Field("returnOrderId", "query"),
            Field("customerOrderId", "query"),
            Field("status", "query", enum=("INITIATED", "DELIVERED", "COMPLETED")),
            Field("replacementInfo", "query", kind="boolean"),
            Field("returnType", "query", enum=("PREORDER", "REPLACEMENT", "REFUND")),
            Field("isWFSEnabled", "query", enum=("Y", "N")),
            Field("returnCreationStartDate", "query"),
            Field("returnCreationEndDate", "query"),
            Field("returnLastModifiedStartDate", "query"),
            Field("returnLastModifiedEndDate", "query"),
            Field("limit", "query", kind="integer", maximum=200),
        ),
        source="https://developer.walmart.com/us-marketplace/reference/getreturns",
    ),
    Operation(
        key="return_get",
        method="GET",
        path="/v3/returns/{returnOrderId}",
        fields=(Field("returnOrderId", "path", required=True),),
        source="https://developer.walmart.com/us-marketplace/docs/returns-and-refunds-api-overview",
    ),
)


def returns_read_registry(
    *, approved_keys: frozenset[str] = frozenset()
) -> ContractRegistry:
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
            )
            for operation in _OPERATIONS
        )
    )
