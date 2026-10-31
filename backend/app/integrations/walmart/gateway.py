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
from typing import Any, Protocol

from app.integrations.walmart.client import WalmartClient, WalmartResult
from app.integrations.walmart.contract_signing import ContractSigner
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
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9:._-]{1,160}$")
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
    outcome: str  # attempt | ok | provider_error | gateway_error | unknown | denied
    error_code: str | None
    duration_ms: int
    idempotency_key: str | None = None


AuditSink = Callable[[CallRecord], None]


def log_audit(record: CallRecord) -> None:
    """Default sink: structured log line (the database sink lives in the pmc_wfs module)."""
    logger.info(
        "walmart_call store=%s op=%s risk=%s actor=%s:%s approval=%s status=%s outcome=%s "
        "error=%s ms=%d contract=%s registry=%s idem=%s",
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
        record.idempotency_key,
    )


class _ActorBoundClient:
    """Lets ``collect_read_pages`` (which calls ``client.call``) carry the actor through."""

    def __init__(self, client: WalmartClient, actor: Actor) -> None:
        self._client = client
        self._actor = actor
        self.registry = client.registry

    def call(self, store_code: str, operation: str, **kwargs: Any) -> WalmartResult:
        return self._client.call(store_code, operation, actor=self._actor.as_event(), **kwargs)


class WriteLedger(Protocol):
    """Persisted idempotency state for writes (reviewer requirements 1 and 4).

    ``begin`` must refuse a key whose last attempt is still ``attempting`` or ended
    ``unknown`` (``WALMART_WRITE_PENDING_REVIEW``) or already succeeded
    (``WALMART_WRITE_ALREADY_DONE``); ``finish`` stores the outcome; ``resolve`` is the
    reconcile hook that closes an unknown attempt after a read-back. The database-backed
    implementation lives next to the audit table in the PMC WFS module; the in-memory one
    below is for tests and single-process tools only.
    """

    def begin(
        self,
        key: str,
        *,
        store_code: str,
        operation_key: str,
        actor_uid: str,
        approval_ref: str,
        request_sha256: str,
    ) -> None: ...

    def finish(
        self, key: str, *, outcome: str, status_code: int | None, error_code: str | None
    ) -> None: ...

    def status(self, key: str) -> str | None: ...

    def resolve(self, key: str, *, outcome: str, note: str) -> None: ...


class RefusingLedger:
    """Default ledger: no persistence configured, so every write is refused.

    Production wiring must pass a persistent ledger (``walmart_scf.persistence``); the
    in-memory ledger below has to be chosen explicitly and is for tests only.
    """

    def begin(self, key: str, **fields: Any) -> None:
        raise GatewayError("WALMART_LEDGER_REQUIRED")

    def finish(self, key: str, **fields: Any) -> None:  # pragma: no cover - never opened
        raise GatewayError("WALMART_LEDGER_REQUIRED")

    def status(self, key: str) -> str | None:
        return None

    def resolve(self, key: str, **fields: Any) -> None:
        raise GatewayError("WALMART_LEDGER_REQUIRED")


class InMemoryWriteLedger:
    """Reference implementation of ``WriteLedger`` for tests and single-process tools.

    It is never selected by default and ``from_env`` refuses it: a process restart would
    forget an open write (reviewer requirement P0, persistent idempotency).
    """

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    def begin(self, key: str, **fields: Any) -> None:
        current = self.entries.get(key)
        if current is not None:
            if current["outcome"] in ("attempting", "unknown"):
                raise GatewayError("WALMART_WRITE_PENDING_REVIEW")
            if current["outcome"] == "ok":
                raise GatewayError("WALMART_WRITE_ALREADY_DONE")
            if current["request_sha256"] != fields["request_sha256"]:
                # Same business key, different payload: a retry must be the same request.
                raise GatewayError("WALMART_WRITE_PAYLOAD_CHANGED")
        self.entries[key] = {
            **fields,
            "outcome": "attempting",
            "attempts": (current or {}).get("attempts", 0) + 1,
        }

    def finish(
        self, key: str, *, outcome: str, status_code: int | None, error_code: str | None
    ) -> None:
        entry = self.entries[key]
        entry.update(outcome=outcome, status_code=status_code, error_code=error_code)

    def status(self, key: str) -> str | None:
        entry = self.entries.get(key)
        return None if entry is None else str(entry["outcome"])

    def resolve(self, key: str, *, outcome: str, note: str) -> None:
        if outcome not in ("ok", "provider_error", "failed"):
            raise GatewayError("WALMART_LEDGER_RESOLUTION_INVALID")
        entry = self.entries[key]
        entry.update(outcome=outcome, note=note)


