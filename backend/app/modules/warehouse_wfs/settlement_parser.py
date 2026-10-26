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
    business_excluded_rows: int
    invalid_rows: int
    missing_store_rows: int
    missing_identity_rows: int
    duplicate_rows: int

    @property
    def accepted_rows(self) -> int:
        return len(self.rows)

    @property
    def rejected_rows(self) -> int:
        """Compatibility total for malformed rows; business exclusions are separate."""

        return self.invalid_rows + self.missing_store_rows + self.missing_identity_rows

    @property
    def missing_store(self) -> int:
        return self.missing_store_rows

    @property
    def missing_identity(self) -> int:
        return self.missing_identity_rows

    @property
    def duplicate_lines(self) -> int:
        return self.duplicate_rows


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
    expected_store_id: str,
    window_start: date,
    window_end: date,
    wfs_scope_verified: bool = False,
) -> SettlementParseResult:
    """Normalize provider rows with strict account/store and date boundaries.

    The request-scoped store ID and response `storeId` must match exactly.
    `storeName` is descriptive and is never used as an authorization identity.
    """

    if not source_account_ref or not expected_store_id or window_start > window_end:
        raise SettlementParseError("WFS_INVALID_SCOPE")

    rows: list[SettlementFeeRow] = []
    seen: set[str] = set()
    business_excluded = 0
    invalid = 0
    missing_store = 0
    missing_identity = 0
    duplicate_lines = 0

    for item in raw_rows:
        if not isinstance(item, dict):
            invalid += 1
            continue

        try:
            msku = _string(item.get("msku"))
            store_id = _string(item.get("storeId"))
            if not store_id or store_id != expected_store_id:
                missing_store += 1
                continue

            if msku.upper().startswith("CS"):
                business_excluded += 1
                continue
            if not msku:
                missing_identity += 1
                continue

            platform_order_no = _string(item.get("platformOrderNo"))
            if not platform_order_no:
                missing_identity += 1
                continue

            currency_code = _string(item.get("currencyCode"))
            if currency_code.upper() != "USD":
                invalid += 1
                continue

            if _string(item.get("platformCode")) != "10008":
                invalid += 1
                continue

            transaction_type = _string(item.get("transactionTypes"))
            if transaction_type != "0":
                # Refunds, adjustments and unknown transaction types are not
                # silently mixed into the order-frequency WFS fee mode.
                invalid += 1
                continue

            settled = _settlement_date(item.get("settlementDate"))
            if not window_start.isoformat() <= settled <= window_end.isoformat():
                invalid += 1
                continue

            unique_id = _string(item.get("uniqueId"))
            row_index = _string(item.get("rowIndex"))
            if not unique_id or not row_index:
                missing_identity += 1
                continue

            line_ref = f"{store_id}:{unique_id}:{row_index}"
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
                    platform_order_no=platform_order_no,
                    sales_num=sales,
                    platform_logistics_amount=logistics,
                    settlement_date=settled,
                    source_line_ref=line_ref,
                    fee_scope_status="verified_wfs" if wfs_scope_verified else "unverified",
                )
            )
        except (ValueError, TypeError):
            invalid += 1

    return SettlementParseResult(
        rows=tuple(rows),
        business_excluded_rows=business_excluded,
        invalid_rows=invalid,
        missing_store_rows=missing_store,
        missing_identity_rows=missing_identity,
        duplicate_rows=duplicate_lines,
    )
