"""Synthetic source-adapter contracts: no Decodo request or real account data."""

from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.modules.keyword_planning.source_bridge import (
    SourceBridgeBlocked,
    _stored_decodo,
    _walmart_source_fields,
)


def test_walmart_fields_are_only_extracted_from_stored_source_payload() -> None:
    assert _walmart_source_fields(
        {
            "title": "Synthetic pantry bin",
            "brand": "Fixture Brand",
            "category_path": ["Home", "Storage", "Pantry Bins"],
            "attributes": {"Material": "plastic", "Color": "blue"},
        }
    ) == {
        "title": "Synthetic pantry bin",
        "item_type": "Pantry Bins",
        "brand": "Fixture Brand",
        "material": "plastic",
        "color": "blue",
        "pack": "",
        "size": "",
        "structure": "",
        "use": "",
    }


class StoredSession:
    def __init__(self, row: object | None):
        self.row = row
        self.calls = 0

    def execute(self, statement: object, parameters: dict):
        self.calls += 1
        assert "decodo_product_snapshots" in str(statement)
        assert parameters["target"] == "walmart_product"
        return NS(first=lambda: self.row)


@pytest.mark.parametrize(
    "row,code",
    [
        (None, "STORED_SOURCE_DATA_UNAVAILABLE"),
        (NS(payload={"verified": False}, fetched_at=None), "STORED_SOURCE_NOT_VERIFIED"),
        (NS(payload="untrusted", fetched_at=None), "STORED_SOURCE_NOT_VERIFIED"),
    ],
)
def test_stored_adapter_fails_closed_without_verified_evidence(row, code) -> None:
    session = StoredSession(row)
    with pytest.raises(SourceBridgeBlocked, match=code):
        _stored_decodo(session, uuid4(), "walmart_product", uuid4(), "123456")
    assert session.calls == 1


def test_stored_adapter_returns_verified_payload_without_network() -> None:
    payload = {"verified": True, "title": "Synthetic pantry bin"}
    session = StoredSession(NS(payload=payload, fetched_at=None))
    result, _observed_at = _stored_decodo(
        session,
        uuid4(),
        "walmart_product",
        uuid4(),
        "123456",
    )
    assert result == payload
    assert session.calls == 1
