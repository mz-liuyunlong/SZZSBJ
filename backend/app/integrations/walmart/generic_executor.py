"""Authenticate and execute v4 without business catalog or approval checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.integrations.walmart.contract_signing import ContractVerifier
from app.integrations.walmart.contracts import ContractError, PreparedRequest, canonical_json
from app.integrations.walmart.generic_protocol import MAX_RESULT_BYTES, VERSION
from app.integrations.walmart.https_transport import TransportRejected
from app.integrations.walmart.scf_bridge import _contains_secret_key


class GenericTransport(Protocol):
    def execute(self, *, store_code: str, request: PreparedRequest) -> tuple[int, Any]: ...


def execute_generic_event(
    event: Mapping[str, Any],
    *,
    verifier: ContractVerifier,
    store: str,
    transport: GenericTransport,
) -> dict[str, Any]:
    try:
        if event.get("store_code") != store:
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        request = verifier.verify_generic(event)
        status, data = transport.execute(store_code=store, request=request)
        if type(status) is not int or not 100 <= status <= 599:
            raise ContractError("WALMART_PROVIDER_ERROR")
        if _contains_secret_key(data):
            raise ContractError("WALMART_PROVIDER_SENSITIVE_RESPONSE")
        success = 200 <= status < 300
        result = {
            "success": True,
            "protocol": VERSION,
            "store_code": store,
            "request_id": event["auth"]["request_id"],
            "status_code": status,
            "data": data if success else None,
            "provider_error": None if success else data,
        }
        if len(canonical_json(result)) > MAX_RESULT_BYTES:
            raise ContractError("WALMART_PROVIDER_RESPONSE_TOO_LARGE")
        return result
    except (ContractError, TransportRejected) as error:
        return {"success": False, "status": str(error)}
    except Exception:
        return {"success": False, "status": "WALMART_EXECUTOR_FAILURE"}
