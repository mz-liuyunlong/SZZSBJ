"""Account/store scoped WFS detection. No database writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import WalmartListingDimension
from app.modules.warehouse_wfs.detection_pipeline import (
    WfsDetectionResult,
    evaluate_wfs_settlements,
    legacy_detection_window,
)
from app.modules.warehouse_wfs.settlement_collector import (
    PageFetcher,
    collect_wfs_settlements,
)
from app.modules.warehouse_wfs.standard_fee_reader import (
    read_product_management_wfs_fee,
)
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore


@dataclass(frozen=True)
class WfsReadOnlyRun:
    result: WfsDetectionResult
    collected_pages: int
    collected_rows: int
    unresolved_listings: int


def run_wfs_read_only_detection(
    session: Session,
    *,
    fetch_page: PageFetcher,
    store: WfsSettlementStore,
    detection_date: date,
    msku: str | None = None,
) -> WfsReadOnlyRun:
    """Collect all pages, resolve exact listing identities, detect anomalies.

    Caller must explicitly authorize external API reads.
    No case creation, commits, flushes or background scheduling.
    """
    if not store.source_account_ref or not store.store_id or not store.store_name:
        raise ValueError("WFS_INVALID_STORE")

    window = legacy_detection_window(detection_date)
    collected = collect_wfs_settlements(
        fetch_page=fetch_page,
        store_id=store.store_id,
        start_date=window.start,
        end_date=window.end,
        msku=msku,
    )

    observed = {
        str(row.get("msku", "")).strip()
        for row in collected.rows
        if isinstance(row, dict) and row.get("msku")
    }

    standards = []
    unresolved = 0

    for code in sorted(observed):
        if code.upper().startswith("CS"):
            continue

        item_ids = session.scalars(
            select(WalmartListingDimension.item_id).where(
                WalmartListingDimension.source_account_ref == store.source_account_ref,
                WalmartListingDimension.store_id == store.store_id,
                WalmartListingDimension.msku == code,
            )
        ).all()

        if len(item_ids) != 1:
            unresolved += 1
            continue

        standard = read_product_management_wfs_fee(
            session,
            source_account_ref=store.source_account_ref,
            store_id=store.store_id,
            item_id=item_ids[0],
            msku=code,
        )
        if standard is None:
            unresolved += 1
            continue

        standards.append(standard)

    result = evaluate_wfs_settlements(
        source_account_ref=store.source_account_ref,
        stores=(store,),
        raw_rows=list(collected.rows),
        standards=standards,
        window=window,
    )

    return WfsReadOnlyRun(
        result=result,
        collected_pages=collected.pages,
        collected_rows=collected.total,
        unresolved_listings=unresolved,
    )
