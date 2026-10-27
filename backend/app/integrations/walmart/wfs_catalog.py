"""Reviewed starter contracts for the colleague's four read capabilities.

These are source-derived GET candidates, not blanket Walmart entitlement.
Only explicitly owner-approved keys are enabled, all others fail closed.
"""
from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation


def wfs_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    all_keys = {
        "wfs_inventory",
        "inbound_shipments",
        "inbound_shipment_items",
        "inventory_log",
    }
    if approved_keys - all_keys:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")

    def field(name: str, kind: str = "string", required: bool = False) -> Field:
        return Field(name=name, location="query", kind=kind, required=required)

    operations = (
        Operation(
            key="wfs_inventory",
            method="GET",
            path="/v3/wfs/inventory",
            fields=(field("limit", "integer"), field("offset", "integer")),
            source="colleague-worker-v1.3.2",
            enabled="wfs_inventory" in approved_keys,
        ),
        Operation(
            key="inbound_shipments",
            method="GET",
            path="/v3/fulfillment/inbound-shipments",
            fields=(
                field("limit", "integer"),
                field("offset", "integer"),
                field("fromCreateDate"),
                field("toCreateDate"),
                field("shipmentId"),
                field("inboundOrderId"),
                field("status"),
            ),
            source="walmart-official-2026-10",
            enabled="inbound_shipments" in approved_keys,
        ),
        Operation(
            key="inbound_shipment_items",
            method="GET",
            path="/v3/fulfillment/inbound-shipment-items",
            fields=(
                field("shipmentId", required=True),
                field("limit", "integer"),
                field("offset", "integer"),
            ),
            source="colleague-worker-v1.3.2",
            enabled="inbound_shipment_items" in approved_keys,
        ),
        Operation(
            key="inventory_log",
            method="GET",
            path="/v3/fulfillment/inventory-log",
            fields=(
                field("gtin", required=True),
                field("startDate"),
                field("endDate"),
                field("shipmentId"),
                field("transactionType"),
                field("transactionLocation"),
                field("sort_by"),
                field("sort_order"),
                field("limit", "integer"),
                field("offset", "integer"),
            ),
            source="walmart-official-2026-10",
            enabled="inventory_log" in approved_keys,
        ),
    )
    return ContractRegistry(operations)
