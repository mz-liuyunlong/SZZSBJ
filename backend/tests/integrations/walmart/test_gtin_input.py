"""GTIN source isolation and fail-closed formatting."""

from __future__ import annotations

import csv
import json
from unittest.mock import Mock

import pytest

from app.integrations.walmart.gtin_input import (
    GtinSourceRejected,
    build_gtin_input,
    build_system_gtin_input,
)


def test_missing_gtin_source_denied(monkeypatch, tmp_path):
    monkeypatch.delenv("SZZSBJ_WALMART_GTIN_SOURCES", raising=False)
    with pytest.raises(GtinSourceRejected, match="GTIN_SOURCE_UNCONFIGURED"):
        build_gtin_input(store_code="CN2502", store_id="123456789", directory=tmp_path)


def test_source_mapping_requires_approved_root(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("store_id,item_id,gtin\n123456789,1,12345\n")
    monkeypatch.setenv(
        "SZZSBJ_WALMART_GTIN_SOURCES",
        json.dumps({"CN2502": str(source)}),
    )
    with pytest.raises(GtinSourceRejected, match="GTIN_SOURCE_UNCONFIGURED"):
        build_gtin_input(store_code="CN2502", store_id="123456789", directory=tmp_path)


def test_system_gtin_scoped_rows_and_worker_format(tmp_path):
    session = Mock()
    session.execute.return_value.all.return_value = [
        ("item-1", "00123456789012"), ("item-2", None)
    ]
    generated = build_system_gtin_input(
        session=session, source_account_ref="acct-a",
        store_id="123456789", directory=tmp_path,
    )
    with generated.open(encoding="utf-8", newline="") as handle:
        assert list(csv.reader(handle)) == [
            ["store_id", "item_id", "gtin"],
            ["123456789", "item-1", "00123456789012"],
            ["123456789", "item-2", ""],
        ]
    query = str(session.execute.call_args.args[0])
    assert "dim_walmart_listings" in query
    assert "source_account_ref" in query
    assert "store_id" in query


def test_system_gtin_empty_source_denied(tmp_path):
    session = Mock()
    session.execute.return_value.all.return_value = []
    with pytest.raises(GtinSourceRejected, match="GTIN_SYSTEM_SOURCE_EMPTY"):
        build_system_gtin_input(
            session=session, source_account_ref="acct-a",
            store_id="123456789", directory=tmp_path,
        )
