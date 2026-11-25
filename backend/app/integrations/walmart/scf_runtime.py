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

Protocol v4 authenticates trusted internal requests with the same public keys
and per-store binding, without interpreting legacy business allowlists or risk
ceilings. The existing live-mode and approved network route remain required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from app.integrations.walmart.cloud_contracts import READ_FACTORIES
from app.integrations.walmart.cloud_executor import RISK_LEVELS, WalmartCloudExecutor
from app.integrations.walmart.contract_signing import (
    ContractVerifier,
    FileReplayStore,
    MemoryReplayStore,
    RedisReplayStore,
    ReplayStore,
)
from app.integrations.walmart.contracts import ContractRegistry, Operation
from app.integrations.walmart.direct_readonly_transport import WalmartDirectReadOnlyTransport
from app.integrations.walmart.generic_executor import execute_generic_event
from app.integrations.walmart.generic_protocol import VERSION as GENERIC_VERSION
from app.integrations.walmart.generic_transport import WalmartGenericTransport
from app.integrations.walmart.https_transport import WalmartHttpsTransport
from app.integrations.walmart.sem_catalog import SEM_WRITE_KEYS, sem_write_registry
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.tencent_ssm import TencentSsmResolver
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS, wfs_write_registry

MAX_CONTRACT_BYTES = 2 * 1024 * 1024
_STORE_PATTERN = re.compile(r"^(?:HK|CN)[0-9]{4}$")
LIVE_MODE_READ_ONLY = "owner-approved-read-only"
LIVE_MODE_READ_WRITE = "owner-approved-read-write"
PUBLIC_KEYS_ENV = "SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS"
MAX_RISK_ENV = "SZZSBJ_WALMART_MAX_RISK"
EGRESS_MODE_ENV = "SZZSBJ_WALMART_EGRESS_MODE"
DIRECT_APPROVED_ENV = "SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED"
# Tencent SCF exports the function's own name; the owner may pin it explicitly instead.
FUNCTION_NAME_ENV = "SZZSBJ_WALMART_FUNCTION_NAME"
_SCF_FUNCTION_NAME_ENV = "SCF_FUNCTIONNAME"
# Cross-instance replay store for writes: a CFS directory mounted into every instance
# (SZZSBJ_WALMART_REPLAY_DIR) or a Redis URL (SZZSBJ_WALMART_REPLAY_REDIS_URL). Without
# either, only the per-instance memory store exists and the executor refuses writes.
REPLAY_DIR_ENV = "SZZSBJ_WALMART_REPLAY_DIR"
REPLAY_REDIS_ENV = "SZZSBJ_WALMART_REPLAY_REDIS_URL"
_MEMORY_REPLAY = MemoryReplayStore()
_REPLAY_CACHE: dict[str, ReplayStore] = {}


def _replay_store_from_env() -> ReplayStore:
    directory = os.environ.get(REPLAY_DIR_ENV, "").strip()
    redis_url = os.environ.get(REPLAY_REDIS_ENV, "").strip()
    cache_key = f"dir={directory}|redis={bool(redis_url)}"
    store = _REPLAY_CACHE.get(cache_key)
    if store is not None:
        return store
    if directory:
        store = FileReplayStore(directory)
    elif redis_url:
        import redis  # optional dependency of the cloud bundle only

        store = RedisReplayStore(redis.Redis.from_url(redis_url, socket_timeout=2.0))
    else:
        store = _MEMORY_REPLAY
    _REPLAY_CACHE[cache_key] = store
    return store


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
        raw,
        bound_store=store,
        bound_function=_function_name_from_env(),
        replay=_replay_store_from_env(),
    )


def _max_risk_from_env(write_mode: bool) -> str:
    """Per-store ceiling; "write" needs the read-write live mode as well (defense in depth)."""
    value = os.environ.get(MAX_RISK_ENV, "read").strip() or "read"
    if value not in RISK_LEVELS:
        raise ValueError("WALMART_RISK_CEILING_INVALID")
    return "write" if value == "write" and write_mode else "read"


