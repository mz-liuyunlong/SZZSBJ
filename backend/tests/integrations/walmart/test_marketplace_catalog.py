"""Source-grounded US Marketplace item/order read contract tests."""

from __future__ import annotations

import pytest

from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.marketplace_catalog import marketplace_read_registry


def test_catalog_has_only_registered_read_operations() -> None:
    registry = marketplace_read_registry()
    assert set(registry.keys()) == {
        "items_list",
        "item_get",
        "items_search",
        "orders_list",
        "orders_released",
        "order_get",
    }
    assert all(not registry.get(key).enabled for key in registry.keys())
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("orders_list", params={"createdStartDate": "2026-10-01"})


def test_items_list_parameter_contract() -> None:
    registry = marketplace_read_registry(approved_keys=frozenset({"items_list"}))
    request = registry.prepare(
        "items_list",
        params={"limit": 50, "offset": 0, "publishedStatus": "PUBLISHED"},
    )
    assert request.path == "/v3/items"
    assert request.query == {"limit": 50, "offset": 0, "publishedStatus": "PUBLISHED"}
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("items_list", params={"limit": 51})
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("items_list", params={"publishedStatus": "SUSPENDED"})


def test_item_get_encodes_path_identifier() -> None:
    registry = marketplace_read_registry(approved_keys=frozenset({"item_get"}))
    request = registry.prepare("item_get", params={"itemId": "SKU/1", "productIdType": "SKU"})
    assert request.path == "/v3/items/SKU%2F1"
    assert request.query == {"productIdType": "SKU"}


def test_orders_list_requires_start_date_and_bounds_limit() -> None:
    registry = marketplace_read_registry(approved_keys=frozenset({"orders_list"}))
    with pytest.raises(ContractError, match="WALMART_PARAM_REQUIRED"):
        registry.prepare("orders_list")
    request = registry.prepare(
        "orders_list", params={"createdStartDate": "2026-10-01", "limit": 200}
    )
    assert request.path == "/v3/orders"
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("orders_list", params={"createdStartDate": "2026-10-01", "limit": 201})


def test_released_orders_limit_and_write_rejection() -> None:
    registry = marketplace_read_registry(approved_keys=frozenset({"orders_released"}))
    request = registry.prepare("orders_released", params={"limit": 100})
    assert request.is_write is False
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("orders_released", params={"limit": 101})
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        registry.prepare("orders_released", params={"url": "https://attacker.invalid"})


def test_catalog_rejects_unknown_approval() -> None:
    with pytest.raises(ContractError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        marketplace_read_registry(approved_keys=frozenset({"orders_cancel"}))
