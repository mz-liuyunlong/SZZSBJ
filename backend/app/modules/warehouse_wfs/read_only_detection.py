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
    read_product_management_wfs_fees,
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

    eligible_codes = {code for code in observed if not code.upper().startswith("CS")}
    listing_rows = session.execute(
        select(WalmartListingDimension.msku, WalmartListingDimension.item_id).where(
            WalmartListingDimension.source_account_ref == store.source_account_ref,
            WalmartListingDimension.store_id == store.store_id,
            WalmartListingDimension.msku.in_(eligible_codes),
        )
    ).all()
    item_ids_by_msku: dict[str, list[str]] = {}
    for code, item_id in listing_rows:
        item_ids_by_msku.setdefault(code, []).append(item_id)
    identity_values = frozenset(
        (store.source_account_ref, store.store_id, item_ids[0], code)
        for code, item_ids in item_ids_by_msku.items()
        if len(item_ids) == 1
    )
    standards_by_identity = read_product_management_wfs_fees(
        session,
        identities=identity_values,
    )
    standards = list(standards_by_identity.values())
    unresolved = len(eligible_codes) - len(standards)

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
