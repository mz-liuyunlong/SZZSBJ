"""Tests for the migrated four-endpoint collector; all transport calls are fake."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.integrations.walmart.client import WalmartResult
from app.integrations.walmart.collector import (
    CollectorConfig,
    CollectorError,
    WalmartReadCollector,
)


class FakeClient:
    def __init__(self, responses: dict[str, list[tuple[int, Any]]]) -> None:
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, store_code: str, operation: str, *, params=None, **kwargs) -> WalmartResult:
        self.calls.append((operation, dict(params or {})))
        queue = self.responses.get(operation, [])
        if not queue:
            return WalmartResult(200, {"payload": {"inventory": []}, "headers": {"totalCount": 0}})
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        if status in (401, 403):
            raise RuntimeError("WALMART_AUTH_FAILED")
        return WalmartResult(status, body)


def test_wfs_nested_payload_pagination_and_hashes() -> None:
    client = FakeClient({
        "wfs_inventory": [
            (200, {"payload": {"inventory": [{"sku": "SKU1"}]}, "headers": {"totalCount": 2}}),
            (200, {"payload": {"inventory": [{"sku": "SKU2"}]}, "headers": {"totalCount": 2}}),
        ]
    })
    collector = WalmartReadCollector(
        client, store_code="HK2615", config=CollectorConfig(page_size=1, max_pages=5)
    )
    result = collector.collect(
        endpoints=["wfs_inventory"], from_date=date(2026, 10, 1), to_date=date(2026, 10, 2)
    )
    assert result["manifest"]["status"] == "SUCCESS"
    assert [row["sku"] for row in result["records"]["wfs_inventory"]] == ["SKU1", "SKU2"]
    assert [call[1]["offset"] for call in client.calls] == [0, 1]
    assert "SHA256SUMS" in result["artifacts"]
    assert result["manifest"]["files"]["raw/wfs_inventory.jsonl"]["records"] == 2


def test_incomplete_paging_is_failed_not_success() -> None:
    client = FakeClient({
        "wfs_inventory": [
            (200, {"payload": {"inventory": [{"sku": "SKU1"}]}, "headers": {"totalCount": 2}}),
            (200, {"payload": {"inventory": []}, "headers": {"totalCount": 2}}),
        ]
    })
    result = WalmartReadCollector(
        client, store_code="HK2615", config=CollectorConfig(page_size=1, max_pages=5)
    ).collect(endpoints=["wfs_inventory"], from_date=date(2026, 10, 1), to_date=date(2026, 10, 2))
    assert result["manifest"]["status"] == "PARTIAL"
    assert result["manifest"]["endpoints"]["wfs_inventory"]["error_code"] == "WALMART_INCOMPLETE_PAGING"


def test_auth_failure_skips_remaining_selected_endpoints() -> None:
    client = FakeClient({"wfs_inventory": [(401, {"error": "secret must not be logged"})]})
    result = WalmartReadCollector(client, store_code="HK2615").collect(
        endpoints=["wfs_inventory", "inbound_shipments"],
        from_date=date(2026, 10, 1), to_date=date(2026, 10, 2),
    )
    assert result["manifest"]["status"] == "AUTH_FAILED"
    assert result["manifest"]["endpoints"]["wfs_inventory"]["status"] == "AUTH_FAILED"
    assert result["manifest"]["endpoints"]["inbound_shipments"]["status"] == "SKIPPED_AUTH_FAILED"
    assert len(client.calls) == 1
    assert "secret must not be logged" not in str(result["artifacts"])


def test_inventory_log_requires_explicit_gtin_source_and_deduplicates() -> None:
    client = FakeClient({"inventory_log": [(200, {"inventoryLog": [{"id": 1}]})]})
    collector = WalmartReadCollector(client, store_code="HK2615")
    result = collector.collect(
        endpoints=["inventory_log"], from_date=date(2026, 10, 1), to_date=date(2026, 10, 2),
        gtin_items=[
            {"item_id": "A", "gtin": "12345670"},
            {"item_id": "B", "gtin": "12345670"},
            {"item_id": "C", "gtin": ""},
            {"item_id": "D", "gtin": "not-a-gtin"},
        ],
    )
    assert len([call for call in client.calls if call[0] == "inventory_log"]) == 1
    assert result["manifest"]["status"] == "SUCCESS"
    item_file = result["artifacts"]["raw/inventory_log_items.jsonl"]
    assert '"item_id": "B"' in item_file
    assert "DUPLICATE_GTIN" in item_file
    assert "INVALID_GTIN" in item_file
    assert "WALMART_CLIENT_SECRET" not in str(result["artifacts"])


def test_no_gtin_does_not_call_walmart_and_write_keys_are_rejected() -> None:
    client = FakeClient({})
    collector = WalmartReadCollector(client, store_code="HK2615")
    result = collector.collect(
        endpoints=["inventory_log"], from_date=date(2026, 10, 1), to_date=date(2026, 10, 2),
        gtin_items=[{"item_id": "A", "gtin": ""}],
    )
    assert client.calls == []
    assert result["manifest"]["endpoints"]["inventory_log"]["status"] == "MISSING_GTIN_DEPENDENCY"
    with pytest.raises(CollectorError, match="WALMART_NON_READ_CAPABILITY_REJECTED"):
        collector.collect(
            endpoints=["orders_cancel"], from_date=date(2026, 10, 1), to_date=date(2026, 10, 2)
        )


def test_inbound_shipment_date_filters_use_worker_epoch_milliseconds() -> None:
    client = FakeClient({
        "inbound_shipments": [
            (200, {"inboundShipments": [], "headers": {"totalCount": 0}})
        ]
    })
    WalmartReadCollector(client, store_code="HK2615").collect(
        endpoints=["inbound_shipments"],
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 2),
    )
    params = client.calls[0][1]
    assert params["fromCreatedDate"] == 1790812800000
    assert params["toCreatedDate"] == 1790985599999
