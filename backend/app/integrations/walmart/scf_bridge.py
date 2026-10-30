"""Protected SCF executor bridge; no Walmart credential is held in this module.

The cloud invoker is injected by the approved runtime.  Its deployment,
identity, signing, retry and SSM access are independently owner controlled.
"""

from __future__ import annotations

import base64
import binascii
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
    provider_error: Any = None
    content_type: str = "application/json"
    pdf: bytes | None = None


MAX_PDF_BYTES = 5 * 1024 * 1024


class ProtectedScfBridge:
    """Build an approved cloud invocation and enforce a typed result envelope.

    Protocol version 1 (default) is the read-only contract: any non-2xx is rejected and
    the provider body is dropped. Version 2 is used for write operations: the executor
    returns Walmart's error body on non-2xx and a base64 PDF for label operations.
    """

    def __init__(self, invoker: CloudInvoker, *, version: int = 1) -> None:
        if version not in (1, 2):
            raise GatewayRejected("WALMART_BRIDGE_VERSION_INVALID")
        self._invoker = invoker
        self._version = version

    def execute(
        self, *, store_code: str, request: PreparedRequest, approval_ref: str | None
    ) -> SafeResult:
        if request.is_write and not approval_ref:
            raise GatewayRejected("WALMART_WRITE_APPROVAL_REQUIRED")
        event: dict[str, Any] = {
            "version": self._version,
            "operation": "marketplace_call",
            "store_code": store_code,
            "api_key": request.key,
            "method": request.method,
            "path": request.path,
            "query": dict(request.query),
            "body": request.body,
            "approval_ref": approval_ref,
        }
        if self._version == 2:
            event["accept"] = request.response_kind
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
        if type(code) is not int or code < 100 or code > 599:
            raise GatewayRejected("WALMART_PROVIDER_NOT_SUCCESSFUL")
        if self._version == 1 and not 200 <= code <= 299:
            raise GatewayRejected("WALMART_PROVIDER_NOT_SUCCESSFUL")
        data = result.get("data")
        provider_error = result.get("provider_error")
        if _contains_secret_key(data) or _contains_secret_key(provider_error):
            raise GatewayRejected("WALMART_GATEWAY_SECRET_RESPONSE")
        if not 200 <= code <= 299:
            return SafeResult(status_code=code, data=None, provider_error=provider_error)
        if request.response_kind == "pdf":
            if not isinstance(data, Mapping) or data.get("content_type") != "application/pdf":
                raise GatewayRejected("WALMART_GATEWAY_RESPONSE_INVALID")
            encoded = data.get("data_base64")
            if not isinstance(encoded, str) or len(encoded) > MAX_PDF_BYTES * 4 // 3 + 4:
                raise GatewayRejected("WALMART_GATEWAY_RESPONSE_INVALID")
            try:
                pdf = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise GatewayRejected("WALMART_GATEWAY_RESPONSE_INVALID") from None
            if not pdf.startswith(b"%PDF") or len(pdf) > MAX_PDF_BYTES:
                raise GatewayRejected("WALMART_GATEWAY_RESPONSE_INVALID")
            return SafeResult(status_code=code, data=None, content_type="application/pdf", pdf=pdf)
        return SafeResult(status_code=code, data=data)


def _contains_secret_key(value: Any, depth: int = 0) -> bool:
    if depth > 20:
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = "".join(x for x in str(key).lower() if x.isalnum())
            if normalized in {
                "accesstoken",
                "refreshtoken",
                "clientsecret",
                "clientid",
                "authorization",
                "password",
                "secretkey",
            }:
                return True
            if _contains_secret_key(item, depth + 1):
                return True
    elif isinstance(value, list):
        return len(value) > 10000 or any(_contains_secret_key(x, depth + 1) for x in value)
    return False
