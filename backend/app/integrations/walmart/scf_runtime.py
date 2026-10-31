"""Fail-closed per-store SCF entrypoint for approved Walmart operations.

Owner must deploy *one bound function and restricted role per store*. This
module does not grant access to SSM, install a proxy, or enable live mode.
Writes stay disabled unless the owner deploys the function with
``SZZSBJ_WALMART_LIVE_MODE=owner-approved-read-write`` and lists the reviewed
WFS write keys in ``SZZSBJ_WALMART_APPROVED_WRITE_KEYS``; every write event must
also carry a non-empty ``approval_ref`` (the caller's audit reference).

Protocol v3 (signed contracts) is enabled by ``SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS``
(JSON ``{"kid": "<base64 Ed25519 public key>"}``). In that mode the per-operation
allowlists above are not consulted; the only per-store switch is
``SZZSBJ_WALMART_MAX_RISK`` ("read" by default, "write" only together with the
read-write live mode). v1/v2 events keep working unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from app.integrations.walmart.cloud_executor import RISK_LEVELS, WalmartCloudExecutor
from app.integrations.walmart.contract_signing import ContractVerifier, ReplayCache
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.feeds_catalog import feed_monitor_registry
from app.integrations.walmart.https_transport import WalmartHttpsTransport
from app.integrations.walmart.marketplace_catalog import marketplace_read_registry
from app.integrations.walmart.operations_catalog import operations_read_registry
from app.integrations.walmart.returns_catalog import returns_read_registry
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.tencent_ssm import TencentSsmResolver
from app.integrations.walmart.wfs_catalog import wfs_registry
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS, wfs_write_registry

MAX_CONTRACT_BYTES = 2 * 1024 * 1024
_STORE_PATTERN = re.compile(r"^(?:HK|CN)[0-9]{4}$")
LIVE_MODE_READ_ONLY = "owner-approved-read-only"
LIVE_MODE_READ_WRITE = "owner-approved-read-write"
PUBLIC_KEYS_ENV = "SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS"
MAX_RISK_ENV = "SZZSBJ_WALMART_MAX_RISK"
# Tencent SCF exports the function's own name; the owner may pin it explicitly instead.
FUNCTION_NAME_ENV = "SZZSBJ_WALMART_FUNCTION_NAME"
_SCF_FUNCTION_NAME_ENV = "SCF_FUNCTIONNAME"
# One replay cache per warm instance (see contract_signing.ReplayCache).
_REPLAY = ReplayCache()


def _function_name_from_env() -> str:
    return (
        os.environ.get(FUNCTION_NAME_ENV, "").strip()
        or os.environ.get(_SCF_FUNCTION_NAME_ENV, "").strip()
    )


def _verifier_from_env(store: str) -> ContractVerifier | None:
    raw = os.environ.get(PUBLIC_KEYS_ENV, "").strip()
    if not raw:
        return None
    return ContractVerifier.from_env_json(
        raw, bound_store=store, bound_function=_function_name_from_env(), replay=_REPLAY
    )


def _max_risk_from_env(write_mode: bool) -> str:
    """Per-store ceiling; "write" needs the read-write live mode as well (defense in depth)."""
    value = os.environ.get(MAX_RISK_ENV, "read").strip() or "read"
    if value not in RISK_LEVELS:
        raise ValueError("WALMART_RISK_CEILING_INVALID")
    return "write" if value == "write" and write_mode else "read"


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


class StoreWritePolicy:
    """Read keys as before; a write needs its key in the write set *and* an approval_ref."""

    def __init__(
        self, store_code: str, read_keys: frozenset[str], write_keys: frozenset[str]
    ) -> None:
        self._store_code = store_code
        self._read_keys = read_keys
        self._write_keys = write_keys

    def authorize(
        self,
        *,
        store_code: str,
        operation_key: str,
        is_write: bool,
        approval_ref: str | None,
    ) -> bool:
        if store_code != self._store_code:
            return False
        if not is_write:
            return operation_key in self._read_keys
        return (
            operation_key in self._write_keys
            and isinstance(approval_ref, str)
            and 1 <= len(approval_ref) <= 128
        )


def _load_registry(
    approved_keys: frozenset[str], approved_write_keys: frozenset[str] = frozenset()
) -> ContractRegistry:
    # Snapshot-only OpenAPI loading; arbitrary URLs and remote $ref are forbidden.
    if approved_write_keys - WFS_WRITE_KEYS or approved_keys & WFS_WRITE_KEYS:
        raise ValueError("WALMART_WRITE_NOT_AUTHORIZED")
    source = os.environ.get("SZZSBJ_WALMART_CONTRACT_FILE", "")
    if not source:
        wfs_keys = set(wfs_registry().keys())
        feed_keys = set(feed_monitor_registry().keys())
        marketplace_keys = set(marketplace_read_registry().keys())
        returns_keys = set(returns_read_registry().keys())
        operations_keys = set(operations_read_registry().keys())
        known_keys = wfs_keys | feed_keys | marketplace_keys | returns_keys | operations_keys
        if approved_keys - known_keys:
            raise ValueError("WALMART_APPROVED_OPERATION_UNKNOWN")
        combined = (
            tuple(wfs_registry(approved_keys=approved_keys & wfs_keys)._operations.values())
            + tuple(
                feed_monitor_registry(approved_keys=approved_keys & feed_keys)._operations.values()
            )
            + tuple(
                marketplace_read_registry(
                    approved_keys=approved_keys & marketplace_keys
                )._operations.values()
            )
            + tuple(
                returns_read_registry(
                    approved_keys=approved_keys & returns_keys
                )._operations.values()
            )
            + tuple(
                operations_read_registry(
                    approved_keys=approved_keys & operations_keys
                )._operations.values()
            )
            + tuple(wfs_write_registry(approved_keys=approved_write_keys)._operations.values())
        )
        return ContractRegistry(combined)
    if approved_write_keys:
        # Writes are only reviewed as built-in contracts; a snapshot cannot enable them.
        raise ValueError("WALMART_WRITE_NOT_AUTHORIZED")
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
    live_mode = os.environ.get("SZZSBJ_WALMART_LIVE_MODE")
    if live_mode not in (LIVE_MODE_READ_ONLY, LIVE_MODE_READ_WRITE):
        return {"success": False, "status": "WALMART_LIVE_DISABLED"}
    write_mode = live_mode == LIVE_MODE_READ_WRITE
    store = os.environ.get("SZZSBJ_WALMART_BOUND_STORE", "")
    if not _STORE_PATTERN.fullmatch(store):
        return {"success": False, "status": "WALMART_STORE_BINDING_MISSING"}
    signed = isinstance(event, dict) and event.get("version") == 3
    try:
        verifier = _verifier_from_env(store)
        if signed and verifier is None:
            return {"success": False, "status": "WALMART_PROTOCOL_NOT_ENABLED"}
        approved = frozenset(
            item.strip()
            for item in os.environ.get("SZZSBJ_WALMART_APPROVED_READ_KEYS", "").split(",")
            if item.strip()
        )
        if not approved and not signed:
            raise ValueError("WALMART_APPROVAL_MISSING")
        approved_write: frozenset[str] = frozenset()
        if write_mode:
            approved_write = frozenset(
                item.strip()
                for item in os.environ.get("SZZSBJ_WALMART_APPROVED_WRITE_KEYS", "").split(",")
                if item.strip()
            )
        mapping = json.loads(os.environ.get("SZZSBJ_WALMART_PRIVATE_PROXIES", "{}"))
        if not isinstance(mapping, dict) or set(mapping) != {store}:
            raise ValueError("WALMART_EGRESS_MISSING")
        # v3 rebuilds the operation from the signed contract; the legacy registry is only
        # needed for v1/v2 events.
        registry = ContractRegistry(()) if signed else _load_registry(approved, approved_write)
        secrets = TencentSsmResolver(
            TencentApiClient(TemporaryTencentIdentity.from_environment()),
            approved_stores=frozenset({store}),
            version=os.environ.get("SZZSBJ_WALMART_SECRET_VERSION", "v1"),
        )
        transport = WalmartHttpsTransport(
            proxy_by_store=mapping,
            secret_resolver=secrets,
            timeout=90.0 if (write_mode or signed) else 12.0,
            pass_provider_errors=write_mode or signed,
        )
        policy: ReadOnlyStorePolicy | StoreWritePolicy
        if write_mode:
            policy = StoreWritePolicy(store, approved, approved_write)
        else:
            policy = ReadOnlyStorePolicy(store, approved)
        executor = WalmartCloudExecutor(
            registry=registry,
            store_allowlist=frozenset({store}),
            policy=policy,
            transport=transport,
            verifier=verifier,
            max_risk=_max_risk_from_env(write_mode),
        )
        return executor.handle(event)
    except Exception:
        return {"success": False, "status": "WALMART_RUNTIME_UNAVAILABLE"}
