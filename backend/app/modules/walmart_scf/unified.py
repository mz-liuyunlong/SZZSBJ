"""Approved, store-scoped read facade for Walmart's protected SCF transport.

This module cannot write data, mutate Walmart, enable a schedule or expose a
credential. Its default configuration allows no outbound operations.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Protocol

from app.core.api import ApiError, ErrorCode
from app.integrations.walmart.client import WalmartResult
from app.integrations.walmart.planner import STORE_ROUTES
from app.integrations.walmart.scf_bridge import _contains_secret_key
from app.integrations.walmart.scf_read_factory import make_walmart_read_api
from app.integrations.walmart.unified_api import load_unified_registry

_ENABLED = "SZZSBJ_WALMART_SCF_READ_ENABLED"
_MAPPING = "SZZSBJ_WALMART_SCF_STORE_ID_MAP"
_KEYS = "SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS"
_ROLE = "SZZSBJ_WALMART_SCF_CVM_ROLE"
_ARN = "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN"


class ScfGateway(Protocol):
    def call(
        self, store_code: str, operation: str, *, params: Mapping[str, Any] | None = None
    ) -> WalmartResult: ...


def _configuration() -> tuple[dict[str, str], frozenset[str]]:
    try:
        raw = json.loads(os.getenv(_MAPPING, "{}"))
    except ValueError:
        raw = None
    if (
        not isinstance(raw, dict)
        or not raw
        or any(
            not isinstance(account, str)
            or not account
            or not isinstance(store, str)
            or store not in STORE_ROUTES
            for account, store in raw.items()
        )
        or len(set(raw.values())) != len(raw)
    ):
        raise ApiError(code="WALMART_SCF_MAPPING_INVALID", status_code=503)
    keys = os.getenv(_KEYS, "").split(",")
    approved = frozenset(key.strip() for key in keys if key.strip())
    if not approved or len(approved) != len([key for key in keys if key.strip()]):
        raise ApiError(code="WALMART_SCF_APPROVAL_MISSING", status_code=503)
    try:
        registry = load_unified_registry(approved)
        if any(registry.get(key).method != "GET" for key in approved):
            raise ValueError
    except Exception:
        raise ApiError(code="WALMART_SCF_APPROVAL_INVALID", status_code=503) from None
    return raw, approved


def store_code_for(store_id: str) -> str:
    """Resolve an operator-reviewed store ID without falling back to source account."""
    mapping, _ = _configuration()
    if store_id not in mapping:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return mapping[store_id]


@lru_cache(maxsize=1)
def _gateway() -> ScfGateway:
    mapping, approved = _configuration()
    role = os.getenv(_ROLE, "").strip()
    arn = os.getenv(_ARN, "").strip()
    if not role or not arn:
        raise ApiError(code="WALMART_SCF_CONFIG_INVALID", status_code=503)
    try:
        return make_walmart_read_api(
            allowed_stores=frozenset(mapping.values()),
            approved_read_keys=approved,
            function_by_store={
                store: f"szzsbj-walmart-{store.lower()}-executor" for store in mapping.values()
            },
            cvm_role=role,
            target_role_arn=arn,
            function_qualifier="stable",
        )
    except Exception:
        raise ApiError(code="WALMART_SCF_CONFIG_INVALID", status_code=503) from None


def approved_read(
    *,
    source_account_ref: str,
    store_id: str,
    verified_store_scope: frozenset[str],
    verified_source_account_scope: frozenset[str],
    operation: str,
    params: Mapping[str, Any] | None = None,
    gateway: ScfGateway | None = None,
) -> WalmartResult:
    """Execute an approved GET after upstream persisted store identity checks."""
    if os.getenv(_ENABLED) != "1":
        raise ApiError(code="WALMART_SCF_READ_DISABLED", status_code=503)
    if source_account_ref not in verified_source_account_scope:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    if store_id not in verified_store_scope and "*" not in verified_store_scope:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    mapping, approved = _configuration()
    if store_id not in mapping:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    if operation not in approved:
        raise ApiError(code="WALMART_OPERATION_NOT_APPROVED", status_code=403)
    try:
        # Contract validation always occurs before any remote dispatch.
        load_unified_registry(approved).prepare(operation, params=params, allow_writes=False)
    except Exception:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422) from None
    try:
        result = (gateway or _gateway()).call(mapping[store_id], operation, params=params)
        if (
            type(result.status_code) is not int
            or not 200 <= result.status_code < 300
            or _contains_secret_key(result.data)
        ):
            raise ValueError
        return result
    except Exception:
        raise ApiError(code="WALMART_SCF_READ_UNAVAILABLE", status_code=502) from None
