"""US Marketplace inventory, settings and report read contracts."""
from __future__ import annotations

import pytest

from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.operations_catalog import operations_read_registry


def test_operations_catalog_is_closed_by_default() -> None:
    registry = operations_read_registry()
    assert set(registry.keys()) == {
        "inventory_get",
        "inventories_list",
        "partner_profile_get",
        "price_incentives_list",
        "report_requests_list",
        "report_request_status_get",
    }
    assert all(not registry.get(key).enabled for key in registry.keys())
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("inventory_get", params={"sku": "SKU-1"})


def test_single_inventory_requires_sku() -> None:
    registry = operations_read_registry(approved_keys=frozenset({"inventory_get"}))
    request = registry.prepare("inventory_get", params={"sku": "SKU/1", "shipNode": "123"})
    assert request.path == "/v3/inventory"
    assert request.query == {"sku": "SKU/1", "shipNode": "123"}
    assert not request.is_write
    with pytest.raises(ContractError, match="WALMART_PARAM_REQUIRED"):
        registry.prepare("inventory_get")


def test_multi_node_inventory_cursor_and_profile() -> None:
    registry = operations_read_registry(
        approved_keys=frozenset({"inventories_list", "partner_profile_get"})
    )
    assert registry.prepare("inventories_list", params={"nextCursor": "cursor-1"}).path == "/v3/inventories"
    assert registry.prepare("partner_profile_get").path == "/v3/settings/partnerprofile"


def test_incentives_and_report_status_validation() -> None:
    registry = operations_read_registry(
        approved_keys=frozenset({"price_incentives_list", "report_requests_list", "report_request_status_get"})
    )
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("price_incentives_list", params={"limit": 101})
    request = registry.prepare(
        "report_requests_list",
        params={"reportType": "ITEM", "requestStatus": "READY", "src": "API"},
    )
    assert request.query["reportType"] == "ITEM"
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("report_requests_list", params={"reportType": "ITEM", "requestStatus": "DONE"})
    status = registry.prepare("report_request_status_get", params={"requestId": "REQ/1"})
    assert status.path == "/v3/reports/reportRequests/REQ%2F1"


def test_unknown_operation_and_report_create_not_enabled() -> None:
    with pytest.raises(ContractError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        operations_read_registry(approved_keys=frozenset({"report_create"}))
