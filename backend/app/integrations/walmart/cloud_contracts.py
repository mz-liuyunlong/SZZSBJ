"""Contracts the cloud function itself trusts for every non-GET call (审核 #358 P1-1).

A signed v3 contract is enough for a GET (a GET cannot change seller data, and adding a
read only needs a server registry entry). A non-GET — a read-semantic POST query or a
write — must also equal, field by field, the reviewed contract built into this package:
method, path template, fields, body flags, request schema, content type, mutating and
response kind. Otherwise a server could sign a contract that keeps a read-only key but
points it at a write path, or widens the body schema, and run it under the read ceiling.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.integrations.walmart.contracts import (
    ContractError,
    ContractRegistry,
    Operation,
    contract_dict,
)
from app.integrations.walmart.feeds_catalog import feed_monitor_registry
from app.integrations.walmart.growth_catalog import growth_read_registry
from app.integrations.walmart.insights_catalog import insights_read_registry
from app.integrations.walmart.marketplace_catalog import marketplace_read_registry
from app.integrations.walmart.misc_catalog import misc_read_registry
from app.integrations.walmart.operations_catalog import operations_read_registry
from app.integrations.walmart.payment_catalog import payment_read_registry
from app.integrations.walmart.recon_catalog import recon_read_registry
from app.integrations.walmart.reports_catalog import reports_registry
from app.integrations.walmart.returns_catalog import returns_read_registry
from app.integrations.walmart.sem_catalog import (
    SEM_WRITE_KEYS,
    sem_read_registry,
    sem_write_registry,
)
from app.integrations.walmart.wfs_catalog import wfs_registry
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS, wfs_write_registry

# Every built-in read catalog (legacy v1/v2 events build their registry from these too).
READ_FACTORIES = (
    wfs_registry,
    feed_monitor_registry,
    marketplace_read_registry,
    returns_read_registry,
    operations_read_registry,
    growth_read_registry,
    recon_read_registry,
    reports_registry,
    payment_read_registry,
    insights_read_registry,
    sem_read_registry,
    misc_read_registry,
)

# Contract keys that identify *what* is called; source / family / permission /
# registry_version are server bookkeeping and may differ.
_PINNED = (
    "key",
    "method",
    "path",
    "fields",
    "has_body",
    "body_required",
    "request_content_type",
    "request_schema",
    "media_supported",
    "mutating",
    "response_kind",
)


@lru_cache(maxsize=1)
def builtin_non_get_registry() -> ContractRegistry:
    """All reviewed non-GET contracts in this package, enabled (reads and writes)."""
    operations: dict[str, Operation] = {}
    factories: list[Any] = [(f, None) for f in READ_FACTORIES]
    factories += [(wfs_write_registry, WFS_WRITE_KEYS), (sem_write_registry, SEM_WRITE_KEYS)]
    for factory, write_keys in factories:
        keys = frozenset(factory().keys()) if write_keys is None else write_keys
        for key, operation in factory(approved_keys=keys)._operations.items():
            if operation.method == "GET":
                continue
            if key in operations:
                raise ValueError("WALMART_OPERATION_COLLISION")
            operations[key] = operation
    return ContractRegistry(tuple(operations.values()))


def pinned_shape(contract: Any) -> dict[str, Any]:
    return {name: contract.get(name) for name in _PINNED} if isinstance(contract, dict) else {}


def builtin_for(contract: Any, registry: ContractRegistry | None = None) -> Operation:
    """The package's own contract for a non-GET call; raise if the signed one differs."""
    registry = registry or builtin_non_get_registry()
    key = contract.get("key") if isinstance(contract, dict) else None
    if not isinstance(key, str) or key not in registry.keys():
        raise ContractError("WALMART_CONTRACT_MISMATCH")
    builtin = registry.get(key)
    if pinned_shape(contract_dict(builtin)) != pinned_shape(contract):
        raise ContractError("WALMART_CONTRACT_MISMATCH")
    return builtin