def _transport_from_env(
    *, store: str, secrets: TencentSsmResolver, signed: bool, write_mode: bool
) -> WalmartHttpsTransport | WalmartDirectReadOnlyTransport:
    """Keep private proxy as default. Direct public egress is explicitly read-only.

    Existing SCF v1 functions used direct-public-readonly. A v3 signed GET may use
    that same approved network path; a non-GET is denied in the executor *and*
    in WalmartDirectReadOnlyTransport, regardless of the signed contract.
    """
    mode = os.environ.get(EGRESS_MODE_ENV, "").strip()
    if mode == "direct-public-readonly":
        if os.environ.get(DIRECT_APPROVED_ENV) != "1" or write_mode:
            raise ValueError("WALMART_DIRECT_WRITE_DENIED")
        return WalmartDirectReadOnlyTransport(
            bound_store=store,
            secret_resolver=secrets,
            timeout=12.0,
            pass_provider_errors=signed,
        )
    if mode not in ("", "private-proxy"):
        raise ValueError("WALMART_EGRESS_NOT_APPROVED")
    mapping = json.loads(os.environ.get("SZZSBJ_WALMART_PRIVATE_PROXIES", "{}"))
    if not isinstance(mapping, dict) or set(mapping) != {store}:
        raise ValueError("WALMART_EGRESS_MISSING")
    return WalmartHttpsTransport(
        proxy_by_store=mapping,
        secret_resolver=secrets,
        timeout=90.0 if (write_mode or signed) else 12.0,
        pass_provider_errors=write_mode or signed,
    )


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
    all_write_keys = WFS_WRITE_KEYS | SEM_WRITE_KEYS
    if approved_write_keys - all_write_keys or approved_keys & all_write_keys:
        raise ValueError("WALMART_WRITE_NOT_AUTHORIZED")
    source = os.environ.get("SZZSBJ_WALMART_CONTRACT_FILE", "")
    if not source:
        combined: list[Operation] = []
        known_keys: set[str] = set()
        for factory in READ_FACTORIES:
            keys = set(factory().keys())
            known_keys |= keys
            combined.extend(factory(approved_keys=approved_keys & keys)._operations.values())
        if approved_keys - known_keys:
            raise ValueError("WALMART_APPROVED_OPERATION_UNKNOWN")
        combined.extend(
            wfs_write_registry(
                approved_keys=approved_write_keys & WFS_WRITE_KEYS
            )._operations.values()
        )
        combined.extend(
            sem_write_registry(
                approved_keys=approved_write_keys & SEM_WRITE_KEYS
            )._operations.values()
        )
        return ContractRegistry(tuple(combined))
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


def _generic_transport_from_env(
    *, store: str, secrets: TencentSsmResolver
) -> WalmartGenericTransport:
    """Reuse the approved network route, not the legacy business risk mode."""
    mode = os.environ.get(EGRESS_MODE_ENV, "").strip()
    if mode == "direct-public-readonly":
        if os.environ.get(DIRECT_APPROVED_ENV) != "1":
            raise ValueError("WALMART_EGRESS_NOT_APPROVED")
        return WalmartGenericTransport(bound_store=store, secret_resolver=secrets)
    if mode not in ("", "private-proxy"):
        raise ValueError("WALMART_EGRESS_NOT_APPROVED")
    mapping = json.loads(os.environ.get("SZZSBJ_WALMART_PRIVATE_PROXIES", "{}"))
    if not isinstance(mapping, dict) or set(mapping) != {store}:
        raise ValueError("WALMART_EGRESS_MISSING")
    return WalmartGenericTransport(bound_store=store, secret_resolver=secrets, proxy=mapping[store])


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
    generic = isinstance(event, dict) and event.get("version") == GENERIC_VERSION
    signed = isinstance(event, dict) and event.get("version") == 3
    try:
        verifier = _verifier_from_env(store)
        if generic:
            if verifier is None:
                return {"success": False, "status": "WALMART_PROTOCOL_NOT_ENABLED"}
            secrets = TencentSsmResolver(
                TencentApiClient(TemporaryTencentIdentity.from_environment()),
                approved_stores=frozenset({store}),
                version=os.environ.get("SZZSBJ_WALMART_SECRET_VERSION", "v1"),
            )
            return execute_generic_event(
                event,
                verifier=verifier,
                store=store,
                transport=_generic_transport_from_env(store=store, secrets=secrets),
            )
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
        # v3 rebuilds the operation from the signed contract; the legacy registry is only
        # needed for v1/v2 events.
        registry = ContractRegistry(()) if signed else _load_registry(approved, approved_write)
        secrets = TencentSsmResolver(
            TencentApiClient(TemporaryTencentIdentity.from_environment()),
            approved_stores=frozenset({store}),
            version=os.environ.get("SZZSBJ_WALMART_SECRET_VERSION", "v1"),
        )
        transport = _transport_from_env(
            store=store, secrets=secrets, signed=signed, write_mode=write_mode
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
