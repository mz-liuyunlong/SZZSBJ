"""Read the current file-sourced ODS rows into :class:`BoardFacts` (8088 ``walmart_facts`` +
``carrier_nodes`` + channel dictionary). Missing tables or files give empty facts."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any, Final

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.modules.pmc_wfs.arrival_rules import CarrierNodes, WalmartFacts, parse_date
from app.modules.pmc_wfs.board_derivations import BoardFacts
from app.modules.pmc_wfs.source_models import (
    SOURCE_FILE_TABLES,
    SOURCE_LINGXING,
    SOURCE_WALMART,
    SOURCE_ZHONGYI,
    CarrierZhongyiOrderOds,
    CarrierZhongyiTrackOds,
    LingxingLogisticsChannelOds,
    PmcWfsSourceFile,
    WalmartWfsInboundItemOds,
    WalmartWfsInboundShipmentOds,
    WalmartWfsReceiptOds,
)

_DATE: Final = re.compile(r"(\d{4}-\d{2}-\d{2})")
_EST_DELIVERY: Final = re.compile(r"预计美国时间\s*(\d{4}-\d{2}-\d{2}).*派送入仓")


def _zdate(value: str) -> date | None:
    match = _DATE.search(value or "")
    return parse_date(match.group(1)) if match else None


def source_tables_ready(session: Session) -> bool:
    connection = session.connection()
    return all(inspect(connection).has_table(name) for name in SOURCE_FILE_TABLES)


def _current(session: Session, source: str, endpoint: str) -> dict[Any, PmcWfsSourceFile]:
    files = session.scalars(
        select(PmcWfsSourceFile).where(
            PmcWfsSourceFile.source == source,
            PmcWfsSourceFile.endpoint == endpoint,
            PmcWfsSourceFile.is_current.is_(True),
        )
    )
    return {f.id: f for f in files}


def carrier_nodes(tracks: list[tuple[str, str | None, str | None]]) -> dict[str, CarrierNodes]:
    """Port of 8088 ``carrier_nodes``: rows (order_number, track_time, name) → nodes."""

    raw: dict[str, dict[str, date | None]] = defaultdict(dict)
    for number, track_time, name in sorted(tracks, key=lambda r: r[1] or ""):
        name = name or ""
        day = parse_date(track_time)
        node = raw[number]
        if (
            name.startswith("官网更新开船时间")
            or name.startswith("船司变更开船时间")
            or ("开船时间延" in name)
        ):
            node["etd"] = _zdate(name[6:]) or node.get("etd")
        elif name == "已开船":
            node["atd"] = day
        elif (
            name.startswith("预计到港时间")
            or name.startswith("船司变更到港时间")
            or name.startswith("预计延迟到")
        ):
            node["eta"] = _zdate(name[4:]) or node.get("eta")
        elif name.startswith("已靠港"):
            node["ata"] = day
        elif name == "签收完成":
            node["delivered"] = day
        match = _EST_DELIVERY.search(name)
        if match:
            node["est_delivery"] = parse_date(match.group(1))
    return {
        number: CarrierNodes(
            delivered=node.get("delivered"),
            atd=node.get("atd"),
            eta=node.get("eta"),
            ata=node.get("ata"),
            est_delivery=node.get("est_delivery"),
        )
        for number, node in raw.items()
    }


def load_board_facts(session: Session) -> BoardFacts:
    facts = BoardFacts()
    if not source_tables_ready(session):
        facts.sources = {"ready": False}
        return facts
    sources: dict[str, Any] = {"ready": True}

    channel_files = _current(session, SOURCE_LINGXING, "logistics_channels")
    if channel_files:
        for row in session.scalars(
            select(LingxingLogisticsChannelOds).where(
                LingxingLogisticsChannelOds.file_id.in_(channel_files)
            )
        ):
            facts.channel_names[row.channel_id] = row.channel_name or ""
    sources["logistics_channels"] = len(facts.channel_names)

    wm = WalmartFacts()
    ship_files = _current(session, SOURCE_WALMART, "inbound_shipments")
    wm.stores = {f.scope_key for f in ship_files.values()}
    if ship_files:
        for row in session.scalars(
            select(WalmartWfsInboundShipmentOds).where(
                WalmartWfsInboundShipmentOds.file_id.in_(ship_files)
            )
        ):
            wm.shipments.add(row.shipment_id)
            if row.actual_delivery_date:
                wm.signed[row.shipment_id] = row.actual_delivery_date
            if row.received_units is not None:
                wm.received_units[row.shipment_id] = row.received_units
    item_files = _current(session, SOURCE_WALMART, "inbound_shipment_items")
    if item_files:
        for item in session.scalars(
            select(WalmartWfsInboundItemOds).where(WalmartWfsInboundItemOds.file_id.in_(item_files))
        ):
            if not item.gtin:
                continue
            received = wm.item_received.setdefault(item.shipment_id, {})
            received[item.gtin] = received.get(item.gtin, 0) + (item.received_qty or 0)
            damaged = wm.item_damaged.setdefault(item.shipment_id, {})
            damaged[item.gtin] = damaged.get(item.gtin, 0) + (item.damaged_qty or 0)
    receipt_files = _current(session, SOURCE_WALMART, "inventory_log")
    if receipt_files:
        for rec in session.scalars(
            select(WalmartWfsReceiptOds).where(WalmartWfsReceiptOds.file_id.in_(receipt_files))
        ):
            shipment, day = rec.shipment_id, rec.transaction_date
            units = rec.changed_units or 0
            wm.shipments.add(shipment)
            wm.receipt_units[shipment] = wm.receipt_units.get(shipment, 0) + units
            if rec.gtin:
                per_gtin = wm.receipt_units_by_gtin.setdefault(shipment, {})
                per_gtin[rec.gtin] = per_gtin.get(rec.gtin, 0) + units
            if not day:
                continue
            if shipment not in wm.first_receipt or day < wm.first_receipt[shipment]:
                wm.first_receipt[shipment] = day
            if shipment not in wm.last_receipt or day > wm.last_receipt[shipment]:
                wm.last_receipt[shipment] = day
            if rec.gtin:
                by_gtin = wm.first_receipt_by_gtin.setdefault(shipment, {})
                if rec.gtin not in by_gtin or day < by_gtin[rec.gtin]:
                    by_gtin[rec.gtin] = day
    facts.walmart = wm
    sources["walmart_stores"] = sorted(wm.stores)
    sources["walmart_batches"] = sorted({f.batch_label for f in ship_files.values()})

    track_files = _current(session, SOURCE_ZHONGYI, "orders_track")
    delivered_at: dict[str, str] = {}
    if track_files:
        rows = [
            tuple(r)
            for r in session.execute(
                select(
                    CarrierZhongyiTrackOds.order_number,
                    CarrierZhongyiTrackOds.track_time,
                    CarrierZhongyiTrackOds.name,
                )
                .where(CarrierZhongyiTrackOds.file_id.in_(track_files))
                .order_by(CarrierZhongyiTrackOds.line_ordinal)
            )
        ]
        facts.carrier_by_number = carrier_nodes(rows)
        for number, track_time, name in rows:
            if name == "签收完成":
                delivered_at.setdefault(number, (track_time or "")[:16])
    order_files = _current(session, SOURCE_ZHONGYI, "orders_summary")
    if order_files:
        for order in session.scalars(
            select(CarrierZhongyiOrderOds)
            .where(CarrierZhongyiOrderOds.file_id.in_(order_files))
            .order_by(CarrierZhongyiOrderOds.line_ordinal)
        ):
            if order.customer_number:
                facts.carrier_number_by_customer.setdefault(
                    order.customer_number, order.order_number
                )
                # 8088 build_from_daily: customerNumber = cargo code; later rows win.
                if order.order_number in delivered_at:
                    facts.carrier_delivered_by_customer[order.customer_number] = delivered_at[
                        order.order_number
                    ]
    sources["carrier_orders"] = len(facts.carrier_by_number)
    facts.sources = sources
    return facts
