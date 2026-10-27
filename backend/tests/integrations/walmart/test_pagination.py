"""Offline pagination tests, with no credentials, network, or database."""
from __future__ import annotations

from typing import Any

import pytest

from app.integrations.walmart.client import WalmartResult
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.pagination import PageContract, PaginationRejected, collect_read_pages


class FakeClient:
    def __init__(self, bodies: list[dict[str, Any]]) -> None:
        self.bodies = iter(bodies)
        self.calls: list[dict[str, Any]] = []
        self.registry = ContractRegistry.from_openapi(
            {
                "openapi": "3.0.3",
                "paths": {
                    "/v3/items": {
                        "get": {
                            "operationId": "listItems",
                            "parameters": [
                                {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                                {"name": "offset", "in": "query", "schema": {"type": "integer"}},
                                {"name": "nextCursor", "in": "query", "schema": {"type": "string"}},
                            ],
                        }
                    }
                },
            },
            approved_keys=frozenset({"listItems"}),
        )

    def call(self, store_code: str, operation: str, **kwargs: Any) -> WalmartResult:
        self.calls.append(kwargs["params"])
        return WalmartResult(status_code=200, data=next(self.bodies))


def contract(mode: str = "offset") -> PageContract:
    return PageContract(
        operation="listItems",
        items_path=("items",),
        mode=mode,
        total_path=("total",),
        next_cursor_path=("nextCursor",),
    )


def test_complete_offset_pages() -> None:
    client = FakeClient([
        {"items": [{"id": 1}, {"id": 2}], "total": 3},
        {"items": [{"id": 3}], "total": 3},
    ])
    rows = collect_read_pages(
        client, store_code="HK2615", contract=contract(), page_size=2
    )
    assert len(rows) == 3
    assert [call["offset"] for call in client.calls] == [0, 2]


def test_incomplete_offset_rejected() -> None:
    client = FakeClient([
        {"items": [{"id": 1}], "total": 3},
        {"items": [], "total": 3},
    ])
    with pytest.raises(PaginationRejected, match="WALMART_PAGE_LIMIT_REACHED"):
        collect_read_pages(client, store_code="HK2615", contract=contract(), page_size=2, max_pages=1)


def test_cursor_loop_rejected() -> None:
    client = FakeClient([
        {"items": [{"id": 1}], "total": 3, "nextCursor": "one"},
        {"items": [{"id": 2}], "total": 3, "nextCursor": "one"},
    ])
    with pytest.raises(PaginationRejected, match="WALMART_PAGE_CURSOR_LOOP"):
        collect_read_pages(client, store_code="HK2615", contract=contract("cursor"), page_size=2)


def test_page_item_limit_and_shape_rejected() -> None:
    client = FakeClient([{"items": [{"id": 1}, {"id": 2}], "total": 3}])
    with pytest.raises(PaginationRejected, match="WALMART_PAGE_ITEM_LIMIT_EXCEEDED"):
        collect_read_pages(
            client, store_code="HK2615", contract=contract(), page_size=2, max_items=1
        )
    wrong = FakeClient([{"items": {"invalid": 1}, "total": 1}])
    with pytest.raises(PaginationRejected, match="WALMART_PAGE_SHAPE_CHANGED"):
        collect_read_pages(wrong, store_code="HK2615", contract=contract(), page_size=2)
