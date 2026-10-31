"""Owner-managed SCF cloud-side Walmart request executor.

The API registry, store scope, and owner decision are checked again inside the
protected execution boundary. The main-server envelope is NEVER trusted.
Live transports and approval policies must be injected by the security owner.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.integrations.walmart.contract_signing import RISK_WRITE, ContractVerifier
from app.integrations.walmart.contracts import ContractError, ContractRegistry
from app.integrations.walmart.https_transport import TransportRejected
from app.integrations.walmart.scf_bridge import _contains_secret_key

RISK_LEVELS = ("read", "write")


class CallPolicy(Protocol):
    def authorize(
        self,
        *,
        store_code: str,
        operation_key: str,
        is_write: bool,
        approval_ref: str | None,
    ) -> bool: ...


class CloudTransport(Protocol):
    def execute(self, *, store_code: str, request: Any) -> tuple[int, Any]: ...


MAX_RESULT_BYTES_V1 = 1024 * 1024
# Tencent SCF caps a synchronous response at 6 MB; leave headroom for the envelope.
MAX_RESULT_BYTES_V2 = 5 * 1024 * 1024 + 512 * 1024


class WalmartCloudExecutor:
    """Runtime executor; never serialize credentials, tokens or raw exceptions.

    Event protocol v1: read-only contract (non-2xx is an error, JSON only).
    Event protocol v2: adds ``accept`` ("json" | "pdf"); a provider 4xx/5xx comes back as
    ``success=True`` with ``provider_error`` so the caller can show Walmart's reason.
    Event protocol v3: the event carries the signed contract itself. The executor verifies
    the signature (``verifier``), rebuilds the operation from the contract, re-validates
    the request with the same contract code, and applies a per-store risk ceiling
    (``max_risk``: "read" rejects every mutating contract) instead of per-key allowlists.
    """

    def __init__(
        self,
        *,
        registry: ContractRegistry,
        store_allowlist: frozenset[str],
        policy: CallPolicy,
        transport: CloudTransport,
        verifier: ContractVerifier | None = None,
        max_risk: str = "read",
    ) -> None:
        if max_risk not in RISK_LEVELS:
            raise ContractError("WALMART_RISK_CEILING_INVALID")
        self._registry = registry
        self._stores = store_allowlist
        self._policy = policy
        self._transport = transport
        self._verifier = verifier
        self._max_risk = max_risk

    def handle(self, event: object) -> dict[str, Any]:
        try:
            return self._handle_approved(event)
        except (ContractError, TransportRejected) as error:
            return {"success": False, "status": str(error)}
        except Exception:
            return {"success": False, "status": "WALMART_EXECUTOR_FAILURE"}

    def _handle_approved(self, event: object) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise ContractError("WALMART_EVENT_INVALID")
        if event.get("version") == 3:
            return self._handle_signed(event)
        allowed_fields = {
            "version",
            "operation",
            "store_code",
            "api_key",
            "method",
            "path",
            "query",
            "body",
            "approval_ref",
            "accept",
        }
        version = event.get("version")
        if set(event) - allowed_fields or version not in (1, 2):
            raise ContractError("WALMART_EVENT_INVALID")
        accept = event.get("accept", "json")
        if version == 1 and "accept" in event:
            raise ContractError("WALMART_EVENT_INVALID")
        if accept not in ("json", "pdf"):
            raise ContractError("WALMART_EVENT_INVALID")
        if event.get("operation") != "marketplace_call":
            raise ContractError("WALMART_EVENT_INVALID")
        store = event.get("store_code")
        key = event.get("api_key")
        if not isinstance(store, str) or store not in self._stores:
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        if not isinstance(key, str):
            raise ContractError("WALMART_API_NOT_REGISTERED")
        approval = event.get("approval_ref")
        if approval is not None and (
            not isinstance(approval, str) or not 1 <= len(approval) <= 128
        ):
            raise ContractError("WALMART_APPROVAL_INVALID")
        request = self._registry.prepare(
            key, params=event.get("query"), body=event.get("body"), allow_writes=True
        )
        if request.method != event.get("method") or request.path != event.get("path"):
            raise ContractError("WALMART_OPERATION_MISMATCH")
        if accept != getattr(request, "response_kind", "json"):
            raise ContractError("WALMART_OPERATION_MISMATCH")
        if request.is_write and not approval:
            raise ContractError("WALMART_WRITE_APPROVAL_REQUIRED")
        if not self._policy.authorize(
            store_code=store,
            operation_key=key,
            is_write=request.is_write,
            approval_ref=approval,
        ):
            raise ContractError("WALMART_OWNER_POLICY_DENIED")
        status, data = self._transport.execute(store_code=store, request=request)
        if type(status) is not int or not 100 <= status <= 599:
            raise ContractError("WALMART_PROVIDER_ERROR")
        provider_ok = 200 <= status < 300
        if not provider_ok and version == 1:
            raise ContractError("WALMART_PROVIDER_ERROR")
        if _contains_secret_key(data):
            raise ContractError("WALMART_PROVIDER_SENSITIVE_RESPONSE")
        try:
            serialized = json.dumps(data, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ContractError("WALMART_PROVIDER_RESPONSE_INVALID") from None
        limit = MAX_RESULT_BYTES_V2 if version == 2 else MAX_RESULT_BYTES_V1
        if len(serialized.encode("utf-8")) > limit:
            raise ContractError("WALMART_PROVIDER_RESPONSE_TOO_LARGE")
        if not provider_ok:
            return {
                "success": True,
                "status_code": status,
                "store_code": store,
                "api_key": key,
                "data": None,
                "provider_error": data,
            }
        return {
            "success": True,
            "status_code": status,
            "store_code": store,
            "api_key": key,
            "data": data,
        }

    # ----- protocol v3 -------------------------------------------------------------

    def _handle_signed(self, event: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "version",
            "operation",
            "store_code",
            "function_name",
            "contract",
            "method",
            "path",
            "params",
            "body",
            "accept",
            "risk",
            "approval_ref",
            "actor",
            "auth",
        }
        if set(event) - allowed_fields or event.get("operation") != "marketplace_call":
            raise ContractError("WALMART_EVENT_INVALID")
        if self._verifier is None:
            raise ContractError("WALMART_PROTOCOL_NOT_ENABLED")
        store = event.get("store_code")
        if not isinstance(store, str) or store not in self._stores:
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        # Actor shape is validated (and signed) inside the verifier.
        accept = event.get("accept", "json")
        if accept not in ("json", "pdf"):
            raise ContractError("WALMART_EVENT_INVALID")
        # Signature, key, freshness, replay, store/function binding, contract shape,
        # hashes and the method-derived risk level.
        verified = self._verifier.verify(event)
        operation = verified.operation
        registry = ContractRegistry((operation,))
        # Same contract code as the server: path/query values are re-validated against the
        # field schemas and the resolved path must equal what the caller claims to call.
        request = registry.prepare(
            operation.key, params=event.get("params"), body=event.get("body"), allow_writes=True
        )
        if request.method != event.get("method") or request.path != event.get("path"):
            raise ContractError("WALMART_OPERATION_MISMATCH")
        if accept != request.response_kind:
            raise ContractError("WALMART_OPERATION_MISMATCH")
        approval = event.get("approval_ref")
        # Risk comes from the verifier (method-based, reviewer requirement 3), never from
        # the contract's own ``mutating`` flag alone.
        if verified.risk == RISK_WRITE or request.is_write:
            if self._max_risk != "write":
                raise ContractError("WALMART_RISK_CEILING_DENIED")
            if not approval:
                raise ContractError("WALMART_WRITE_APPROVAL_REQUIRED")
            if not self._verifier.shared_replay:
                # A write may only run where a replayed request is refused by every
                # instance of this function, not just by the one that saw it first.
                raise ContractError("WALMART_REPLAY_STORE_REQUIRED")
        status, data = self._transport.execute(store_code=store, request=request)
        if type(status) is not int or not 100 <= status <= 599:
            raise ContractError("WALMART_PROVIDER_ERROR")
        if _contains_secret_key(data):
            raise ContractError("WALMART_PROVIDER_SENSITIVE_RESPONSE")
        try:
            serialized = json.dumps(data, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ContractError("WALMART_PROVIDER_RESPONSE_INVALID") from None
        if len(serialized.encode("utf-8")) > MAX_RESULT_BYTES_V2:
            raise ContractError("WALMART_PROVIDER_RESPONSE_TOO_LARGE")
        provider_ok = 200 <= status < 300
        return {
            "success": True,
            "protocol": 3,
            "status_code": status,
            "store_code": store,
            "api_key": operation.key,
            "request_id": verified.request_id,
            "risk": verified.risk,
            "contract_sha256": verified.contract_sha256,
            "registry_version": str(event["contract"].get("registry_version", "")),
            "data": data if provider_ok else None,
            "provider_error": None if provider_ok else data,
        }
