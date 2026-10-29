"""Verified Walmart run JSONL -> original-compatible daily CSV archive.

Derived from the supplied 2026-10-26 walmart_to_daily/convert.py.
This is a file conversion stage, not an unapproved write into product tables.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from app.integrations.walmart.remote_dispatch import DispatchRejected, verify_result

COLUMNS = {
    "wfs_inventory": (
        "itemInformation.itemName, itemInformation.gtin, itemInformation.sku, itemInformation.itemID, "
        "itemInformation.offerID, itemInformation.brand, itemInformation.itemCondition, "
        "inventoryData.publishingStatus, inventoryData.itemLifecycle, inventoryData.stockStatus, "
        "inventoryData.availableUnits, inventoryData.reservedUnits, inventoryData.inboundUnits, "
        "inventoryData.unavailableUnits.inventoryReviewUnits, inventoryData.unavailableUnits.inventoryMovementUnits, "
        "inventoryData.onhandUnits, inventoryData.inventoryAge.0To90days, inventoryData.inventoryAge.91To180days, "
        "inventoryData.inventoryAge.181To270days, inventoryData.inventoryAge.271To365days, "
        "inventoryData.inventoryAge.365PlusDays, inventoryData.inventoryAge.365To450days, "
        "inventoryData.inventoryAge.450PlusDays, inventoryData.firstInStockDate, "
        "inventoryInsights.salesForecastWeek1to4, inventoryInsights.salesForecastWeek5to8, "
        "inventoryInsights.salesForecastWeek9to12, inventoryInsights.sellThroughRate, "
        "inventoryInsights.daysOfSupply, inventoryInsights.outOfStockDate, "
        "inventoryInsights.suggestedUnits, inventoryInsights.surplusUnits, inventoryInsights.customerFavorite"
    ),
    "inbound_shipments": (
        "inboundOrderId, shipmentId, shipToAddress.fcName, shipToAddress.addressLine1, "
        "shipToAddress.city, shipToAddress.stateCode, shipToAddress.countryCode, shipToAddress.postalCode, "
        "returnAddress.addressLine1, returnAddress.city, returnAddress.stateCode, returnAddress.countryCode, "
        "returnAddress.postalCode, status, createdDate, shipmentUnits, receivedUnits, expectedDeliveryDate, "
        "updatedExpectedDeliveryDate, actualDeliveryDate, returnAddress.addressLine2, trackingNo, carrierName"
    ),
    "inbound_shipment_items": (
        "inboundOrderId, shipmentId, gtin, sku, itemQty, vendorPackQty, innerPackQty, receivedQty, "
        "damagedQty, fillRate, expectedDeliveryDate, updatedExpectedDeliveryDate, shipNodeName, itemDesc"
    ),
    "inventory_log": (
        "id, gtin, fcId, fcName, changedUnits, transactionTime, transactionLocation, "
        "transactionReasonCode, transactionReasonDesc, transactionType, shipmentId, gtin_query, raw_json"
    ),
}
OUT_NAMES = {
    "wfs_inventory": "wfs_inventory",
    "inbound_shipments": "shipments",
    "inbound_shipment_items": "items",
    "inventory_log": "inventory_log",
}


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {prefix: obj}
    result: dict[str, Any] = {}
    for key, value in obj.items():
        subkey = prefix + "." + str(key) if prefix else str(key)
        result.update(flatten(value, subkey))
    return result


def _records(endpoint: str, params: dict[str, Any], body: dict[str, Any]) -> list[dict[str, Any]]:
    payload = body.get("payload")
    if endpoint == "wfs_inventory":
        rows = payload.get("inventory", []) if isinstance(payload, dict) else []
    elif endpoint == "inventory_log":
        rows = payload.get("inventoryLog", []) if isinstance(payload, dict) else []
    else:
        rows = payload if isinstance(payload, list) else []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise DispatchRejected("REMOTE_CONVERSION_RESPONSE_INVALID")
    converted: list[dict[str, Any]] = []
    for record in rows:
        flattened = flatten(record)
        if endpoint == "inbound_shipment_items" and not flattened.get("shipmentId"):
            flattened["shipmentId"] = params.get("shipmentId", "")
        if endpoint == "inventory_log":
            flattened["gtin_query"] = params.get("gtin", "")
            flattened["raw_json"] = record
        converted.append(flattened)
    return converted


def convert_verified_run(
    *,
    run_dir: Path,
    output_root: Path,
    run_id: str,
    store_id: str,
) -> dict[str, Any]:
    """Write no-overwrite CSVs after validation; never modify source run."""
    verify_result(run_dir, run_id=run_id)
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("store_id") != store_id:
            raise ValueError
        day = date.fromisoformat(manifest["date"]).strftime("%Y%m%d")
        if not store_id.isdecimal():
            raise ValueError
        destination = output_root / day / "walmart" / store_id
        if destination.exists() or destination.is_symlink():
            raise DispatchRejected("REMOTE_CONVERSION_ALREADY_EXISTS")
        output_root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".walmart-convert-", dir=output_root))
        written: list[dict[str, Any]] = []
        try:
            for endpoint in manifest["endpoints_requested"]:
                raw = run_dir / "raw" / (endpoint + ".jsonl")
                if not raw.is_file() or raw.is_symlink():
                    raise ValueError
                rows: list[dict[str, Any]] = []
                for line in raw.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    page = json.loads(line)
                    if not isinstance(page, dict):
                        raise ValueError
                    rows.extend(
                        _records(endpoint, page.get("params") or {}, page.get("body") or {})
                    )
                status = manifest["endpoints"][endpoint]
                if status.get("rows") is not None and int(status["rows"]) != len(rows):
                    raise ValueError
                if (
                    endpoint == "wfs_inventory"
                    and status.get("total_count") is not None
                    and int(status["total_count"]) != len(rows)
                ):
                    raise ValueError
                fields = [name.strip() for name in COLUMNS[endpoint].split(",")]
                known = set(fields)
                for row in rows:
                    for key in row:
                        if key not in known:
                            fields.append(key)
                            known.add(key)
                filename = OUT_NAMES[endpoint] + ".csv"
                target = stage / filename
                with target.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(
                            {
                                key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                                if isinstance(value, (dict, list))
                                else value
                                for key, value in row.items()
                            }
                        )
                written.append(
                    {
                        "file": filename,
                        "rows": len(rows),
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    }
                )
            (stage / "_convert_manifest.json").write_text(
                json.dumps(
                    {"run_id": run_id, "store_id": store_id, "date": day, "written": written},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise DispatchRejected("REMOTE_CONVERSION_ALREADY_EXISTS")
            os.rename(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return {"status": "converted", "store_id": store_id, "files": len(written)}
    except DispatchRejected:
        raise
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise DispatchRejected("REMOTE_CONVERSION_FAILED") from None
