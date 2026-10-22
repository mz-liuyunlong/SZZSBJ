"""Database-free file collection, with bounded pagination and replayable evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.integrations.lingxing.security import redact_json
from app.modules.pmc_domestic.inbound_builder import (
    InboundDataError,
    build_inbound_rows,
    quantity,
    source_id,
    unique_records,
)

BATCH_PATH = "/erp/sc/routing/data/local_inventory/getBatchDetailList"
STATEMENT_PATH = "/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement"
FetchPage = Callable[[str, dict[str, Any]], Any]


@dataclass
class InboundCapture:
    account: str
    warehouse: str
    start: date
    end: date
    statements: list[dict[str, Any]]
    batches: list[dict[str, Any]]
    observed_at: datetime


def collect_inbound(
    fetch: FetchPage,
    *,
    account: str,
    warehouse: str,
    start: date,
    end: date,
    max_pages: int = 1000,
    record_page: Callable | None = None,
) -> InboundCapture:
    if not account.strip() or len(account) > 128 or not warehouse.strip() or len(warehouse) > 64:
        raise InboundDataError("INBOUND_SCOPE_INVALID")
    if start >= end or (end - start).days > 3660 or not 1 <= max_pages <= 10000:
        raise InboundDataError("INBOUND_WINDOW_INVALID")
    page_budget = 0
    observed = []

    def pages(path: str, params: dict[str, Any], length: int) -> list[dict[str, Any]]:
        nonlocal page_budget
        result = []
        expected = None
        offset = 0
        while True:
            page_budget += 1
            if page_budget > max_pages:
                raise InboundDataError("INBOUND_PAGE_LIMIT")
            body = {**params, "offset": offset, "length": length}
            envelope = fetch(path, body)
            payload = envelope.response_json
            if record_page:
                record_page(path, body, envelope)
            if (
                not envelope.is_success
                or not isinstance(payload, dict)
                or (isinstance(payload.get("code"), bool) or str(payload.get("code")) != "0")
            ):
                raise InboundDataError("INBOUND_SOURCE_FAILED")
            data = payload.get("data")
            total = quantity(payload.get("total"))
            if not isinstance(data, list) or total is None or total < 0:
                raise InboundDataError("INBOUND_RESPONSE_INVALID")
            if expected is not None and expected != total:
                raise InboundDataError("INBOUND_TOTAL_CHANGED")
            expected = total
            if len(data) > length or offset + len(data) > total or (not data and offset < total):
                raise InboundDataError("INBOUND_INCOMPLETE_PAGE")
            for row in data:
                if not isinstance(row, dict) or source_id(row.get("wid")) != warehouse:
                    raise InboundDataError("INBOUND_WAREHOUSE_MISMATCH")
                result.append(row)
            observed.append(envelope.pulled_at)
            offset += len(data)
            if offset == total:
                kind = "batch" if path == BATCH_PATH else "statement"
                if len(unique_records(result, kind)) != len(result):
                    raise InboundDataError("INBOUND_DUPLICATE_PAGE")
                return result
            if len(data) < length:
                raise InboundDataError("INBOUND_INCOMPLETE_PAGE")

    batches = pages(BATCH_PATH, {"wids": warehouse, "show_zero_stock": 1}, 400)
    statements = []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=30), end)
        statements.extend(
            pages(
                STATEMENT_PATH,
                {
                    "wids": warehouse,
                    "start_date": str(cursor),
                    "end_date": str(stop),
                },
                200,
            )
        )
        cursor = stop
    statements = unique_records(statements, "statement")
    return InboundCapture(account, warehouse, start, end, statements, batches, min(observed))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ["record_status"]

    def encode(value: Any) -> str:
        if value is None:
            return "\\N"
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if isinstance(value, str) and value.startswith("\\"):
            return "\\" + value
        return str(value)

    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: encode(row.get(k)) for k in fields} for row in rows)


def export_inbound_csv(
    fetch: FetchPage, *, output: Path, source_timezone: str | None = None, **scope
) -> dict[str, Any]:
    # Exclusive directory creation prevents an unsuccessful retry overwriting evidence.
    output.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "format_version": 1,
        "complete": False,
        "source": "lingxing_openapi",
        "account": scope["account"],
        "warehouse": scope["warehouse"],
        "start_inclusive": str(scope["start"]),
        "end_exclusive": str(scope["end"]),
        "source_timezone": source_timezone,
        "csv_null": "\\N",
        "csv_escape": "leading backslash doubled",
        "files": {},
    }

    def page(path, body, envelope):
        safe = {
            "api_path": path,
            "body": body,
            "pulled_at": envelope.pulled_at.isoformat(),
            "is_success": envelope.is_success,
            "response": redact_json(envelope.response_json),
        }
        with (output / "source_pages.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe, ensure_ascii=False) + "\n")
        with (output / "requests_log.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({k: v for k, v in safe.items() if k != "response"}) + "\n")

    try:
        capture = collect_inbound(fetch, record_page=page, **scope)
        board = build_inbound_rows(
            capture.statements,
            capture.batches,
            account=capture.account,
            warehouse=capture.warehouse,
            source_timezone=source_timezone,
        )
        datasets = {
            "warehouse_statements.csv": capture.statements,
            "batch_details.csv": capture.batches,
            "inbound_board_preview.csv": board,
        }
        for filename, rows in datasets.items():
            path = output / filename
            write_csv(path, rows)
            manifest["files"][filename] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        manifest.update(
            complete=True,
            source_observed_at=capture.observed_at.isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
        )
    except Exception as error:
        manifest["error_code"] = (
            str(error) if isinstance(error, InboundDataError) else "INBOUND_EXPORT_FAILED"
        )
        raise InboundDataError(manifest["error_code"]) from None
    finally:
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return manifest