class WalmartGateway:
    def __init__(
        self,
        client: WalmartClient,
        *,
        audit: AuditSink | None = None,
        ledger: WriteLedger | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._registry: ContractRegistry = client.registry
        self._audit = audit or log_audit
        self._ledger: WriteLedger = ledger or RefusingLedger()
        self._clock = clock
        # Records the audit sink could not persist yet (transactional-outbox style):
        # flushed before the next call; a write is refused while anything is pending.
        self._outbox: list[CallRecord] = []

    @property
    def pending_audit(self) -> int:
        return len(self._outbox)

    @property
    def ledger(self) -> WriteLedger:
        return self._ledger

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
        idempotency_key: str | None = None,
    ) -> WalmartResult:
        """Execute one operation. Non-2xx answers are returned (``provider_error`` set);
        anything that prevents a trustworthy answer raises ``GatewayError``.

        A write needs ``approval_ref`` (audit reference, generated server-side) and an
        ``idempotency_key`` (business identity of the write, e.g. ``create:<inboundOrderId>``).
        The ledger records the attempt before the cloud call and the outcome after it; a
        key whose last attempt is still open or unknown is refused until a reconcile step
        resolves it, so an uncertain write is never repeated blindly.
        """
        started = self._clock()
        contract_hash: str | None = None
        request_hash: str | None = None
        operation: Operation | None = None
        ledger_open = False
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
            request_hash = sha256_hex(
                {
                    "method": prepared.method,
                    "path": prepared.path,
                    "params": dict(prepared.params or {}),
                    "body": prepared.body,
                }
            )
            if operation.is_write:
                if idempotency_key is None or not _IDEMPOTENCY.fullmatch(idempotency_key):
                    raise GatewayError("WALMART_IDEMPOTENCY_KEY_REQUIRED")
                if not self._flush_outbox():
                    # Earlier evidence is still unpersisted: no new write until it is.
                    raise GatewayError("WALMART_AUDIT_UNAVAILABLE")
                try:
                    self._ledger.begin(
                        idempotency_key,
                        store_code=store_code,
                        operation_key=operation_key,
                        actor_uid=actor.uid,
                        approval_ref=approval_ref or "",
                        request_sha256=request_hash,
                    )
                except GatewayError:
                    raise
                except Exception as error:  # a persistent ledger's own stable codes
                    code = getattr(error, "code", None)
                    if not isinstance(code, str):
                        code = str(error)
                    if re.fullmatch(r"[A-Z0-9_]{4,64}", code):
                        raise GatewayError(code) from None
                    raise GatewayError("WALMART_LEDGER_UNAVAILABLE") from None
                ledger_open = True
                # The intent must be on record before anything leaves the server.
                persisted = self._record(
                    store_code,
                    operation_key,
                    operation,
                    actor,
                    approval_ref,
                    contract_hash,
                    request_hash,
                    None,
                    "attempt",
                    None,
                    started,
                    idempotency_key,
                )
                if not persisted:
                    self._ledger.finish(
                        idempotency_key,
                        outcome="failed",
                        status_code=None,
                        error_code="WALMART_AUDIT_UNAVAILABLE",
                    )
                    ledger_open = False
                    raise GatewayError("WALMART_AUDIT_UNAVAILABLE")
            else:
                self._flush_outbox()
            result = self._client.call(
                store_code,
                operation_key,
                params=params,
                body=body,
                allow_writes=True,
                approval_ref=approval_ref,
                actor=actor.as_event(),
            )
        except GatewayError as error:  # authorize / ledger refusals
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
                idempotency_key,
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
                idempotency_key,
            )
            raise GatewayError(str(error)) from None
        except Exception as error:  # transport, STS, SCF: the outcome is unknown
            code = str(error) if isinstance(error, (RuntimeError, ValueError)) else ""
            code = code if re.fullmatch(r"[A-Z0-9_]{4,64}", code) else "WALMART_GATEWAY_UNAVAILABLE"
            if ledger_open and idempotency_key is not None:
                self._ledger.finish(
                    idempotency_key, outcome="unknown", status_code=None, error_code=code
                )
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
                idempotency_key,
            )
            raise GatewayError(code) from None
        outcome = "ok" if result.ok else "provider_error"
        if ledger_open and idempotency_key is not None:
            self._ledger.finish(
                idempotency_key, outcome=outcome, status_code=result.status_code, error_code=None
            )
        self._record(
            store_code,
            operation_key,
            operation,
            actor,
            approval_ref,
            contract_hash,
            request_hash,
            result.status_code,
            outcome,
            None,
            started,
            idempotency_key,
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
        idempotency_key: str | None = None,
    ) -> bool:
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
            idempotency_key=idempotency_key,
        )
        return self._persist(record)

    def _persist(self, record: CallRecord) -> bool:
        """Hand a record to the sink; on failure keep it in the outbox (and in the log)."""
        try:
            self._audit(record)
            return True
        except Exception:
            logger.exception("walmart audit sink failed; record kept in outbox")
            log_audit(record)
            self._outbox.append(record)
            return False

    def _flush_outbox(self) -> bool:
        """Retry pending records in order; True when nothing is pending afterwards."""
        while self._outbox:
            record = self._outbox[0]
            try:
                self._audit(record)
            except Exception:
                logger.warning("walmart audit outbox still pending (%d records)", len(self._outbox))
                return False
            self._outbox.pop(0)
        return True

    # ----- construction -------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        *,
        audit: AuditSink | None = None,
        ledger: WriteLedger | None = None,
        identity_provider: Any = None,
        environ: Mapping[str, str] | None = None,
    ) -> WalmartGateway:
        """Build the production gateway from the server's ``SZZSBJ_WALMART_SCF_*`` variables.

        Protocol 3 needs the signing key file; protocol 1 keeps the legacy per-key
        approvals so a server can switch before or after the cloud functions are upgraded.
        """
        if ledger is None or audit is None or isinstance(ledger, InMemoryWriteLedger):
            # Production composition must supply the persistent ledger and the database
            # audit sink (``app.modules.walmart_scf.persistence.build_production_gateway``).
            raise GatewayError("WALMART_LEDGER_REQUIRED")
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
                signer = ContractSigner.from_pem_file(
                    key_file, kid=kid, registry=reviewed_registry()
                )
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
            return cls(client, audit=audit, ledger=ledger)
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
        return cls(client, audit=audit, ledger=ledger)


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
