"""GTIN source isolation and fail-closed formatting."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.integrations.walmart.gtin_input import GtinSourceRejected, build_gtin_input


def test_missing_gtin_source_denied(monkeypatch, tmp_path):
    monkeypatch.delenv("SZZSBJ_WALMART_GTIN_SOURCES", raising=False)
    with pytest.raises(GtinSourceRejected, match="GTIN_SOURCE_UNCONFIGURED"):
        build_gtin_input(
            store_code="CN2502", store_id="123456789", directory=tmp_path
        )


def test_source_mapping_requires_approved_root(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("store_id,item_id,gtin\n123456789,1,12345\n")
    monkeypatch.setenv(
        "SZZSBJ_WALMART_GTIN_SOURCES",
        json.dumps({"CN2502": str(source)}),
    )
    with pytest.raises(GtinSourceRejected, match="GTIN_SOURCE_UNCONFIGURED"):
        build_gtin_input(
            store_code="CN2502", store_id="123456789", directory=tmp_path
        )
