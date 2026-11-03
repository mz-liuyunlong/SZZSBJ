"""Load verified collection files into ``raw_pmc_wfs_source_files`` + ODS (no external calls).

Accepted layout (the converted output of the approved collectors, identical on the server
archive ``…/daily/<run>/`` and in the local replay folder ``data/daily/<日期>/``)::

    walmart/<store_id>/shipments.csv       → inbound_shipments
    walmart/<store_id>/items.csv           → inbound_shipment_items
    walmart/<store_id>/inventory_log.csv   → inventory_log (only Receipt rows with a shipment)
    zhongyi/orders_summary.csv             → orders_summary
    zhongyi/orders_track.csv               → orders_track
    lingxing/logistics_channels.csv        → logistics_channels

A file whose sha256 is already loaded for the same scope is skipped (idempotent). A newly
loaded file becomes the current one for its ``(source, endpoint, scope_key)``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.pmc_wfs.arrival_rules import parse_date
from app.modules.pmc_wfs.source_models import (
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

WALMART_FILES: Final = {
    "shipments.csv": "inbound_shipments",
    "items.csv": "inbound_shipment_items",
    "inventory_log.csv": "inventory_log",
}
STORE_ID: Final = re.compile(r"^[0-9]{6,32}$")
SCOPE_ALL: Final = "all"


def _channel_payload(row: dict[str, str], raw: dict[str, Any]) -> dict[str, Any]:
    """CSV columns plus the ``raw_json`` fields the 8088 物流看板 reads (method / remark)."""

    payload: dict[str, Any] = {k: v for k, v in row.items() if k != "raw_json"}
    payload.setdefault("method_name", raw.get("method_name") or "")
    payload.setdefault("remark", raw.get("remark") or "")
    payload.setdefault("enabled", str(raw.get("enabled", row.get("is_enable", ""))))
    return payload


class SourceLoadError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LoadedFile:
    source: str
    endpoint: str
    scope_key: str
    path: str
    rows: int
    loaded_rows: int
    skipped: bool


def _rows(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _s(value: str | None, size: int) -> str | None:
    text_value = (value or "").strip()
    return text_value[:size] if text_value else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WfsSourceLoader:
    def __init__(self, session: Session, *, actor: str, batch_label: str) -> None:
        if not actor.strip() or not batch_label.strip():
            raise SourceLoadError("WFS_SOURCE_LOAD_SCOPE_INVALID")
        self.session = session
        self.actor = actor.strip()[:128]
        self.batch = batch_label.strip()[:64]

    def load_directory(self, root: Path) -> list[LoadedFile]:
        """Load every recognised file under ``root``; unknown files are ignored."""

        if root.is_symlink() or not root.is_dir():
            raise SourceLoadError("WFS_SOURCE_ROOT_INVALID")
        results: list[LoadedFile] = []
        walmart = root / "walmart"
        if walmart.is_dir():
            for store_dir in sorted(p for p in walmart.iterdir() if p.is_dir()):
                if not STORE_ID.match(store_dir.name):
                    continue
                for name, endpoint in WALMART_FILES.items():
                    path = store_dir / name
                    if path.is_file():
                        results.append(self._load(SOURCE_WALMART, endpoint, store_dir.name, path))
        for name, endpoint in (
            ("orders_summary.csv", "orders_summary"),
            ("orders_track.csv", "orders_track"),
        ):
            path = root / "zhongyi" / name
            if path.is_file():
                results.append(self._load(SOURCE_ZHONGYI, endpoint, SCOPE_ALL, path))
        channels = root / "lingxing" / "logistics_channels.csv"
        if channels.is_file():
            results.append(self._load(SOURCE_LINGXING, "logistics_channels", SCOPE_ALL, channels))
        self.session.commit()
        return results

    # ---- one file --------------------------------------------------------------------

    def _load(self, source: str, endpoint: str, scope: str, path: Path) -> LoadedFile:
        if path.is_symlink():
            raise SourceLoadError("WFS_SOURCE_FILE_SYMLINK")
        digest = _sha256(path)
        existing = self.session.scalar(
            select(PmcWfsSourceFile).where(
                PmcWfsSourceFile.source == source,
                PmcWfsSourceFile.endpoint == endpoint,
                PmcWfsSourceFile.scope_key == scope,
                PmcWfsSourceFile.sha256 == digest,
            )
        )
        if existing is not None:
            if source == SOURCE_LINGXING and endpoint == "logistics_channels":
                self._backfill_channel_remarks(existing, list(_rows(path)))
            return LoadedFile(
                source, endpoint, scope, str(path), existing.row_count, existing.loaded_rows, True
            )
        rows = list(_rows(path))
        record = PmcWfsSourceFile(
            source=source,
            endpoint=endpoint,
            scope_key=scope,
            batch_label=self.batch,
            source_path=str(path)[-512:],
            sha256=digest,
            byte_size=path.stat().st_size,
            row_count=len(rows),
            loaded_rows=0,
            is_current=False,
            loaded_by=self.actor,
        )
        self.session.add(record)
        self.session.flush()
        loaded = self._insert(source, endpoint, scope, record, rows)
        record.loaded_rows = loaded
        self.session.execute(
            update(PmcWfsSourceFile)
            .where(
                PmcWfsSourceFile.source == source,
                PmcWfsSourceFile.endpoint == endpoint,
                PmcWfsSourceFile.scope_key == scope,
                PmcWfsSourceFile.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()
        record.is_current = True
        self.session.flush()
        return LoadedFile(source, endpoint, scope, str(path), len(rows), loaded, False)

    def _backfill_channel_remarks(
        self, record: PmcWfsSourceFile, rows: list[dict[str, str]]
    ) -> None:
        """Files loaded before 2026-11-03 dropped ``raw_json.remark`` (仓库代码 / 渠道代码 for the
        物流看板); add it to the existing rows in place. Nothing is deleted."""

        by_id = {_s(row.get("channel_id") or row.get("id"), 64): row for row in rows}
        for ods in self.session.scalars(
            select(LingxingLogisticsChannelOds).where(
                LingxingLogisticsChannelOds.file_id == record.id
            )
        ):
            if "remark" in (ods.payload_json or {}):
                continue
            row = by_id.get(ods.channel_id)
            if row is None:
                continue
            try:
                raw = json.loads(row.get("raw_json") or "{}")
            except ValueError:
                raw = {}
            ods.payload_json = _channel_payload(row, raw if isinstance(raw, dict) else {})
        self.session.flush()

    def _insert(
        self,
        source: str,
        endpoint: str,
        scope: str,
        record: PmcWfsSourceFile,
        rows: list[dict[str, str]],
    ) -> int:
        objects: list[Any] = []
        if source == SOURCE_WALMART and endpoint == "inbound_shipments":
            seen: set[str] = set()
            for row in rows:
                shipment = _s(row.get("shipmentId"), 64)
                if not shipment or shipment in seen:
                    continue
                seen.add(shipment)
                objects.append(
                    WalmartWfsInboundShipmentOds(
                        file_id=record.id,
                        store_id=scope,
                        shipment_id=shipment,
                        inbound_order_id=_s(row.get("inboundOrderId"), 128),
                        status=_s(row.get("status"), 64),
                        created_date=parse_date(row.get("createdDate")),
                        actual_delivery_date=parse_date(row.get("actualDeliveryDate")),
                        expected_delivery_date=parse_date(
                            row.get("updatedExpectedDeliveryDate")
                            or row.get("expectedDeliveryDate")
                        ),
                        shipment_units=_int(row.get("shipmentUnits")),
                        received_units=_int(row.get("receivedUnits")),
                        payload_json=dict(row),
                    )
                )
        elif source == SOURCE_WALMART and endpoint == "inbound_shipment_items":
            for ordinal, row in enumerate(rows):
                shipment = _s(row.get("shipmentId"), 64)
                if not shipment:
                    continue
                objects.append(
                    WalmartWfsInboundItemOds(
                        file_id=record.id,
                        line_ordinal=ordinal,
                        store_id=scope,
                        shipment_id=shipment,
                        gtin=_s(row.get("gtin"), 64),
                        sku=_s(row.get("sku"), 255),
                        item_qty=_int(row.get("itemQty")),
                        received_qty=_int(row.get("receivedQty")),
                        damaged_qty=_int(row.get("damagedQty")),
                        payload_json=dict(row),
                    )
                )
        elif source == SOURCE_WALMART and endpoint == "inventory_log":
            for ordinal, row in enumerate(rows):
                shipment = _s(row.get("shipmentId"), 64)
                if row.get("transactionType") != "Receipt" or not shipment:
                    continue
                payload = {k: v for k, v in row.items() if k != "raw_json"}
                objects.append(
                    WalmartWfsReceiptOds(
                        file_id=record.id,
                        line_ordinal=ordinal,
                        store_id=scope,
                        shipment_id=shipment,
                        gtin=_s(row.get("gtin"), 64),
                        transaction_time=_s(row.get("transactionTime"), 40),
                        transaction_date=parse_date(row.get("transactionTime")),
                        changed_units=_int(row.get("changedUnits")),
                        payload_json=payload,
                    )
                )
        elif source == SOURCE_ZHONGYI and endpoint == "orders_summary":
            seen = set()
            for ordinal, row in enumerate(rows):
                number = _s(row.get("number"), 64)
                if not number or number in seen:
                    continue
                seen.add(number)
                objects.append(
                    CarrierZhongyiOrderOds(
                        file_id=record.id,
                        line_ordinal=ordinal,
                        order_number=number,
                        customer_number=_s(row.get("customerNumber"), 128),
                        status=_s(row.get("status"), 64),
                        total_weight_kg=_s(row.get("totalWeightKg"), 32),
                        payload_json={k: v for k, v in row.items() if k != "details"},
                    )
                )
        elif source == SOURCE_ZHONGYI and endpoint == "orders_track":
            for ordinal, row in enumerate(rows):
                number = _s(row.get("orderNumber"), 64)
                if not number:
                    continue
                objects.append(
                    CarrierZhongyiTrackOds(
                        file_id=record.id,
                        line_ordinal=ordinal,
                        order_number=number,
                        track_time=_s(row.get("trackTime"), 40),
                        name=row.get("name") or None,
                        payload_json=dict(row),
                    )
                )
        elif source == SOURCE_LINGXING and endpoint == "logistics_channels":
            for row in rows:
                channel = _s(row.get("channel_id") or row.get("id"), 64)
                if not channel:
                    continue
                try:
                    raw = json.loads(row.get("raw_json") or "{}")
                except ValueError:
                    raw = {}
                raw = raw if isinstance(raw, dict) else {}
                objects.append(
                    LingxingLogisticsChannelOds(
                        file_id=record.id,
                        channel_id=channel,
                        channel_name=_s(row.get("channel_name") or row.get("name"), 255),
                        provider_id=_s(row.get("provider_id"), 64),
                        provider_name=_s(row.get("provider_name"), 255),
                        method_name=_s(row.get("method_name") or raw.get("method_name"), 128),
                        enabled=_s(
                            str(row.get("enabled") or raw.get("enabled", row.get("is_enable", ""))),
                            16,
                        ),
                        payload_json=_channel_payload(row, raw),
                    )
                )
        else:  # pragma: no cover - guarded by the caller's fixed mapping
            raise SourceLoadError("WFS_SOURCE_ENDPOINT_UNKNOWN")
        self.session.add_all(objects)
        self.session.flush()
        return len(objects)
