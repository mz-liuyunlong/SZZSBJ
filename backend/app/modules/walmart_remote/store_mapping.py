"""Strict, independent nine-store identity mapping for remote collection."""

from __future__ import annotations

import json
import os

from app.core.api import ApiError, ErrorCode
from app.integrations.walmart.remote_dispatch import STORES


def remote_store_mapping() -> dict[str, str]:
    """Map persisted store ID to store code; do not depend on legacy SCF read keys."""
    try:
        mapping = json.loads(os.getenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", "{}"))
    except (ValueError, TypeError):
        mapping = None
    if (
        not isinstance(mapping, dict)
        or not mapping
        or any(
            not isinstance(store_id, str)
            or not store_id.isdecimal()
            or not isinstance(code, str)
            or code not in STORES
            for store_id, code in mapping.items()
        )
        or len(set(mapping.values())) != len(mapping)
    ):
        raise ApiError(code="REMOTE_STORE_MAPPING_INVALID", status_code=503)
    return mapping


def remote_store_code_for(store_id: str) -> str:
    mapping = remote_store_mapping()
    if store_id not in mapping:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return mapping[store_id]
