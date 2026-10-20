"""Read-only WFS detection orchestration.

Reuses the existing settlement parser, modal fee resolver and anomaly detector.
Transport, product-management fee lookup and case persistence stay separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.modules.warehouse_wfs.anomaly_detection import (
    WfsDetectionSummary,
    WfsStandardFee,
    detect_wfs_anomalies,
)
from app.modules.warehouse_wfs.fee_detection import resolve_wfs_fees
from app.modules.warehouse_wfs.settlement_parser import parse_settlement_rows
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore


class WfsDetectionError(ValueError):
    """Fail-closed detection error without exposing source records."""


@dataclass(frozen=True, slots=True)
class WfsDetectionWindow:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class WfsDetectionResult:
    window: WfsDetectionWindow
    settlement_rows: int
    detection: WfsDetectionSummary


def legacy_detection_window(
    detection_date: date,
    *,
    lag_days: int = 2,
    window_days: int = 60,
) -> WfsDetectionWindow:
    """Match the legacy T-2, rolling 60-calendar-day settlement window."""
    if lag_days < 0 or window_days < 1:
        raise WfsDetectionError("WFS_INVALID_WINDOW")

    end = detection_date - timedelta(days=lag_days)
    start = end - timedelta(days=window_days - 1)
    return WfsDetectionWindow(start=start, end=end)


def evaluate_wfs_settlements(
    *,
    source_account_ref: str,
    stores: tuple[WfsSettlementStore, ...],
    raw_rows: list[dict[str, Any]],
    standards: list[WfsStandardFee],
    window: WfsDetectionWindow,
) -> WfsDetectionResult:
    """Evaluate one complete settlement batch without writing data.

    The caller must guarantee complete pagination and correct API filters.
    Any rejected input row blocks detection to prevent partial fee estimates.
    """
    if not source_account_ref or not stores:
        raise WfsDetectionError("WFS_INVALID_SCOPE")

    store_ids_by_name: dict[str, str] = {}
    seen_store_ids: set[str] = set()

    for store in stores:
        if (
            store.source_account_ref != source_account_ref
            or not store.store_id
            or not store.store_name
            or store.store_id in seen_store_ids
            or store.store_name in store_ids_by_name
        ):
            raise WfsDetectionError("WFS_AMBIGUOUS_STORE_SCOPE")

        seen_store_ids.add(store.store_id)
        store_ids_by_name[store.store_name] = store.store_id

    if window.start > window.end:
        raise WfsDetectionError("WFS_INVALID_WINDOW")

    parsed = parse_settlement_rows(
        raw_rows,
        source_account_ref=source_account_ref,
        store_ids_by_name=store_ids_by_name,
        window_start=window.start,
        window_end=window.end,
    )

    if parsed.rejected_rows or parsed.duplicate_lines:
        raise WfsDetectionError("WFS_INCOMPLETE_OR_INVALID_SETTLEMENT")

    for standard in standards:
        if (
            standard.source_account_ref != source_account_ref
            or standard.store_id not in seen_store_ids
        ):
            raise WfsDetectionError("WFS_STANDARD_SCOPE_MISMATCH")

    actual_fees = resolve_wfs_fees(list(parsed.rows))
    detection = detect_wfs_anomalies(actual_fees, standards)

    return WfsDetectionResult(
        window=window,
        settlement_rows=len(parsed.rows),
        detection=detection,
    )
