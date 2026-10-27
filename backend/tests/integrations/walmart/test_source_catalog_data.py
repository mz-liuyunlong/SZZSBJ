"""Offline integrity checks for the source capability catalog snapshot.

The source document has 192 business capabilities across 143 physical API
operations. This is not evidence of runtime support or seller authorization.
"""

from __future__ import annotations

import json

from app.integrations.walmart.source_catalog_data import load_source_catalog


def test_source_catalog_keeps_all_192_capability_records() -> None:
    records = load_source_catalog()
    assert len(records) == 192
    assert all(isinstance(record, dict) and record for record in records)


def test_source_catalog_snapshot_is_deterministic_and_independent() -> None:
    first = load_source_catalog()
    second = load_source_catalog()
    assert first == second
    assert first is not second
    assert len({json.dumps(record, sort_keys=True, ensure_ascii=False) for record in first}) == 192


def test_diagnose_original_snapshot_missing_base64_character() -> None:
    """Diagnostic: find and report one damaged Base64 character, never forge records."""
    import base64
    import gzip
    import string

    from app.integrations.walmart.source_catalog_data import _CATALOG_GZIP_B64

    original = _CATALOG_GZIP_B64
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
    matches = []
    # Try the final 200 characters first. The snapshot has invalid Base64 length.
    for index in range(max(0, len(original) - 200), len(original) - 2):
        for char in chars:
            candidate = original[:index] + char + original[index:]
            try:
                data = gzip.decompress(base64.b64decode(candidate, validate=True))
                rows = json.loads(data)
            except (ValueError, OSError, EOFError):
                continue
            if isinstance(rows, list) and len(rows) == 192:
                matches.append((index, char))
    assert matches, "No one-character recovery in final 200 Base64 characters"
    assert False, f"RECOVERY_CANDIDATES: {matches!r}"
