"""8088 shipment-board derivations computed at publish time (``build_from_daily.py`` +
``app-a.jsx`` ``enrich``), stored under ``payload_json["derived"]`` of each board row.

Only date-stable facts are stored here. Anything relative to "today" (arrival bucket,
days overdue) is computed when the board is read, so a published version never goes stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, Protocol

from app.modules.pmc_wfs.arrival_rules import (
    CarrierNodes,
    ShippingFacts,
    SpArrival,
    WalmartFacts,
    cargo_arrival,
    is_its_node,
    region_of_state,
    sellable_date,
    sp_arrival,
    state_from_address,
)

DERIVED_VERSION: Final = "wfs_board_derived.v1"
TEST_INBOUND_PREFIX: Final = "PMC-TEST-"


class CargoLike(Protocol):
    cargo_code: str | None
    cargo_status: str | None
    in_bound_order_id: str | None
    logistics_code: str | None
    distribution_addresses: str | None
    shipping_list_codes: list[str]


class ShippingLike(Protocol):
    shipping_code: str
    shipping_status: str | None
    logistics_code: str | None
    logistics_channel_id: str | None
    delivery_time: str | None
    actual_delivery_time: str | None
    sail_time: str | None
    arrival_time: str | None
    expected_arrival_time: str | None
    cargo_codes: list[str]
    logistics_numbers: list[str]
    tracking_numbers: list[str]
    payload_json: dict[str, Any]


@dataclass(slots=True)
class BoardFacts:
    """External facts the 8088 rules read besides Lingxing cargo / shipping lists.

    Each source is optional; a missing source leaves its fields empty (never invented).
    """

    channel_names: dict[str, str] = field(default_factory=dict)
    walmart: WalmartFacts = field(default_factory=WalmartFacts)
    carrier_by_number: dict[str, CarrierNodes] = field(default_factory=dict)
    carrier_number_by_customer: dict[str, str] = field(default_factory=dict)
    carrier_delivered_by_customer: dict[str, str] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _shipping_goods(shipping: ShippingLike) -> list[dict[str, Any]]:
    goods = (shipping.payload_json or {}).get("shipping_goods")
    return [g for g in goods if isinstance(g, dict)] if isinstance(goods, list) else []


def _carrier_for(shipping: ShippingLike, facts: BoardFacts) -> CarrierNodes | None:
    for number in [*(shipping.tracking_numbers or []), *(shipping.logistics_numbers or [])]:
        if number in facts.carrier_by_number:
            return facts.carrier_by_number[number]
    for code in shipping.cargo_codes or []:
        number = facts.carrier_number_by_customer.get(code)
        if number and number in facts.carrier_by_number:
            return facts.carrier_by_number[number]
    return None


def fc_regions(cargos: Iterable[CargoLike]) -> dict[str, str]:
    regions: dict[str, str] = {}
    for cargo in cargos:
        state = state_from_address(cargo.distribution_addresses)
        if cargo.logistics_code and state:
            regions.setdefault(cargo.logistics_code, region_of_state(state))
    return regions


def sp_arrivals(
    shipping_lists: Sequence[ShippingLike],
    regions: Mapping[str, str],
    facts: BoardFacts,
    as_of: date,
) -> dict[str, SpArrival]:
    out: dict[str, SpArrival] = {}
    for shipping in shipping_lists:
        sp = ShippingFacts(
            shipping_code=shipping.shipping_code,
            status=shipping.shipping_status,
            region=regions.get(shipping.logistics_code or "", "待定"),
            channel_name=facts.channel_names.get(shipping.logistics_channel_id or ""),
            delivery_time=shipping.delivery_time,
            actual_delivery_time=shipping.actual_delivery_time,
            sail_time=shipping.sail_time,
            arrival_time=shipping.arrival_time,
            expected_arrival_time=shipping.expected_arrival_time,
            cargo_codes=tuple(shipping.cargo_codes or ()),
            carrier=_carrier_for(shipping, facts),
        )
        out[shipping.shipping_code] = sp_arrival(sp, as_of, facts.walmart.signed)
    return out


def derive_cargo(
    cargo: CargoLike,
    linked_shipping: Sequence[ShippingLike],
    sp_map: Mapping[str, SpArrival],
    facts: BoardFacts,
) -> dict[str, Any]:
    code = cargo.cargo_code or ""
    sp_goods = [
        {
            "shipping_code": shipping.shipping_code,
            "msku": good.get("msku"),
            "sku": good.get("sku"),
            "shipped": _int(good.get("shipments_num")),
            "boxes": _int(good.get("box_num")),
            "per_box": _int(good.get("quantity_in_case")),
        }
        for shipping in linked_shipping
        for good in _shipping_goods(shipping)
        if good.get("cargo_code") == code
    ]
    arrival = cargo_arrival(
        cargo_code=code,
        cargo_status=cargo.cargo_status,
        shipping_codes=cargo.shipping_list_codes or [],
        sp_map=sp_map,
        walmart_signed=facts.walmart.signed,
    )
    first_receipt = facts.walmart.first_receipt.get(code)
    sellable, sellable_real = sellable_date(first_receipt, arrival.date)
    state = state_from_address(cargo.distribution_addresses)
    return {
        "version": DERIVED_VERSION,
        "is_test": (cargo.in_bound_order_id or "").startswith(TEST_INBOUND_PREFIX),
        "region": region_of_state(state),
        "its_inferred": is_its_node(cargo.logistics_code),
        "sp_goods": sp_goods,
        "sp_shipped_units": sum(g["shipped"] for g in sp_goods),
        "sp_boxes": sum(g["boxes"] for g in sp_goods),
        "arrival_date": _iso(arrival.date),
        "arrival_source": arrival.source,
        "arrival_real": arrival.real,
        "shipped_out": arrival.shipped,
        "sellable_date": _iso(sellable),
        "sellable_real": sellable_real,
        "carrier_delivered_at": facts.carrier_delivered_by_customer.get(code),
        "walmart_has_shipment": code in facts.walmart.shipments,
        "walmart_signed_date": _iso(facts.walmart.signed.get(code)),
        "walmart_first_receipt": _iso(first_receipt),
        "walmart_last_receipt": _iso(facts.walmart.last_receipt.get(code)),
        "walmart_receipt_by_gtin": {
            gtin: _iso(day)
            for gtin, day in facts.walmart.first_receipt_by_gtin.get(code, {}).items()
        },
        "walmart_receipt_units": facts.walmart.receipt_units.get(code),
        "walmart_receipt_units_by_gtin": dict(facts.walmart.receipt_units_by_gtin.get(code, {})),
        "walmart_received_units": facts.walmart.received_units.get(code),
        "walmart_item_received": dict(facts.walmart.item_received.get(code, {})),
        "walmart_item_damaged": dict(facts.walmart.item_damaged.get(code, {})),
    }
