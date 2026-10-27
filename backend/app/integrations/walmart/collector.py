"""Bounded read-only collector ported from the colleague's tested worker semantics.

The collector never reads credentials or performs network I/O itself. It calls
an injected, scope-bound WalmartClient and returns only bounded, sanitized
artifacts. All 4 original capabilities remain read-only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.integrations.walmart.client import WalmartClient

READ_ENDPOINTS = (
    "wfs_inventory",
    "inbound_shipments",
    "inbound_shipment_items",
    "inventory_log",
)
GTIN_PATTERN = re.compile(r"^(?:\d{8}|\d{12,14})$")
SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(
        r"(access_token|client_secret|client_id|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"WM_SEC\.ACCESS_TOKEN\s*[:=]\s*\S+", re.IGNORECASE),
)


class CollectorError(RuntimeError):
    """Stable failure code without remote payload or credential content."""


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    page_size: int = 100
    max_pages: int = 100
    max_records: int = 100_000
    retry_count: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 100:
            raise ValueError("WALMART_PAGE_SIZE_INVALID")
        if not 1 <= self.max_pages <= 500:
            raise ValueError("WALMART_MAX_PAGES_INVALID")
        if not 1 <= self.max_records <= 500_000:
            raise ValueError("WALMART_MAX_RECORDS_INVALID")
        if self.retry_count not in (0, 1):
            raise ValueError("WALMART_RETRY_COUNT_INVALID")


def _records(payload: Any) -> list[dict[str, Any]]:
    """Recognize the response envelopes seen in the source worker fixtures."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in (
            "payload",
            "inboundShipments",
            "shipmentItems",
            "inventory",
            "inventoryData",
            "items",
            "list",
            "data",
        ):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
            if isinstance(candidate, dict):
                for nested_key in (
                    "inventory",
                    "inventoryLog",
                    "records",
                    "list",
                    "items",
                    "inboundShipments",
                    "shipmentItems",
                ):
                    nested = candidate.get(nested_key)
                    if isinstance(nested, list):
                        rows = nested
                        break
                if rows is not None:
                    break
        if rows is None:
            rows = []
    else:
        raise CollectorError("WALMART_RESPONSE_SHAPE_INVALID")
    if any(not isinstance(row, dict) for row in rows):
        raise CollectorError("WALMART_RESPONSE_SHAPE_INVALID")
    return rows


def _total_count(payload: Any) -> int | None:
    headers = payload.get("headers") if isinstance(payload, dict) else None
    value = headers.get("totalCount") if isinstance(headers, dict) else None
    if value is None:
        return None
    if isinstance(value, bool):
        raise CollectorError("WALMART_TOTAL_COUNT_INVALID")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise CollectorError("WALMART_TOTAL_COUNT_INVALID") from None
    if result < 0:
        raise CollectorError("WALMART_TOTAL_COUNT_INVALID")
    return result


