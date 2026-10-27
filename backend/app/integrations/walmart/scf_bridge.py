"""Protected SCF executor bridge; no Walmart credential is held in this module.

The cloud invoker is injected by the approved runtime.  Its deployment,
identity, signing, retry and SSM access are independently owner controlled.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.integrations.walmart.contracts import PreparedRequest


class GatewayRejected(RuntimeError):
    """A stable error code; never return an external exception or secret."""


class CloudInvoker(Protocol):
    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SafeResult:
    status_code: int
    data: Any


class ProtectedScfBridge:
    """Build an approved cloud invocation and enforce a typed result envelope."""

    def __init__(self, invoker: CloudInvoker) -> None:
        self._invoker = invoker

    def execute(
        self, *, store_code: str, request: PreparedRequest, approval_ref: str | None
    ) -> SafeResult:
        if request.is_write and not approval_ref:
            raise GatewayRejected("WALMART_WRITE_APPROVAL_REQUIRED")
        event = {
            "version": 1,
            "operation": "marketplace_call",
            "store_code": store_code,
            "api_key": request.key,
            "method": request.method,
            "path": request.path,
            "query": dict(request.query),
            "body": request.body,
            "approval_ref": approval_ref,
        }
        try:
            result = self._invoker.invoke(event)
        except Exception:
            raise GatewayRejected("WALMART_GATEWAY_UNAVAILABLE") from None
        if not isinstance(result, Mapping):
            raise GatewayRejected("WALMART_GATEWAY_RESPONSE_INVALID")
        if result.get("success") is not True:
            raise GatewayRejected("WALMART_GATEWAY_REJECTED")
        if result.get("store_code") != store_code or result.get("api_key") != request.key:
            raise GatewayRejected("WALMART_GATEWAY_SCOPE_MISMATCH")
        code = result.get("status_code")
        if type(code) is not int or code < 200 or code > 299:
            raise GatewayRejected("WALMART_PROVIDER_NOT_SUCCESSFUL")
        data = result.get("data")
        if _contains_secret_key(data):
            raise GatewayRejected("WALMART_GATEWAY_SECRET_RESPONSE")
        return SafeResult(status_code=code, data=data)


def _contains_secret_key(value: Any, depth: int = 0) -> bool:
    if depth > 20:
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = "".join(x for x in str(key).lower() if x.isalnum())
            if normalized in {
                "accesstoken", "refreshtoken", "clientsecret", "clientid",
                "authorization", "password", "secretkey",
            }:
                return True
            if _contains_secret_key(item, depth + 1):
                return True
    elif isinstance(value, list):
        return len(value) > 10000 or any(_contains_secret_key(x, depth + 1) for x in value)
    return False
