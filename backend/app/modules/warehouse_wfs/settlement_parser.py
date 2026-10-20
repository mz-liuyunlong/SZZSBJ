"""Parse Lingxing Walmart settlement rows without network or database access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.modules.warehouse_wfs.fee_detection import (
    SettlementFeeRow,
    decimal_value,
)


class SettlementParseError(ValueError):
    """Safe error code without raw order or account details."""


@dataclass(frozen=True)
class SettlementParseResult:
    rows: tuple[SettlementFeeRow, ...]
    rejected_rows: int
    missing_store: int
    missing_identity: int
    duplicate_lines: int


def _string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, float):
        raise SettlementParseError("WFS_UNSAFE_FLOAT_IDENTIFIER")
    return str(value).strip()


def _settlement_date(value: object) -> str:
    raw = _string(value)[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise SettlementParseError("WFS_INVALID_SETTLEMENT_DATE") from exc


def parse_settlement_rows(
    raw_rows: list[dict[str, Any]],
    *,
    source_account_ref: str,
    store_ids_by_name: dict[str, str],
    window_start: date,
    window_end: date,
) -> SettlementParseResult:
    """Normalize provider rows with strict account/store and date boundaries.

    Store IDs from provider JSON are not trusted as numbers. A verified
    store-name mapping is required; unknown stores are rejected, not guessed.
    """

    if not source_account_ref or window_start > window_end:
        raise SettlementParseError("WFS_INVALID_SCOPE")

    rows: list[SettlementFeeRow] = []
    seen: set[str] = set()
    rejected = 0
    missing_store = 0
    missing_identity = 0
    duplicate_lines = 0

    for item in raw_rows:
        if not isinstance(item, dict):
            rejected += 1
            continue

        try:
            msku = _string(item.get("msku"))
            store_name = _string(item.get("storeName"))
            store_id = store_ids_by_name.get(store_name, "")

            if not store_id:
                missing_store += 1
                rejected += 1
                continue

            if not msku or msku.upper().startswith("CS"):
                missing_identity += 1
                rejected += 1
                continue

            settled = _settlement_date(item.get("settlementDate"))
            if not window_start.isoformat() <= settled <= window_end.isoformat():
                rejected += 1
                continue

            unique_id = _string(item.get("uniqueId"))
            row_index = _string(item.get("rowIndex"))
            if not unique_id or not row_index:
                missing_identity += 1
                rejected += 1
                continue

            line_ref = f"{unique_id}:{row_index}"
            if line_ref in seen:
                duplicate_lines += 1
                continue
            seen.add(line_ref)

            sales = decimal_value(item.get("salesNum"))
            logistics = decimal_value(item.get("platformLogisticsAmount"))

            rows.append(
                SettlementFeeRow(
                    source_account_ref=source_account_ref,
                    store_id=store_id,
                    msku=msku,
                    platform_order_no=_string(item.get("platformOrderNo")),
                    sales_num=sales,
                    platform_logistics_amount=logistics,
                    settlement_date=settled,
                    source_line_ref=line_ref,
                )
            )
        except (ValueError, TypeError):
            rejected += 1

    return SettlementParseResult(
        rows=tuple(rows),
        rejected_rows=rejected,
        missing_store=missing_store,
        missing_identity=missing_identity,
        duplicate_lines=duplicate_lines,
    )
