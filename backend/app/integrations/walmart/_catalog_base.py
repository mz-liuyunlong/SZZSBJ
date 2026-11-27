"""Shared helper for the small read catalogs: copy operations with an ``enabled`` flag."""

from __future__ import annotations

from collections.abc import Iterable

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Operation


def enabled_registry(
    operations: Iterable[Operation], approved_keys: frozenset[str]
) -> ContractRegistry:
    operations = tuple(operations)
    known = frozenset(operation.key for operation in operations)
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
            for operation in operations
        )
    )
