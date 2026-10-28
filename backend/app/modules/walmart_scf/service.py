"""Fail-closed business entrypoint for store-scoped Walmart SCF reads.

The main server never receives Walmart client credentials. No schedules, writes,
or background dispatch are enabled by this module.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Protocol

from app.core.api import ApiError, ErrorCode
from app.integrations.walmart.client import WalmartResult
from app.integrations.walmart.planner import STORE_ROUTES
from app.integrations.walmart.scf_bridge import _contains_secret_key
from app.integrations.walmart.scf_read_factory import make_walmart_read_api

_ENABLED_ENV = "SZZSBJ_WALMART_SCF_READ_ENABLED"
_STORES_ENV = "SZZSBJ_WALMART_SCF_APPROVED_STORES"
_ROLE_ENV = "SZZSBJ_WALMART_SCF_CVM_ROLE"
_TARGET_ROLE_ENV = "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN"


class ReadGateway(Protocol):
    def call(
        self, store_code: str, operation: str, *, params: dict[str, Any]
    ) -> WalmartResult: ...


def _approved_stores() -> frozenset[str]:
    raw = os.getenv(_STORES_ENV, "")
    parts = [part.strip() for part in raw.split(",")]
    if (
        not raw
        or any(not part or part not in STORE_ROUTES for part in parts)
        or len(set(parts)) != len(parts)
    ):
        raise ApiError(code="WALMART_SCF_CONFIG_INVALID", status_code=503)
    return frozenset(parts)


@lru_cache(maxsize=1)
def _configured_gateway() -> ReadGateway:
    stores = _approved_stores()
    cvm_role = os.getenv(_ROLE_ENV, "").strip()
    target_role = os.getenv(_TARGET_ROLE_ENV, "").strip()
    if not cvm_role or not target_role:
        raise ApiError(code="WALMART_SCF_CONFIG_INVALID", status_code=503)
    try:
        return make_walmart_read_api(
            allowed_stores=stores,
            approved_read_keys=frozenset({"wfs_inventory"}),
            function_by_store={
                store: f"szzsbj-walmart-{store.lower()}-executor" for store in stores
            },
            cvm_role=cvm_role,
            target_role_arn=target_role,
            function_qualifier="stable",
        )
    except Exception:
        raise ApiError(code="WALMART_SCF_CONFIG_INVALID", status_code=503) from None


def read_wfs_inventory(
    *,
    store_code: str,
    verified_source_account_scope: frozenset[str],
    limit: int = 1,
    gateway: ReadGateway | None = None,
) -> WalmartResult:
    """Read exactly one approved GET operation after independent IAM data-scope checks.

    The caller must supply a verified, server-side source-account scope. This
    intentionally fails closed when internal account IDs are not equal to the
    documented Walmart store codes; an audited mapping must be added separately.
    """
    if os.getenv(_ENABLED_ENV) != "1":
        raise ApiError(code="WALMART_SCF_READ_DISABLED", status_code=503)
    if store_code not in verified_source_account_scope:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    if store_code not in _approved_stores():
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    try:
        result = (gateway or _configured_gateway()).call(
            store_code, "wfs_inventory", params={"limit": limit}
        )
        if not 200 <= result.status_code < 300 or _contains_secret_key(result.data):
            raise ValueError("unsafe upstream response")
        return result
    except Exception:
        # No cloud exception contents, credentials, identifiers or provider bodies.
        raise ApiError(code="WALMART_SCF_READ_UNAVAILABLE", status_code=502) from None
