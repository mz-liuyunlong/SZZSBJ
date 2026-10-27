"""Reusable Walmart read API entrypoint for SZZSBJ (fail-closed).

The historical 192-capability inventory is discovery-only. Calls require a
reviewed built-in contract or SHA256-pinned OpenAPI snapshot, a per-operation
approval, and an independently authorized per-store SCF gateway.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.collector import CollectorConfig, WalmartReadCollector
from app.integrations.walmart.contracts import ContractRegistry, Operation, PreparedRequest
from app.integrations.walmart.feeds_catalog import feed_monitor_registry
from app.integrations.walmart.marketplace_catalog import marketplace_read_registry
from app.integrations.walmart.operations_catalog import operations_read_registry
from app.integrations.walmart.pagination import PageContract, collect_read_pages
from app.integrations.walmart.returns_catalog import returns_read_registry
from app.integrations.walmart.source_catalog_data import load_source_catalog
from app.integrations.walmart.wfs_catalog import wfs_registry

MAX_CONTRACT_BYTES = 2 * 1024 * 1024


class WalmartIntegrationError(ValueError):
    """Stable failure codes only; never include contract contents or secrets."""


def _builtins(approved_keys: frozenset[str]) -> dict[str, Operation]:
    factories = (
        wfs_registry,
        feed_monitor_registry,
        marketplace_read_registry,
        returns_read_registry,
        operations_read_registry,
    )
    operations: dict[str, Operation] = {}
    for factory in factories:
        known = factory().keys()
        accepted = approved_keys.intersection(known)
        for key, operation in factory(approved_keys=frozenset(accepted))._operations.items():
            if key in operations:
                raise WalmartIntegrationError("WALMART_OPERATION_COLLISION")
            operations[key] = operation
    return operations


def load_unified_registry(
    approved_keys: frozenset[str] = frozenset(),
    *,
    contract_file: str | None = None,
    contract_sha256: str | None = None,
) -> ContractRegistry:
    """Build a single registry; no live requests or implicit approvals.

    An additional owner-reviewed OpenAPI 3.x snapshot can provide more
    operations without editing the SDK. Its exact bytes MUST be SHA256-pinned.
    A snapshot may refine a built-in operation only if method/path are equal.
    No write operation can be approved through this read-only factory.
    """
    if not isinstance(approved_keys, frozenset) or not all(
        isinstance(key, str) for key in approved_keys
    ):
        raise WalmartIntegrationError("WALMART_APPROVED_KEYS_INVALID")
    merged = _builtins(approved_keys)
    if contract_file is not None or contract_sha256 is not None:
        if (
            not contract_file
            or not isinstance(contract_sha256, str)
            or not re.fullmatch(r"[a-fA-F0-9]{64}", contract_sha256)
        ):
            raise WalmartIntegrationError("CONTRACT_SNAPSHOT_NOT_APPROVED")
        path = Path(contract_file)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_CONTRACT_BYTES:
            raise WalmartIntegrationError("CONTRACT_SNAPSHOT_NOT_APPROVED")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != contract_sha256.lower():
            raise WalmartIntegrationError("CONTRACT_SNAPSHOT_CHANGED")
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise WalmartIntegrationError("CONTRACT_SNAPSHOT_INVALID") from None
        imported = ContractRegistry.from_openapi(parsed, approved_keys=frozenset())
        for key, op in imported._operations.items():
            existing = merged.get(key)
            if existing is not None and (existing.method != op.method or existing.path != op.path):
                raise WalmartIntegrationError("WALMART_OPERATION_COLLISION")
            # Explicit approval must still be applied to the imported contract.
            merged[key] = Operation(
                key=op.key,
                method=op.method,
                path=op.path,
                fields=op.fields,
                has_body=op.has_body,
                source=op.source,
                enabled=key in approved_keys,
                request_schema=op.request_schema,
                request_content_type=op.request_content_type,
                body_required=op.body_required,
                media_supported=op.media_supported,
                mutating=op.mutating,
            )
    unknown = approved_keys.difference(merged)
    if unknown:
        raise WalmartIntegrationError("WALMART_APPROVED_OPERATION_UNKNOWN")
    if any(op.enabled and op.is_write for op in merged.values()):
        raise WalmartIntegrationError("WALMART_WRITE_NOT_AUTHORIZED")
    return ContractRegistry(tuple(merged.values()))


def capability_summary(registry: ContractRegistry | None = None) -> dict[str, Any]:
    """Describe catalog coverage without conflating discovery and execution."""
    source = load_source_catalog()
    declared = registry or load_unified_registry()
    paths = {(op.method, op.path) for op in declared._operations.values()}
    category_counts = Counter(str(row["category"]) for row in source)
    return {
        "source_capabilities": len(source),
        "physical_endpoints": len({(str(row["method"]), str(row["path"])) for row in source}),
        "historical_categories": dict(category_counts),
        "reviewed_contracts": len(declared.keys()),
        "approved_read_operations": sum(
            op.enabled and not op.is_write for op in declared._operations.values()
        ),
        "historical_paths_with_contract": sum(
            (str(row["method"]), str(row["path"])) in paths for row in source
        ),
        "live_enabled": False,
        "notice": "Catalog coverage and approval are not live API validation.",
    }


class WalmartReadAPI:
    """One business-facing read API; gateway/store/contract policy stay external."""

    def __init__(self, client: WalmartClient) -> None:
        self._client = client

    def prepare(
        self, store_code: str, operation: str, *, params: Mapping[str, Any] | None = None
    ) -> PreparedRequest:
        request = self._client.prepare(store_code, operation, params=params, allow_writes=False)
        if request.is_write:
            raise WalmartIntegrationError("WALMART_WRITE_NOT_AUTHORIZED")
        return request

    def call(
        self, store_code: str, operation: str, *, params: Mapping[str, Any] | None = None
    ) -> WalmartResult:
        self.prepare(store_code, operation, params=params)
        return self._client.call(store_code, operation, params=params, allow_writes=False)

    def pages(
        self,
        store_code: str,
        *,
        contract: PageContract,
        params: Mapping[str, Any] | None = None,
        page_size: int = 50,
        max_pages: int = 50,
        max_items: int = 2500,
    ) -> tuple[dict[str, Any], ...]:
        self.prepare(store_code, contract.operation, params=params)
        return collect_read_pages(
            self._client,
            store_code=store_code,
            contract=contract,
            params=params,
            page_size=page_size,
            max_pages=max_pages,
            max_items=max_items,
        )

    def original_worker(
        self,
        store_code: str,
        *,
        endpoints: tuple[str, ...],
        from_date: Any,
        to_date: Any,
        gtin_items: Any = None,
        config: CollectorConfig | None = None,
    ) -> dict[str, Any]:
        """Reuse the existing four-endpoint collector and its artifact checks."""
        return WalmartReadCollector(self._client, store_code=store_code, config=config).collect(
            endpoints=endpoints,
            from_date=from_date,
            to_date=to_date,
            gtin_items=gtin_items,
        )
