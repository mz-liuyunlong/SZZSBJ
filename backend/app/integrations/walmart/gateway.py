"""Unified Walmart gateway for SZZSBJ business modules (handover chapter 76).

One entry point for every reviewed Walmart operation:

    gateway.call(store_code, operation_key, params=..., body=..., actor=..., approval_ref=...)
    gateway.pages(store_code, operation_key, contract=PageContract(...), actor=...)
    gateway.call_many(store_codes, operation_key, params=..., actor=...)

Authorization is decided here, on the server, from the operation's business permission
and the actor's store scope; the per-store cloud function re-validates the signed
contract and applies its risk ceiling (protocol v3). Nothing in this module reads or
holds Walmart credentials, and every call (success or failure) is handed to the audit
sink as a ``CallRecord`` without request or response bodies.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.contract_signing import ContractSigner, request_sha256
from app.integrations.walmart.contracts import (
    ContractError,
    ContractRegistry,
    Operation,
    sha256_hex,
)
from app.integrations.walmart.pagination import PageContract, PaginationRejected, collect_read_pages
from app.integrations.walmart.planner import STORE_ROUTES
from app.integrations.walmart.unified_api import reviewed_registry

logger = logging.getLogger("szzsbj.walmart.gateway")

_APPROVAL = re.compile(r"^[^\x00-\x1f]{1,128}$")
_UID = re.compile(r"^[^\x00-\x1f]{1,128}$")
ALL = "*"

# Environment (main server). The SCF variables already exist in /etc/szzsbj/walmart-scf.env.
ENV_PROTOCOL = "SZZSBJ_WALMART_SCF_PROTOCOL"  # "1" (default, legacy) or "3" (signed contracts)
ENV_STORE_MAP = "SZZSBJ_WALMART_SCF_STORE_ID_MAP"  # {"<lingxing store_id>": "HK2614", ...}
ENV_CVM_ROLE = "SZZSBJ_WALMART_SCF_CVM_ROLE"
ENV_TARGET_ROLE_ARN = "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN"
ENV_APPROVED_READ_KEYS = "SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS"  # legacy protocol only
ENV_APPROVED_WRITE_KEYS = "SZZSBJ_WALMART_SCF_APPROVED_WRITE_KEYS"  # legacy protocol only
ENV_SIGNING_KEY_FILE = "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE"
ENV_SIGNING_KEY_ID = "SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_ID"
DEFAULT_SIGNING_KEY_FILE = "/etc/szzsbj/walmart-contract-signing.pem"


class GatewayError(RuntimeError):
    """Stable code; ``provider_error`` carries Walmart's sanitized body when there is one."""

    def __init__(
        self, code: str, *, status_code: int | None = None, provider_error: Any = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.provider_error = provider_error


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is calling. ``permissions`` and ``store_codes`` come from verified server state.

    ``store_codes=None`` means every configured store (owner / scheduler scope);
    ``permissions={"*"}`` means every permission. System actors (schedulers, workers)
    are built with ``Actor.system`` and carry an explicit operation allowlist instead.
    """

    kind: str
    uid: str
    permissions: frozenset[str]
    store_codes: frozenset[str] | None = None
    operations: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("user", "system") or not _UID.fullmatch(self.uid):
            raise GatewayError("WALMART_ACTOR_INVALID")

    @classmethod
    def from_principal(cls, principal: Any, *, store_codes: Iterable[str] | None) -> Actor:
        """``principal`` is ``app.core.auth.Principal`` (user_id, permissions)."""
        return cls(
            kind="user",
            uid=str(principal.user_id),
            permissions=frozenset(principal.permissions),
            store_codes=None if store_codes is None else frozenset(store_codes),
        )

    @classmethod
    def system(
        cls, uid: str, *, operations: Iterable[str], store_codes: Iterable[str] | None = None
    ) -> Actor:
        """A background process. It may only use the operations listed in its own code."""
        allowed = frozenset(operations)
        if not allowed:
            raise GatewayError("WALMART_ACTOR_INVALID")
        return cls(
            kind="system",
            uid=uid,
            permissions=frozenset({ALL}),
            store_codes=None if store_codes is None else frozenset(store_codes),
            operations=allowed,
        )

    def as_event(self) -> dict[str, str]:
        return {"kind": self.kind, "uid": self.uid}


@dataclass(frozen=True, slots=True)
class CallRecord:
    """Audit line for one gateway call. Never carries params, bodies or responses."""

    store_code: str
    operation_key: str
    risk: str
    actor_kind: str
    actor_uid: str
    approval_ref: str | None
    contract_sha256: str | None
    registry_version: str
    request_sha256: str | None
    status_code: int | None
    outcome: str  # ok | provider_error | gateway_error | unknown | denied
    error_code: str | None
    duration_ms: int


AuditSink = Callable[[CallRecord], None]


def log_audit(record: CallRecord) -> None:
    """Default sink: structured log line (the database sink lives in the pmc_wfs module)."""
    logger.info(
        "walmart_call store=%s op=%s risk=%s actor=%s:%s approval=%s status=%s outcome=%s "
        "error=%s ms=%d contract=%s registry=%s",
        record.store_code,
        record.operation_key,
        record.risk,
        record.actor_kind,
        record.actor_uid,
        record.approval_ref,
        record.status_code,
        record.outcome,
        record.error_code,
        record.duration_ms,
        record.contract_sha256,
        record.registry_version,
    )


class _ActorBoundClient:
    """Lets ``collect_read_pages`` (which calls ``client.call``) carry the actor through."""

    def __init__(self, client: WalmartClient, actor: Actor) -> None:
        self._client = client
        self._actor = actor
        self.registry = client.registry

    def call(self, store_code: str, operation: str, **kwargs: Any) -> WalmartResult:
        return self._client.call(store_code, operation, actor=self._actor.as_event(), **kwargs)


class WalmartGateway:
    def __init__(
        self,
        client: WalmartClient,
        *,
        audit: AuditSink | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._registry: ContractRegistry = client.registry
        self._audit = audit or log_audit
        self._clock = clock

    @property
    def registry(self) -> ContractRegistry:
        return self._registry

    @property
    def stores(self) -> frozenset[str]:
        return self._client.allowed_stores

    # ----- authorization ------------------------------------------------------------

    def authorize(
        self, *, actor: Actor, store_code: str, operation_key: str, approval_ref: str | None
    ) -> Operation:
        """Server-side business authorization; raises ``GatewayError`` with a stable code."""
        try:
            operation = self._registry.get(operation_key)
        except ContractError as error:
            raise GatewayError(str(error)) from None
        if store_code not in STORE_ROUTES or store_code not in self._client.allowed_stores:
            raise GatewayError("WALMART_STORE_NOT_AUTHORIZED")
        if actor.store_codes is not None and store_code not in actor.store_codes:
            raise GatewayError("WALMART_STORE_NOT_AUTHORIZED")
        if actor.operations is not None and operation_key not in actor.operations:
            raise GatewayError("WALMART_PERMISSION_DENIED")
        permission = operation.permission
        if permission is None:
            raise GatewayError("WALMART_PERMISSION_DENIED")
        if ALL not in actor.permissions and permission not in actor.permissions:
            raise GatewayError("WALMART_PERMISSION_DENIED")
        if approval_ref is not None and not _APPROVAL.fullmatch(approval_ref):
            raise GatewayError("WALMART_APPROVAL_INVALID")
        if operation.is_write and approval_ref is None:
            raise GatewayError("WALMART_WRITE_APPROVAL_REQUIRED")
        return operation

    # ----- calls --------------------------------------------------------------------

    def call(
        self,
        store_code: str,
        operation_key: str,
        *,
        actor: Actor,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        approval_ref: str | None = None,
    ) -> WalmartResult:
        """Execute one operation. Non-2xx answers are returned (``provider_error`` set);
        anything that prevents a trustworthy answer raises ``GatewayError``.
        """
        started = self._clock()
        contract_hash: str | None = None
        request_hash: str | None = None
        operation: Operation | None = None
        try:
            operation = self.authorize(
                actor=actor,
                store_code=store_code,
                operation_key=operation_key,
                approval_ref=approval_ref,
            )
            prepared = self._registry.prepare(
                operation_key, params=params, body=body, allow_writes=True
            )
            contract_hash = sha256_hex(prepared.contract) if prepared.contract else None
            request_hash = request_sha256(
                method=prepared.method,
                path=prepared.path,
                params=prepared.params or {},
                body=prepared.body,
            )
            result = self._client.call(
                store_code,
                operation_key,
                params=params,
                body=body,
                allow_writes=True,
                approval_ref=approval_ref,
                actor=actor.as_event(),
            )
        except GatewayError as error:  # only ``authorize`` raises this: a refusal
            self._record(
                store_code,
                operation_key,
                operation,
                actor,
                approval_ref,
                contract_hash,
                request_hash,
                None,
                "denied",
                error.code,
                started,
            )
            raise
        except ContractError as error:
            self._record(
                store_code,
                operation_key,
                operation,
                actor,
                approval_ref,
                contract_hash,
                request_hash,
                None,
                "gateway_error",
                str(error),
                started,
            )
            raise GatewayError(str(error)) from None
        except Exception as error:  # transport, STS, SCF: the outcome is unknown
            code = str(error) if isinstance(error, (RuntimeError, ValueError)) else ""
            code = code if re.fullmatch(r"[A-Z0-9_]{4,64}", code) else "WALMART_GATEWAY_UNAVAILABLE"
            self._record(
                store_code,
                operation_key,
                operation,
                actor,
                approval_ref,
                contract_hash,
                request_hash,
                None,
                "unknown",
                code,
                started,
            )
            raise GatewayError(code) from None
        self._record(
            store_code,
            operation_key,
            operation,
            actor,
            approval_ref,
            contract_hash,
            request_hash,
            result.status_code,
            "ok" if result.ok else "provider_error",
            None,
            started,
        )
        return result

    def pages(
        self,
        store_code: str,
        *,
        actor: Actor,
        contract: PageContract,
        params: Mapping[str, Any] | None = None,
        page_size: int = 50,
        max_pages: int = 50,
        max_items: int = 2500,
    ) -> tuple[dict[str, Any], ...]:
        """All pages of a read operation or nothing (bounded; never a silently short list)."""
        started = self._clock()
        operation = self.authorize(
            actor=actor, store_code=store_code, operation_key=contract.operation, approval_ref=None
        )
        if operation.is_write:
            raise GatewayError("WALMART_PAGE_WRITE_FORBIDDEN")
        try:
            rows = collect_read_pages(
                _ActorBoundClient(self._client, actor),  # type: ignore[arg-type]
                store_code=store_code,
                contract=contract,
                params=params,
                page_size=page_size,
                max_pages=max_pages,
                max_items=max_items,
            )
        except (PaginationRejected, ContractError) as error:
            self._record(
                store_code,
                contract.operation,
                operation,
                actor,
                None,
                None,
                None,
                None,
                "gateway_error",
                str(error),
                started,
            )
            raise GatewayError(str(error)) from None
        self._record(
            store_code,
            contract.operation,
            operation,
            actor,
            None,
            None,
            None,
            200,
            "ok",
            None,
            started,
        )
        return rows

    def call_many(
        self,
        store_codes: Iterable[str],
        operation_key: str,
        *,
        actor: Actor,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, WalmartResult | GatewayError]:
        """Same read on several stores; one store's failure never hides another's result."""
        results: dict[str, WalmartResult | GatewayError] = {}
        for store_code in dict.fromkeys(store_codes):
            try:
                results[store_code] = self.call(
                    store_code, operation_key, actor=actor, params=params
                )
            except GatewayError as error:
                results[store_code] = error
        return results

    # ----- audit --------------------------------------------------------------------

    def _record(
        self,
        store_code: str,
        operation_key: str,
        operation: Operation | None,
        actor: Actor,
        approval_ref: str | None,
        contract_hash: str | None,
        request_hash: str | None,
        status_code: int | None,
        outcome: str,
        error_code: str | None,
        started: float,
    ) -> None:
        record = CallRecord(
            store_code=store_code,
            operation_key=operation_key,
            risk=operation.risk if operation else "unknown",
            actor_kind=actor.kind,
            actor_uid=actor.uid,
            approval_ref=approval_ref,
            contract_sha256=contract_hash,
            registry_version=self._registry.version(),
            request_sha256=request_hash,
            status_code=status_code,
            outcome=outcome,
            error_code=error_code,
            duration_ms=max(0, int((self._clock() - started) * 1000)),
        )
        try:
            self._audit(record)
        except Exception:  # the audit sink must never break or mask the business call
            logger.exception("walmart audit sink failed (record dropped from sink, logged here)")
            log_audit(record)

    # ----- construction -------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        *,
        audit: AuditSink | None = None,
        identity_provider: Any = None,
        environ: Mapping[str, str] | None = None,
    ) -> WalmartGateway:
        """Build the production gateway from the server's ``SZZSBJ_WALMART_SCF_*`` variables.

        Protocol 3 needs the signing key file; protocol 1 keeps the legacy per-key
        approvals so a server can switch before or after the cloud functions are upgraded.
        """
        env = os.environ if environ is None else environ
        store_map = reviewed_store_id_map(env)
        stores = frozenset(store_map.values())
        role = env.get(ENV_CVM_ROLE, "").strip()
        arn = env.get(ENV_TARGET_ROLE_ARN, "").strip()
        if not stores or not role or not arn:
            raise GatewayError("WALMART_GATEWAY_CONFIG_INVALID")
        protocol = env.get(ENV_PROTOCOL, "1").strip() or "1"
        if protocol not in ("1", "3"):
            raise GatewayError("WALMART_GATEWAY_CONFIG_INVALID")
        function_by_store = {s: f"szzsbj-walmart-{s.lower()}-executor" for s in stores}
        from app.integrations.walmart.routed_scf import create_scoped_client
        from app.integrations.walmart.scf_read_factory import RefreshingScfApi
        from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity

        provider = identity_provider or CachedScfAssumeRoleIdentity(
            cvm_role=role, target_role_arn=arn
        )
        if protocol == "3":
            key_file = env.get(ENV_SIGNING_KEY_FILE, DEFAULT_SIGNING_KEY_FILE).strip()
            kid = env.get(ENV_SIGNING_KEY_ID, "").strip()
            if not kid:
                raise GatewayError("WALMART_GATEWAY_CONFIG_INVALID")
            try:
                signer = ContractSigner.from_pem_file(key_file, kid=kid)
            except ContractError as error:
                raise GatewayError(str(error)) from None
            client = create_scoped_client(
                reviewed_registry(),
                allowed_stores=stores,
                function_by_store=function_by_store,
                cloud_api=RefreshingScfApi(provider),
                bridge_version=3,
                signer=signer,
            )
            return cls(client, audit=audit)
        # Legacy protocol: the registry only enables what the cloud allowlists enable.
        from app.integrations.walmart.unified_api import load_unified_registry

        read_keys = _csv(env.get(ENV_APPROVED_READ_KEYS, ""))
        write_keys = _csv(env.get(ENV_APPROVED_WRITE_KEYS, ""))
        if not read_keys and not write_keys:
            raise GatewayError("WALMART_GATEWAY_CONFIG_INVALID")
        try:
            legacy = load_unified_registry(read_keys, approved_write_keys=write_keys)
        except ValueError as error:
            raise GatewayError(str(error)) from None
        # Carry the business permissions over so authorization works the same way.
        reviewed = reviewed_registry()
        enabled = tuple(
            _with_permission(legacy.get(key), reviewed)
            for key in legacy.keys()
            if legacy.get(key).enabled
        )
        client = create_scoped_client(
            ContractRegistry(enabled),
            allowed_stores=stores,
            function_by_store=function_by_store,
            cloud_api=RefreshingScfApi(provider),
            bridge_version=2 if write_keys else 1,
        )
        return cls(client, audit=audit)


def _with_permission(operation: Operation, reviewed: ContractRegistry) -> Operation:
    from dataclasses import replace

    try:
        source = reviewed.get(operation.key)
    except ContractError:
        return operation
    return replace(operation, family=source.family, permission=source.permission)


def _csv(raw: str) -> frozenset[str]:
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def reviewed_store_id_map(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """``SZZSBJ_WALMART_SCF_STORE_ID_MAP``: Lingxing store_id -> Walmart store code."""
    import json

    env = os.environ if environ is None else environ
    try:
        raw = json.loads(env.get(ENV_STORE_MAP, "{}"))
    except ValueError:
        raise GatewayError("WALMART_SCF_MAPPING_INVALID") from None
    if (
        not isinstance(raw, dict)
        or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or v not in STORE_ROUTES
            for k, v in raw.items()
        )
        or len(set(raw.values())) != len(raw)
    ):
        raise GatewayError("WALMART_SCF_MAPPING_INVALID")
    return dict(raw)
