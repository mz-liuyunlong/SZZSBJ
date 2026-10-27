"""Sanitized static 2026-10-08.9 capability catalog from the original app.js.

192 business capabilities / 143 distinct method+path physical endpoints.
Contains only identifiers, access classification and historical probe status.
No samples, store identifiers, request payloads, notes, tokens, or credentials.

This is an audit inventory, NOT an executable API contract. No entry from this
snapshot can be enabled by loading this module.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from collections import Counter

COLUMNS = (
    "domain",
    "endpoint_key",
    "capability_key",
    "method",
    "path",
    "category",
    "status",
    "selectable",
    "auth",
    "path_verified",
)
_CATALOG_SHA256 = "59baa1b5043b96247b9d896a025a1902e0310e9964a68da32f34869784cffac4"
_CATALOG_GZIP_B64 = (
    "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"
)


def load_source_catalog() -> tuple[dict[str, object], ...]:
    """Decode and validate the immutable, offline source capability inventory."""
    raw = gzip.decompress(base64.b64decode(_CATALOG_GZIP_B64, validate=True))
    if hashlib.sha256(raw).hexdigest() != _CATALOG_SHA256:
        raise ValueError("WALMART_SOURCE_CATALOG_DIGEST_MISMATCH")
    matrix = json.loads(raw)
    if not isinstance(matrix, list) or len(matrix) != 192:
        raise ValueError("WALMART_SOURCE_CATALOG_INVALID")
    records = []
    for values in matrix:
        if not isinstance(values, list) or len(values) != len(COLUMNS):
            raise ValueError("WALMART_SOURCE_CATALOG_INVALID")
        records.append(dict(zip(COLUMNS, values, strict=True)))
    keys = [item["capability_key"] for item in records]
    physical = {(item["method"], item["path"]) for item in records}
    categories = Counter(item["category"] for item in records)
    if (
        len(set(keys)) != 192
        or len(physical) != 143
        or categories != {"read": 120, "write": 71, "auth": 1}
        or sum(item["selectable"] is True for item in records) != 4
    ):
        raise ValueError("WALMART_SOURCE_CATALOG_INTEGRITY_FAILURE")
    return tuple(records)