def _gtin_from_record(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    item_id = row.get("item_id") or row.get("itemId") or row.get("sku")
    gtin = row.get("gtin") or row.get("GTIN")
    info = row.get("itemInformation")
    if isinstance(info, dict):
        item_id = item_id or info.get("sku") or info.get("itemId")
        gtin = gtin or info.get("gtin") or info.get("GTIN")
    item_id_value = str(item_id).strip() if item_id is not None else None
    gtin_value = str(gtin).strip() if gtin is not None else None
    return item_id_value, gtin_value


def _sanitize_text(value: str) -> tuple[str, int]:
    hits = 0
    for pattern in SECRET_PATTERNS:
        value, count = pattern.subn("[REDACTED]", value)
        hits += count
    return value, hits


def _sanitize(value: Any, *, depth: int = 0) -> tuple[Any, int]:
    if depth > 20:
        raise CollectorError("WALMART_RESPONSE_DEPTH_EXCEEDED")
    hits = 0
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        if len(value) > 100_000:
            raise CollectorError("WALMART_RESPONSE_TOO_LARGE")
        output = []
        for item in value:
            safe, count = _sanitize(item, depth=depth + 1)
            output.append(safe)
            hits += count
        return output, hits
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            normalized = "".join(ch for ch in str(key).lower() if ch.isalnum())
            if normalized in {
                "accesstoken",
                "refreshtoken",
                "clientsecret",
                "clientid",
                "authorization",
                "secretkey",
                "password",
            }:
                output[str(key)] = "[REDACTED]"
                hits += 1
                continue
            safe, count = _sanitize(item, depth=depth + 1)
            output[str(key)] = safe
            hits += count
        return output, hits
    return value, 0


class WalmartReadCollector:
    """Execute the four source-verified GET capabilities with strict boundaries."""

    def __init__(
        self,
        client: WalmartClient,
        *,
        store_code: str,
        config: CollectorConfig | None = None,
    ) -> None:
        self._client = client
        self._store = store_code
        self._config = config if config is not None else CollectorConfig()
        self._calls = 0
        self._redactions = 0
        self._request_log: list[dict[str, Any]] = []

    def collect(
        self,
        *,
        endpoints: Sequence[str],
        from_date: date,
        to_date: date,
        gtin_items: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if to_date < from_date:
            raise CollectorError("WALMART_DATE_RANGE_INVALID")
        if not endpoints or len(set(endpoints)) != len(endpoints):
            raise CollectorError("WALMART_ENDPOINT_SELECTION_INVALID")
        if any(key not in READ_ENDPOINTS for key in endpoints):
            raise CollectorError("WALMART_NON_READ_CAPABILITY_REJECTED")
        if "inventory_log" in endpoints and gtin_items is None and "wfs_inventory" not in endpoints:
            gtin_items = None
        endpoint_results: dict[str, dict[str, Any]] = {}
        collected: dict[str, list[dict[str, Any]]] = {}
        auth_failed = False
        for endpoint in endpoints:
            if auth_failed:
                endpoint_results[endpoint] = {
                    "status": "SKIPPED_AUTH_FAILED",
                    "rows": 0,
                    "pages": 0,
                }
                continue
            try:
                if endpoint == "wfs_inventory":
                    rows, pages = self._collect_offset(endpoint, {}, ("payload", "inventory"))
                elif endpoint == "inbound_shipments":
                    rows, pages = self._collect_offset(
                        endpoint,
                        {
                            "fromCreatedDate": int(
                                datetime.combine(from_date, time.min, tzinfo=UTC).timestamp() * 1000
                            ),
                            "toCreatedDate": int(
                                datetime.combine(
                                    to_date + timedelta(days=1), time.min, tzinfo=UTC
                                ).timestamp()
                                * 1000
                            )
                            - 1,
                        },
                    )
                elif endpoint == "inbound_shipment_items":
                    shipments = collected.get("inbound_shipments")
                    if shipments is None:
                        raise CollectorError("WALMART_DEPENDENCY_MISSING")
                    rows, pages = self._collect_by_shipment(shipments)
                else:
                    source = (
                        list(gtin_items)
                        if gtin_items is not None
                        else self._gtin_items_from_wfs(collected.get("wfs_inventory"))
                    )
                    rows, pages, resolution = self._collect_inventory_log(
                        source, from_date=from_date, to_date=to_date
                    )
                    endpoint_results["inventory_log"] = {
                        "status": resolution["status"],
                        "rows": len(rows),
                        "pages": pages,
                        "gtin_resolution": resolution,
                    }
                    collected[endpoint] = rows
                    continue
                collected[endpoint] = rows
                endpoint_results[endpoint] = {
                    "status": "SUCCESS",
                    "rows": len(rows),
                    "pages": pages,
                }
            except CollectorError as exc:
                code = str(exc)
                if code == "WALMART_AUTH_FAILED":
                    auth_failed = True
                    state = "AUTH_FAILED"
                else:
                    state = "FAILED"
                endpoint_results[endpoint] = {
                    "status": state,
                    "error_code": code,
                    "rows": 0,
                    "pages": 0,
                }
        overall = (
            "AUTH_FAILED"
            if auth_failed
            else "SUCCESS"
            if all(item["status"] == "SUCCESS" for item in endpoint_results.values())
            else "PARTIAL"
        )
        raw_files = {
            "raw/" + key + ".jsonl": self._jsonl(collected.get(key, []))
            for key in endpoints
            if key in collected
        }
        item_statuses = getattr(self, "_gtin_item_statuses", None)
        if "inventory_log" in endpoints and item_statuses is not None:
            raw_files["raw/inventory_log_items.jsonl"] = self._jsonl(item_statuses)
            if "inventory_log" in endpoint_results:
                endpoint_results["inventory_log"]["item_gtin_mapping"] = (
                    "raw/inventory_log_items.jsonl"
                )
        files: dict[str, dict[str, Any]] = {}
        for name, content in raw_files.items():
            files[name] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "records": len(collected[name[4:-6]]),
            }
        safe_endpoints, count = _sanitize(endpoint_results)
        self._redactions += count
        manifest = {
            "manifest_version": 1,
            "store_code": self._store,
            "status": overall,
            "endpoints_requested": list(endpoints),
            "endpoints": safe_endpoints,
            "http_calls": self._calls,
            "redactions": self._redactions,
            "credential_files_read": 0,
            "files": files,
        }
        manifest_bytes = self._json_bytes(manifest)
        summary = {
            "store_code": self._store,
            "status": overall,
            "endpoints": {key: value["status"] for key, value in safe_endpoints.items()},
            "rows": {key: value["rows"] for key, value in safe_endpoints.items()},
            "http_calls": self._calls,
        }
        artifacts = {
            **raw_files,
            "summary.json": self._json_bytes(summary),
            "manifest.json": manifest_bytes,
            "requests_log.md": self._json_bytes(self._request_log).decode("utf-8"),
        }
        sums = [
            f"{hashlib.sha256(value.encode('utf-8')).hexdigest()}  {name}"
            for name, value in sorted(artifacts.items())
        ]
        artifacts["SHA256SUMS"] = "\n".join(sums) + "\n"
        return {
            "manifest": manifest,
            "summary": summary,
            "artifacts": artifacts,
            "records": collected,
        }

    def _gtin_items_from_wfs(
        self, rows: Sequence[Mapping[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if rows is None:
            return []
        return [
            {"item_id": item_id, "gtin": gtin} for item_id, gtin in map(_gtin_from_record, rows)
        ]

    def _collect_offset(
        self,
        endpoint: str,
        base_params: Mapping[str, Any],
        expected_nested_path: tuple[str, ...] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        offset = 0
        total: int | None = None
        for page in range(self._config.max_pages):
            params = dict(base_params)
            params.update({"limit": self._config.page_size, "offset": offset})
            payload = self._request(endpoint, params)
            page_rows = self._extract_endpoint_rows(endpoint, payload, expected_nested_path)
            page_total = _total_count(payload)
            if page_total is not None:
                total = page_total
            if len(rows) + len(page_rows) > self._config.max_records:
                raise CollectorError("WALMART_MAX_RECORDS_EXCEEDED")
            rows.extend(page_rows)
            offset += len(page_rows)
            if total is not None:
                if len(rows) > total:
                    raise CollectorError("WALMART_TOTAL_COUNT_MISMATCH")
                if len(rows) == total:
                    return rows, page + 1
                if not page_rows:
                    raise CollectorError("WALMART_INCOMPLETE_PAGING")
            elif len(page_rows) < self._config.page_size:
                return rows, page + 1
        raise CollectorError("WALMART_MAX_PAGES_REACHED")

    def _extract_endpoint_rows(
        self,
        endpoint: str,
        payload: Any,
        expected_nested_path: tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        if endpoint == "wfs_inventory" and isinstance(payload, dict):
            nested = payload.get("payload")
            if isinstance(nested, dict) and isinstance(nested.get("inventory"), list):
                rows = nested["inventory"]
                if any(not isinstance(row, dict) for row in rows):
                    raise CollectorError("WALMART_RESPONSE_SHAPE_INVALID")
                return rows
        return _records(payload)

    def _collect_by_shipment(
        self, shipments: Sequence[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        output: list[dict[str, Any]] = []
        pages = 0
        ids = []
        for shipment in shipments:
            shipment_id = shipment.get("shipmentId") or shipment.get("shipment_id")
            if shipment_id is None:
                continue
            ids.append(str(shipment_id))
        if not ids:
            raise CollectorError("WALMART_DEPENDENCY_MISSING")
        for shipment_id in ids:
            rows, used = self._collect_offset("inbound_shipment_items", {"shipmentId": shipment_id})
            output.extend(rows)
            pages += used
            if len(output) > self._config.max_records:
                raise CollectorError("WALMART_MAX_RECORDS_EXCEEDED")
        return output, pages

    def _collect_inventory_log(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        from_date: date,
        to_date: date,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        unique: dict[str, str | None] = {}
        statuses: list[dict[str, Any]] = []
        counts = {
            "total_items": 0,
            "with_gtin": 0,
            "without_gtin": 0,
            "invalid_gtin": 0,
            "duplicate_gtin": 0,
            "unique_gtins": 0,
            "queried_gtins": 0,
            "inventory_log_success": 0,
            "inventory_log_failed": 0,
            "skipped_no_gtin": 0,
            "skipped_invalid_gtin": 0,
        }
        for item in items:
            item_id, gtin = _gtin_from_record(item)
            counts["total_items"] += 1
            if not gtin:
                counts["without_gtin"] += 1
                counts["skipped_no_gtin"] += 1
                statuses.append({"item_id": item_id, "gtin": None, "status": "SKIPPED_NO_GTIN"})
                continue
            if not GTIN_PATTERN.fullmatch(gtin):
                counts["invalid_gtin"] += 1
                counts["skipped_invalid_gtin"] += 1
                statuses.append({"item_id": item_id, "gtin": gtin, "status": "INVALID_GTIN"})
                continue
            counts["with_gtin"] += 1
            if gtin in unique:
                counts["duplicate_gtin"] += 1
                statuses.append(
                    {
                        "item_id": item_id,
                        "gtin": gtin,
                        "status": "DUPLICATE_GTIN",
                        "query_item_id": unique[gtin],
                    }
                )
            else:
                unique[gtin] = item_id
        counts["unique_gtins"] = len(unique)
        counts["queried_gtins"] = len(unique)
        all_rows: list[dict[str, Any]] = []
        pages = 0
        for gtin, item_id in unique.items():
            try:
                rows, used = self._collect_offset(
                    "inventory_log",
                    {
                        "gtin": gtin,
                        "fromDate": from_date.isoformat() + "T00:00:00Z",
                        "toDate": to_date.isoformat() + "T23:59:59Z",
                    },
                )
                all_rows.extend(rows)
                pages += used
                counts["inventory_log_success"] += 1
                statuses.append(
                    {
                        "item_id": item_id,
                        "gtin": gtin,
                        "status": "SUCCESS",
                        "query_item_id": item_id,
                    }
                )
            except CollectorError as exc:
                if str(exc) == "WALMART_AUTH_FAILED":
                    raise
                counts["inventory_log_failed"] += 1
                statuses.append(
                    {
                        "item_id": item_id,
                        "gtin": gtin,
                        "status": "FAILED",
                        "query_item_id": item_id,
                        "error_code": str(exc),
                    }
                )
        if counts["with_gtin"] == 0 and counts["invalid_gtin"] > 0 and counts["without_gtin"] == 0:
            status = "INVALID_GTIN_INPUT"
        elif counts["queried_gtins"] == 0:
            status = "MISSING_GTIN_DEPENDENCY"
        elif counts["inventory_log_failed"] > 0:
            status = "PARTIAL"
        else:
            status = "SUCCESS"
        # Do not expose item-level mappings in the manifest/summary.
        self._gtin_item_statuses = statuses
        return (
            all_rows,
            pages,
            {"source": "explicit_or_current_run", "status": status, "stats": counts},
        )

    def _request(self, endpoint: str, params: Mapping[str, Any]) -> Any:
        attempts = 0
        while True:
            attempts += 1
            self._calls += 1
            safe_params, redactions = _sanitize(dict(params))
            self._redactions += redactions
            try:
                result = self._client.call(
                    self._store,
                    endpoint,
                    params=params,
                    allow_writes=False,
                )
            except Exception as exc:
                code = str(exc)
                self._request_log.append(
                    {
                        "method": "GET",
                        "endpoint": endpoint,
                        "params": safe_params,
                        "attempt": attempts,
                        "error_code": code,
                    }
                )
                if code == "WALMART_AUTH_FAILED":
                    raise CollectorError("WALMART_AUTH_FAILED") from None
                if attempts <= self._config.retry_count:
                    continue
                raise CollectorError("WALMART_REQUEST_FAILED") from None
            if result.status_code in (401, 403):
                raise CollectorError("WALMART_AUTH_FAILED")
            if not 200 <= result.status_code < 300:
                self._request_log.append(
                    {
                        "method": "GET",
                        "endpoint": endpoint,
                        "params": safe_params,
                        "attempt": attempts,
                        "status_code": result.status_code,
                    }
                )
                if attempts <= self._config.retry_count:
                    continue
                raise CollectorError("WALMART_REQUEST_FAILED")
            self._request_log.append(
                {
                    "method": "GET",
                    "endpoint": endpoint,
                    "params": safe_params,
                    "attempt": attempts,
                    "status_code": result.status_code,
                }
            )
            safe_payload, redactions = _sanitize(result.data)
            self._redactions += redactions
            return safe_payload

    @staticmethod
    def _json_bytes(value: Any) -> str:
        safe, _ = _sanitize(value)
        return json.dumps(safe, ensure_ascii=False, sort_keys=True, indent=2)

    @staticmethod
    def _jsonl(rows: Sequence[Mapping[str, Any]]) -> str:
        lines = []
        for row in rows:
            safe, _ = _sanitize(row)
            lines.append(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return "\n".join(lines) + ("\n" if lines else "")
