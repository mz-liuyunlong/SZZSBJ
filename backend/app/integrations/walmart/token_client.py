"""Main-server token fetch adapter for migration from the colleague's Mac scheduler.

No client credentials or SSM GetSecretValue permissions are held here. The
returned token is sensitive: keep it in process memory, pass to the existing
store-specific SSH stdin worker only, and never write to Celery payloads/logs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.integrations.walmart.tencent_scf import TencentScfInvoker

_STORE = re.compile(r"^(?:HK|CN)[0-9]{4}$")


class TokenClientRejected(RuntimeError):
    """No response body, token, or cloud error in the exception."""


@dataclass(frozen=True, repr=False)
class StoreToken:
    store_code: str
    access_token: str
    expires_in: int

    def __repr__(self) -> str:
        return "StoreToken([REDACTED])"


class Invoke(Protocol):
    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


def request_store_token(
    store_code: str, *, invoker: Invoke, authorized_stores: frozenset[str]
) -> StoreToken:
    if not _STORE.fullmatch(store_code) or store_code not in authorized_stores:
        raise TokenClientRejected("TOKEN_STORE_NOT_AUTHORIZED")
    try:
        result = invoker.invoke(
            {"version": 1, "operation": "issue_store_token", "store_code": store_code}
        )
        if not isinstance(result, Mapping):
            raise ValueError
        token = result.get("access_token")
        expiry = result.get("expires_in")
        if (
            result.get("success") is not True
            or result.get("operation") != "issue_store_token"
            or result.get("store_code") != store_code
            or not isinstance(token, str)
            or not token
            or len(token) > 8192
            or type(expiry) is not int
            or not 1 <= expiry <= 900
            or set(result) != {
                "success", "operation", "store_code", "access_token", "expires_in"
            }
        ):
            raise ValueError
        return StoreToken(store_code, token, expiry)
    except Exception:
        raise TokenClientRejected("TOKEN_ISSUE_UNAVAILABLE") from None


def store_token_invoker(
    *, cloud_api: Any, store_code: str, authorized_stores: frozenset[str]
) -> StoreToken:
    """Caller obtains cloud_api through existing STS RefreshingScfApi."""
    if not _STORE.fullmatch(store_code) or store_code not in authorized_stores:
        raise TokenClientRejected("TOKEN_STORE_NOT_AUTHORIZED")
    invoker = TencentScfInvoker(
        cloud_api,
        function_name="szzsbj-walmart-" + store_code.lower() + "-executor",
        qualifier="stable",
    )
    return request_store_token(
        store_code, invoker=invoker, authorized_stores=authorized_stores
    )
