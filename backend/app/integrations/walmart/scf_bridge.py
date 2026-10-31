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

from app.integrations.walmart.contract_signing import ContractSigner
from app.integrations.walmart.contracts import PreparedRequest, sha256_hex


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

    Version 3 sends the signed contract itself (see ``contract_signing``); the cloud side
    then needs no per-operation allowlist. It requires a ``signer`` and an ``actor``.
    """

    def __init__(
        self, invoker: CloudInvoker, *, version: int = 1, signer: ContractSigner | None = None
    ) -> None:
        if version not in (1, 2, 3):
            raise GatewayRejected("WALMART_BRIDGE_VERSION_INVALID")
        if version == 3 and signer is None:
            raise GatewayRejected("WALMART_SIGNER_REQUIRED")
        self._invoker = invoker
        self._version = version
        self._signer = signer

    def execute(
        self,
        *,
        store_code: str,
        request: PreparedRequest,
        approval_ref: str | None,
        actor: Mapping[str, str] | None = None,
    ) -> SafeResult:
        if request.is_write and not approval_ref:
            raise GatewayRejected("WALMART_WRITE_APPROVAL_REQUIRED")
        if self._version == 3:
            event = self._signed_event(
                store_code=store_code, request=request, approval_ref=approval_ref, actor=actor
            )
        else:
            event = {
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
        if self._version == 3 and (
            result.get("protocol") != 3
            or result.get("contract_sha256") != sha256_hex(request.contract)
        ):
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

    def _signed_event(
        self,
        *,
        store_code: str,
        request: PreparedRequest,
        approval_ref: str | None,
        actor: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        assert self._signer is not None
        if request.contract is None:
            raise GatewayRejected("WALMART_CONTRACT_MISSING")
        if (
            not isinstance(actor, Mapping)
            or set(actor) != {"kind", "uid"}
            or actor["kind"] not in ("user", "system")
            or not isinstance(actor["uid"], str)
            or not 1 <= len(actor["uid"]) <= 128
        ):
            raise GatewayRejected("WALMART_ACTOR_INVALID")
        params = dict(request.params or {})
        contract = dict(request.contract)
        auth = self._signer.sign(
            store_code=store_code,
            contract=contract,
            method=request.method,
            path=request.path,
            params=params,
            body=request.body,
            approval_ref=approval_ref,
        )
        return {
            "version": 3,
            "operation": "marketplace_call",
            "store_code": store_code,
            "contract": contract,
            "method": request.method,
            "path": request.path,
            "params": params,
            "body": request.body,
            "accept": request.response_kind,
            "approval_ref": approval_ref,
            "actor": {"kind": actor["kind"], "uid": actor["uid"]},
            "auth": auth,
        }


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
