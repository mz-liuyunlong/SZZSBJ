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
