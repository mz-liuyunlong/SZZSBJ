"""Verified CSV to four Walmart remote business tables; one atomic transaction.

The remote run and local CSV hashes are revalidated before any database write.
No Lingxing-owned listing, inventory or financial rows are overwritten.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.integrations.walmart.remote_dispatch import (
    ALLOWED_KEYS,
    RUN_PATTERN,
    DispatchRejected,
    verify_result,
)
from app.modules.walmart_remote.business_models import (
    WalmartRemoteInboundItem,
    WalmartRemoteInboundShipment,
    WalmartRemoteIngestBatch,
    WalmartRemoteInventoryLog,
    WalmartRemoteWfsInventory,
)

MODELS = {
    "wfs_inventory": (WalmartRemoteWfsInventory, "wfs_inventory.csv"),
    "inbound_shipments": (WalmartRemoteInboundShipment, "shipments.csv"),
    "inbound_shipment_items": (WalmartRemoteInboundItem, "items.csv"),
    "inventory_log": (WalmartRemoteInventoryLog, "inventory_log.csv"),
}
ROW_LIMIT = 100_000
FILE_LIMIT = 50 * 1024 * 1024
BATCH_SIZE = 500


def _field(row: dict[str, str | None], name: str, limit: int) -> str | None:
    value = (row.get(name) or "").strip()
    if len(value) > limit:
        raise DispatchRejected("REMOTE_INGEST_ID_INVALID")
    return value or None


def prepare_verified_csv(
    *, archive_root: Path, store_code: str, store_id: str, run_id: str
) -> tuple[date, dict[str, str], dict[str, list[dict[str, object]]]]:
    """Pure file verification/parsing; raises before any SQL is attempted."""
    if not RUN_PATTERN.fullmatch(run_id) or not store_id.isdecimal():
        raise DispatchRejected("REMOTE_INGEST_ID_INVALID")
    raw_dir = archive_root / store_code / run_id
    verify_result(raw_dir, run_id=run_id)
    try:
        manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("store_id") != store_id:
            raise ValueError
        day = date.fromisoformat(manifest["date"])
        endpoints = manifest["endpoints_requested"]
        if (
            not isinstance(endpoints, list)
            or not endpoints
            or len(set(endpoints)) != len(endpoints)
        ):
            raise ValueError
        if not set(endpoints) <= ALLOWED_KEYS:
            raise ValueError
        destination = archive_root / "daily" / day.strftime("%Y%m%d") / "walmart" / store_id / run_id
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError
        manifest_file = destination / "_convert_manifest.json"
        if manifest_file.is_symlink():
            raise ValueError
        converted = json.loads(manifest_file.read_text(encoding="utf-8"))
        if converted.get("run_id") != run_id or converted.get("store_id") != store_id:
            raise ValueError
        written = converted["written"]
        if not isinstance(written, list) or len(written) != len(endpoints):
            raise ValueError
        files = {x["file"]: x for x in written}
        required = {MODELS[endpoint][1] for endpoint in endpoints}
        if set(files) != required:
            raise ValueError
        hashes: dict[str, str] = {}
        result: dict[str, list[dict[str, object]]] = {}
        for endpoint in endpoints:
            filename = MODELS[endpoint][1]
            metadata = files[filename]
            path = destination / filename
            if path.is_symlink() or not path.is_file() or path.stat().st_size > FILE_LIMIT:
                raise ValueError
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != metadata["sha256"]:
                raise ValueError
            hashes[endpoint] = digest
            records: list[dict[str, object]] = []
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if (
                    not reader.fieldnames
                    or len(reader.fieldnames) != len(set(reader.fieldnames))
                    or any(name is None for name in reader.fieldnames)
                ):
                    raise ValueError
                for index, row in enumerate(reader, start=1):
                    if index > ROW_LIMIT or None in row:
                        raise ValueError
                    item_id = _field(
                        row,
                        "itemInformation.itemID" if endpoint == "wfs_inventory" else "item_id",
                        128,
                    )
                    sku = _field(
                        row,
                        "itemInformation.sku" if endpoint == "wfs_inventory" else "sku",
                        255,
                    )
                    gtin = _field(
                        row,
                        "itemInformation.gtin" if endpoint == "wfs_inventory" else "gtin",
                        128,
                    )
                    shipment = _field(row, "shipmentId", 128)
                    event_id = _field(row, "id", 128)
                    records.append(
                        {
                            "row_number": index,
                            "item_id": item_id,
                            "sku": sku,
                            "gtin": gtin,
                            "shipment_id": shipment,
                            "event_id": event_id,
                            "payload": row,
                        }
                    )
            if len(records) != metadata["rows"]:
                raise ValueError
            result[endpoint] = records
        return day, hashes, result
    except DispatchRejected:
        raise
    except (KeyError, OSError, ValueError, TypeError, UnicodeError, csv.Error):
        raise DispatchRejected("REMOTE_INGEST_VERIFICATION_FAILED") from None


def ingest_verified_archive(
    session: Session,
    *,
    job_id: UUID,
    source_account_ref: str,
    store_code: str,
    store_id: str,
    run_id: str,
    archive_root: Path,
) -> dict[str, int]:
    """Write all four requested datasets and receipt atomically.

    Caller MUST commit this session before declaring ingestion successful or
    attempting remote cleanup; any error MUST roll the session back.
    """
    day, hashes, records = prepare_verified_csv(
        archive_root=archive_root, store_code=store_code, store_id=store_id, run_id=run_id
    )
    row_counts = {endpoint: len(rows) for endpoint, rows in records.items()}
    existing = session.scalar(
        select(WalmartRemoteIngestBatch).where(
            WalmartRemoteIngestBatch.store_id == store_id,
            WalmartRemoteIngestBatch.run_id == run_id,
        )
    )
    if existing is not None:
        if (
            existing.source_account_ref != source_account_ref
            or existing.store_code != store_code
            or existing.job_id != job_id
            or existing.file_hashes != hashes
            or existing.row_counts != row_counts
            or existing.snapshot_date != day
        ):
            raise DispatchRejected("REMOTE_INGEST_RECEIPT_CONFLICT")
        return row_counts
    for endpoint, rows in records.items():
        model = MODELS[endpoint][0]
        for start in range(0, len(rows), BATCH_SIZE):
            values = [
                {
                    "source_account_ref": source_account_ref,
                    "store_id": store_id,
                    "run_id": run_id,
                    "snapshot_date": day,
                    **row,
                }
                for row in rows[start : start + BATCH_SIZE]
            ]
            session.execute(insert(model), values)
    session.add(
        WalmartRemoteIngestBatch(
            job_id=job_id,
            source_account_ref=source_account_ref,
            store_code=store_code,
            store_id=store_id,
            run_id=run_id,
            snapshot_date=day,
            file_hashes=hashes,
            row_counts=row_counts,
        )
    )
    session.flush()
    return row_counts
