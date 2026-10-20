"""Multi-store WFS detection orchestrator. Read-only; no scheduling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.warehouse_wfs.read_only_detection import (
    run_wfs_read_only_detection,
)
from app.modules.warehouse_wfs.settlement_collector import PageFetcher
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore


@dataclass(frozen=True)
class WfsStoreRunSummary:
    store_id: str
    status: str
    pages: int = 0
    rows: int = 0
    anomalies: int = 0
    missing_standard: int = 0
    unresolved_listings: int = 0
    error_type: str | None = None


@dataclass(frozen=True)
class WfsBatchRunSummary:
    stores_total: int
    stores_succeeded: int
    stores_failed: int
    anomalies: int
    stores: tuple[WfsStoreRunSummary, ...]


def run_wfs_batch_read_only(
    *,
    session_factory: Callable[[], Session],
    fetch_page: PageFetcher,
    stores: tuple[WfsSettlementStore, ...],
    detection_date: date,
    max_stores: int = 20,
    max_pages_per_store: int = 500,
) -> WfsBatchRunSummary:
    """Process each store in an independent read-only transaction.

    Both the session and the API fetcher must be explicitly supplied.
    No implicit credential acquisition or live execution.
    """
    if (
        not 1 <= max_stores <= 200
        or not 1 <= max_pages_per_store <= 500
        or len(stores) > max_stores
    ):
        raise ValueError("WFS_BATCH_LIMIT_EXCEEDED")

    identities = [
        (s.source_account_ref, s.store_id)
        for s in stores
    ]
    if (
        len(set(identities)) != len(identities)
        or any(not account or not store for account, store in identities)
    ):
        raise ValueError("WFS_DUPLICATE_OR_INVALID_STORE")

    outcomes: list[WfsStoreRunSummary] = []

    for store in stores:
        pages_called = 0

        def limited_fetch(
            interface_id: str,
            params: dict[str, Any],
        ) -> Any:
            nonlocal pages_called
            if pages_called >= max_pages_per_store:
                raise ValueError("WFS_STORE_PAGE_LIMIT")
            pages_called += 1
            return fetch_page(interface_id, params)

        try:
            with session_factory() as session:
                try:
                    session.execute(text("SET TRANSACTION READ ONLY"))
                    result = run_wfs_read_only_detection(
                        session,
                        fetch_page=limited_fetch,
                        store=store,
                        detection_date=detection_date,
                    )
                finally:
                    session.rollback()

            detection = result.result.detection
            outcomes.append(
                WfsStoreRunSummary(
                    store_id=store.store_id,
                    status="completed",
                    pages=result.collected_pages,
                    rows=result.collected_rows,
                    anomalies=detection.anomalies,
                    missing_standard=detection.missing_standard,
                    unresolved_listings=result.unresolved_listings,
                )
            )
        except Exception as exc:
            outcomes.append(
                WfsStoreRunSummary(
                    store_id=store.store_id,
                    status="failed",
                    error_type=type(exc).__name__,
                )
            )

    return WfsBatchRunSummary(
        stores_total=len(stores),
        stores_succeeded=sum(x.status == "completed" for x in outcomes),
        stores_failed=sum(x.status == "failed" for x in outcomes),
        anomalies=sum(x.anomalies for x in outcomes),
        stores=tuple(outcomes),
    )
