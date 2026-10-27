"""Fail-closed per-store SCF entrypoint for approved Walmart read operations.

Owner must deploy *one bound function and restricted role per store*. This
module does not grant access to SSM, install a proxy, or enable live mode.
All writes are disabled in this runtime until a durable approval/replay system
is separately reviewed and installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from app.integrations.walmart.cloud_executor import WalmartCloudExecutor
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.feeds_catalog import feed_monitor_registry
from app.integrations.walmart.https_transport import WalmartHttpsTransport
from app.integrations.walmart.marketplace_catalog import marketplace_read_registry
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.tencent_ssm import TencentSsmResolver
from app.integrations.walmart.wfs_catalog import wfs_registry

MAX_CONTRACT_BYTES = 2 * 1024 * 1024
_STORE_PATTERN = re.compile(r"^(?:HK|CN)[0-9]{4}$")


class ReadOnlyStorePolicy:
    def __init__(self, store_code: str, allowed_keys: frozenset[str]) -> None:
        self._store_code = store_code
        self._keys = allowed_keys

    def authorize(
        self,
        *,
        store_code: str,
        operation_key: str,
        is_write: bool,
        approval_ref: str | None,
    ) -> bool:
        return store_code == self._store_code and operation_key in self._keys and not is_write


def _load_registry(approved_keys: frozenset[str]) -> ContractRegistry:
    # Snapshot-only OpenAPI loading; arbitrary URLs and remote $ref are forbidden.
    source = os.environ.get("SZZSBJ_WALMART_CONTRACT_FILE", "")
    if not source:
        wfs_keys = set(wfs_registry().keys())
        feed_keys = set(feed_monitor_registry().keys())
        marketplace_keys = set(marketplace_read_registry().keys())
        known_keys = wfs_keys | feed_keys | marketplace_keys
        if approved_keys - known_keys:
            raise ValueError("WALMART_APPROVED_OPERATION_UNKNOWN")
        combined = (
            tuple(wfs_registry(approved_keys=approved_keys & wfs_keys)._operations.values())
            + tuple(feed_monitor_registry(approved_keys=approved_keys & feed_keys)._operations.values())
            + tuple(marketplace_read_registry(approved_keys=approved_keys & marketplace_keys)._operations.values())
        )
        return ContractRegistry(combined)
    path = Path(source)
    expected = os.environ.get("SZZSBJ_WALMART_CONTRACT_SHA256", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or not path.is_file():
        raise ValueError("CONTRACT_SNAPSHOT_NOT_APPROVED")
    if path.stat().st_size > MAX_CONTRACT_BYTES:
        raise ValueError("CONTRACT_SNAPSHOT_TOO_LARGE")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("CONTRACT_SNAPSHOT_CHANGED")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("CONTRACT_SNAPSHOT_INVALID")
    return ContractRegistry.from_openapi(parsed, approved_keys=approved_keys)


def main_handler(event: object, context: object) -> dict[str, Any]:
    """Tencent SCF handler; no raw error details, bodies, keys or tokens."""
    if isinstance(event, dict) and event.get("operation") == "health":
        return {"success": True, "status": "SAFE_RUNTIME_AVAILABLE"}
    if os.environ.get("SZZSBJ_WALMART_LIVE_MODE") != "owner-approved-read-only":
        return {"success": False, "status": "WALMART_LIVE_DISABLED"}
    store = os.environ.get("SZZSBJ_WALMART_BOUND_STORE", "")
    if not _STORE_PATTERN.fullmatch(store):
        return {"success": False, "status": "WALMART_STORE_BINDING_MISSING"}
    try:
        approved = frozenset(
            item.strip()
            for item in os.environ.get("SZZSBJ_WALMART_APPROVED_READ_KEYS", "").split(",")
            if item.strip()
        )
        if not approved:
            raise ValueError("WALMART_APPROVAL_MISSING")
        mapping = json.loads(os.environ.get("SZZSBJ_WALMART_PRIVATE_PROXIES", "{}"))
        if not isinstance(mapping, dict) or set(mapping) != {store}:
            raise ValueError("WALMART_EGRESS_MISSING")
        registry = _load_registry(approved)
        secrets = TencentSsmResolver(
            TencentApiClient(TemporaryTencentIdentity.from_environment()),
            approved_stores=frozenset({store}),
            version=os.environ.get("SZZSBJ_WALMART_SECRET_VERSION", "v1"),
        )
        transport = WalmartHttpsTransport(proxy_by_store=mapping, secret_resolver=secrets)
        policy = ReadOnlyStorePolicy(store, approved)
        executor = WalmartCloudExecutor(
            registry=registry,
            store_allowlist=frozenset({store}),
            policy=policy,
            transport=transport,
        )
        return executor.handle(event)
    except Exception:
        return {"success": False, "status": "WALMART_RUNTIME_UNAVAILABLE"}
