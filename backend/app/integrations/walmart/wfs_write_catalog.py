"""Reviewed WFS inbound-shipment write contracts (PMC WFS creation flow).

Every operation here is mutating and fails closed: it is disabled unless its key is in the
owner-approved write set, and the client still demands an ``approval_ref`` per call.
Field shapes follow the requests that were executed against production in Sep–Oct 2026
(handover chapter 24); this module never performs network I/O.
"""

from __future__ import annotations

from typing import Any

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation

WFS_WRITE_KEYS: frozenset[str] = frozenset(
    {
        "wfs_inbound_shipment_create",
        "wfs_shipment_label",
        "wfs_inbound_preview",
        "wfs_inbound_shipment_cancel",
        "wfs_shipment_quantities",
        "wfs_shipment_tracking",
    }
)

_ORDER_ID = {"type": "string", "minLength": 1, "maxLength": 64, "pattern": r"^[A-Za-z0-9._-]+$"}
_SHIPMENT_ID = {"type": "string", "minLength": 1, "maxLength": 32, "pattern": r"^[A-Za-z0-9]+$"}

_RETURN_ADDRESS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "addressLine1": {"type": "string", "minLength": 1, "maxLength": 200},
        "addressLine2": {"type": "string", "maxLength": 200},
        "city": {"type": "string", "minLength": 1, "maxLength": 100},
        "stateCode": {"type": "string", "pattern": r"^[A-Z]{2}$"},
        "countryCode": {"type": "string", "enum": ["US"]},
        "postalCode": {"type": "string", "pattern": r"^\d{5}(-\d{4})?$"},
    },
    "required": ["addressLine1", "city", "stateCode", "countryCode", "postalCode"],
    "additionalProperties": False,
}

_ORDER_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "productId": {"type": "string", "pattern": r"^\d{14}$"},
        "productType": {"type": "string", "enum": ["GTIN"]},
        "sku": {"type": "string", "minLength": 1, "maxLength": 100},
        "itemDesc": {"type": "string", "minLength": 1, "maxLength": 500},
        "itemQty": {"type": "integer", "minimum": 1, "maximum": 1_000_000},
        "vendorPackQty": {"type": "integer", "minimum": 1, "maximum": 9_999},
        "innerPackQty": {"type": "integer", "minimum": 1, "maximum": 100_000},
        "expectedDeliveryDate": {"type": "string", "minLength": 20, "maxLength": 30},
    },
    "required": [
        "productId",
        "productType",
        "sku",
        "itemDesc",
        "itemQty",
        "vendorPackQty",
        "innerPackQty",
        "expectedDeliveryDate",
    ],
    "additionalProperties": False,
}

# Shared by create (W1) and preview (W3, wrapped in header/payload).
INBOUND_ORDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "inboundOrderId": _ORDER_ID,
        "returnAddress": _RETURN_ADDRESS,
        "orderItems": {"type": "array", "minItems": 1, "maxItems": 20, "items": _ORDER_ITEM},
        "inboundServices": {
            "type": "object",
            "properties": {"inventoryTransferService": {"type": "string", "enum": ["Y", "N"]}},
            "additionalProperties": False,
        },
    },
    "required": ["inboundOrderId", "orderItems"],
    "additionalProperties": False,
}

LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "shipmentId": _SHIPMENT_ID,
        "labelSize": {"type": "string", "enum": ["X4_6"]},
        "labelFormat": {"type": "string", "enum": ["PDF"]},
        "loadTypes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "loadType": {"type": "string", "enum": ["SINGLE SKU", "MIXED SKUS"]},
                    # Walmart wants the carton count as a string.
                    "count": {"type": "string", "pattern": r"^[1-9]\d{0,4}$"},
                },
                "required": ["loadType", "count"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["shipmentId", "labelSize", "labelFormat", "loadTypes"],
    "additionalProperties": False,
}

PREVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "header": {
            "type": "object",
            "properties": {"headerAttributes": {"type": "object"}},
            "required": ["headerAttributes"],
            "additionalProperties": False,
        },
        "payload": INBOUND_ORDER_SCHEMA,
    },
    "required": ["header", "payload"],
    "additionalProperties": False,
}

QUANTITIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "inboundOrderId": _ORDER_ID,
        "shipmentId": _SHIPMENT_ID,
        "orderItems": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "minLength": 1, "maxLength": 100},
                    "updatedShipmentQty": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
                },
                "required": ["sku", "updatedShipmentQty"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["inboundOrderId", "shipmentId", "orderItems"],
    "additionalProperties": False,
}

TRACKING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "shipmentId": _SHIPMENT_ID,
        "carrierName": {"type": "string", "minLength": 1, "maxLength": 50},
        "trackingInfo": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {"type": "string", "pattern": r"^[A-Za-z0-9-]{6,40}$"},
        },
    },
    "required": ["shipmentId", "carrierName", "trackingInfo"],
    "additionalProperties": False,
}


def wfs_write_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    if approved_keys - WFS_WRITE_KEYS:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
    source = "pmc-wfs-exec-2026-10"

    def body_op(
        key: str, method: str, path: str, schema: dict[str, Any], **extra: Any
    ) -> Operation:
        return Operation(
            key=key,
            method=method,
            path=path,
            fields=(),
            has_body=True,
            body_required=True,
            request_schema=schema,
            source=source,
            enabled=key in approved_keys,
            mutating=True,
            **extra,
        )

    operations = (
        body_op(
            "wfs_inbound_shipment_create",
            "POST",
            "/v3/fulfillment/inbound-shipments",
            INBOUND_ORDER_SCHEMA,
        ),
        body_op(
            "wfs_shipment_label",
            "POST",
            "/v3/fulfillment/shipment-label",
            LABEL_SCHEMA,
            response_kind="pdf",
        ),
        # Query-style POST (no shipment is created) but kept mutating so it still needs an
        # approval_ref and never travels through the read-only API.
        body_op("wfs_inbound_preview", "POST", "/v3/fulfillment/inbound-preview", PREVIEW_SCHEMA),
        Operation(
            key="wfs_inbound_shipment_cancel",
            method="DELETE",
            path="/v3/fulfillment/inbound-shipments/{inboundOrderId}",
            fields=(Field(name="inboundOrderId", location="path", required=True),),
            source=source,
            enabled="wfs_inbound_shipment_cancel" in approved_keys,
            mutating=True,
        ),
        body_op(
            "wfs_shipment_quantities",
            "PUT",
            "/v3/fulfillment/shipment-quantities",
            QUANTITIES_SCHEMA,
        ),
        body_op(
            "wfs_shipment_tracking",
            "POST",
            "/v3/fulfillment/shipment-tracking",
            TRACKING_SCHEMA,
        ),
    )
    return ContractRegistry(operations)
