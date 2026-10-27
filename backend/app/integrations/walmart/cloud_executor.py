"""Owner-managed SCF cloud-side Walmart request executor.

The API registry, store scope, and owner decision are checked again inside the
protected execution boundary. The main-server envelope is NEVER trusted.
Live transports and approval policies must be injected by the security owner.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from app.integrations.walmart.contracts import ContractError, ContractRegistry
from app.integrations.walmart.https_transport import TransportRejected
from app.integrations.walmart.scf_bridge import _contains_secret_key


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


class WalmartCloudExecutor:
    """Runtime executor; never serialize credentials, tokens or raw exceptions."""

    def __init__(
        self,
        *,
        registry: ContractRegistry,
        store_allowlist: frozenset[str],
        policy: CallPolicy,
        transport: CloudTransport,
    ) -> None:
        self._registry = registry
        self._stores = store_allowlist
        self._policy = policy
        self._transport = transport

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
        }
        if set(event) - allowed_fields or event.get("version") != 1:
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
        if type(status) is not int or not 200 <= status < 300:
            raise ContractError("WALMART_PROVIDER_ERROR")
        if _contains_secret_key(data):
            raise ContractError("WALMART_PROVIDER_SENSITIVE_RESPONSE")
        try:
            serialized = json.dumps(data, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ContractError("WALMART_PROVIDER_RESPONSE_INVALID") from None
        if len(serialized.encode("utf-8")) > 1024 * 1024:
            raise ContractError("WALMART_PROVIDER_RESPONSE_TOO_LARGE")
        return {
            "success": True,
            "status_code": status,
            "store_code": store,
            "api_key": key,
            "data": data,
        }
