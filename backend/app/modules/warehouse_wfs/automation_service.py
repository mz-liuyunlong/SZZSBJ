"""Stored-evidence WFS detection and optional insert-only case creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.data_pages.models import WalmartListingDimension
from app.modules.warehouse_wfs.anomaly_detection import detect_wfs_anomalies
from app.modules.warehouse_wfs.auto_case_writer import (
    create_wfs_case,
    record_wfs_detection_evidence,
)
from app.modules.warehouse_wfs.fee_detection import resolve_wfs_fees
from app.modules.warehouse_wfs.sales_reader import (
    WfsSalesReadError,
    read_walmart_lifetime_sales_batch,
)
from app.modules.warehouse_wfs.settlement_repository import WfsSettlementRepository
from app.modules.warehouse_wfs.standard_fee_reader import read_product_management_wfs_fees
from app.modules.warehouse_wfs.store_discovery import discover_walmart_stores


@dataclass(frozen=True, slots=True)
class WfsStoreDetectionPreview:
    source_account_ref: str
    store_id: str
    scanned_skus: int
    valid_samples: int
    overcharge_candidates: int
    would_create: int
    already_exists: int
    review_required: int
    skipped: int


@dataclass(frozen=True, slots=True)
class WfsBatchDetectionPreview:
    scanned_accounts: int
    scanned_stores: int
    scanned_skus: int
    valid_samples: int
    overcharge_candidates: int
    would_create: int
    already_exists: int
    review_required: int
    skipped: int
    failed: int
    stores: tuple[WfsStoreDetectionPreview, ...]


def detect_store_from_persisted_evidence(
    session: Session,
    *,
    settings: Settings,
    source_account_ref: str,
    store_id: str,
    start_date: date,
    end_date: date,
    execute_cases: bool = False,
    collection_id: UUID | None = None,
    detection_executed_at: datetime | None = None,
    business_as_of_date: date | None = None,
    backtest: bool = False,
    persist_evidence: bool = False,
) -> WfsStoreDetectionPreview:
    """Detect one store after collection completed and pagination was verified."""

    repository = WfsSettlementRepository(session)
    if backtest and (execute_cases or persist_evidence):
        raise ValueError("WFS_BACKTEST_WRITE_FORBIDDEN")
    collection = repository.get_verified_collection(
        source_account_ref=source_account_ref,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
    )
    if collection is None or (collection_id is not None and collection.id != collection_id):
        raise ValueError("WFS_COLLECTION_NOT_VERIFIED")

    rows = repository.list_rows(
        source_account_ref=source_account_ref,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        collection_id=collection.id,
    )
    resolved = resolve_wfs_fees(
        list(rows),
        min_sample_units=settings.wfs_detect_min_sample_units,
    )

    candidates = 0
    would_create = 0
    already_exists = 0
    review_required = 0
    skipped = 0

    item_rows = session.execute(
        select(WalmartListingDimension.msku, WalmartListingDimension.item_id).where(
            WalmartListingDimension.source_account_ref == source_account_ref,
            WalmartListingDimension.store_id == store_id,
            WalmartListingDimension.msku.in_([item.msku for item in resolved]),
        )
    ).all()
    item_ids_by_msku: dict[str, list[str]] = {}
    for msku, item_id in item_rows:
        item_ids_by_msku.setdefault(msku, []).append(item_id)

    identity_values: set[tuple[str, str, str, str]] = set()
    for actual in resolved:
        item_ids = item_ids_by_msku.get(actual.msku, [])
        if len(item_ids) == 1:
            identity_values.add((source_account_ref, store_id, item_ids[0], actual.msku))
    resolved_identities = frozenset(identity_values)
    standards_by_identity = read_product_management_wfs_fees(
        session,
        identities=resolved_identities,
    )
    try:
        sales_by_identity = read_walmart_lifetime_sales_batch(
            session,
            identities=resolved_identities,
            required_coverage_end=end_date,
        )
    except WfsSalesReadError:
        sales_by_identity = {}

    executed_at = detection_executed_at or datetime.now(UTC)
    effective_date = business_as_of_date if backtest else executed_at.date()
    if effective_date is None:
        raise ValueError("WFS_BACKTEST_DATE_REQUIRED")

    for actual in resolved:
        item_ids = item_ids_by_msku.get(actual.msku, [])
        if len(item_ids) != 1:
            skipped += 1
            continue
        item_id = item_ids[0]
        identity = (source_account_ref, store_id, item_id, actual.msku)
        standard = standards_by_identity.get(identity)
        if standard is None:
            skipped += 1
            continue
        sales = sales_by_identity.get(identity)
        if sales is None:
            skipped += 1
            continue

        key = (source_account_ref, store_id, actual.msku)
        detection = detect_wfs_anomalies(
            [actual],
            [standard],
            {key: sales},
            as_of=effective_date,
            max_stale_days=settings.wfs_detect_max_stale_days,
        )
        if not detection.candidates:
            skipped += 1
            continue
        candidate = detection.candidates[0]
        candidates += 1
        result = create_wfs_case(
            session,
            item_id=item_id,
            candidate=candidate,
            execute=execute_cases,
            detect_enabled=settings.wfs_auto_detect_enabled,
            case_create_enabled=settings.wfs_auto_case_create_enabled,
        )
        record_wfs_detection_evidence(
            session,
            collection_id=collection.id,
            item_id=item_id,
            candidate=candidate,
            case_id=result.case_id,
            business_as_of_date=effective_date,
            detected_at=executed_at,
            persist=persist_evidence,
            is_backtest=backtest,
        )
        if result.action == "dry_run":
            would_create += 1
        elif result.action == "created":
            would_create += 1
        elif result.action == "already_exists":
            already_exists += 1
        else:
            review_required += 1

    return WfsStoreDetectionPreview(
        source_account_ref=source_account_ref,
        store_id=store_id,
        scanned_skus=len(resolved),
        valid_samples=sum(item.unit_fee is not None for item in resolved),
        overcharge_candidates=candidates,
        would_create=would_create,
        already_exists=already_exists,
        review_required=review_required,
        skipped=skipped,
    )


def preview_persisted_wfs_detection(
    session: Session,
    *,
    settings: Settings,
    source_account_refs: frozenset[str],
    start_date: date,
    end_date: date,
    store_id: str | None = None,
) -> WfsBatchDetectionPreview:
    """Run a database-read-only preview over authorized accounts and stores."""

    if not source_account_refs or start_date > end_date:
        raise ValueError("WFS_PREVIEW_SCOPE_INVALID")
    if (end_date - start_date).days + 1 > 366:
        raise ValueError("WFS_PREVIEW_WINDOW_TOO_LARGE")

    previews: list[WfsStoreDetectionPreview] = []
    failed = 0
    for account_ref in sorted(source_account_refs):
        stores = discover_walmart_stores(session, source_account_ref=account_ref)
        selected = tuple(item for item in stores if store_id is None or item.store_id == store_id)
        if store_id is not None and not selected:
            continue
        for store in selected:
            try:
                previews.append(
                    detect_store_from_persisted_evidence(
                        session,
                        settings=settings,
                        source_account_ref=account_ref,
                        store_id=store.store_id,
                        start_date=start_date,
                        end_date=end_date,
                        execute_cases=False,
                    )
                )
            except (ValueError, WfsSalesReadError):
                failed += 1

    return WfsBatchDetectionPreview(
        scanned_accounts=len(source_account_refs),
        scanned_stores=len(previews) + failed,
        scanned_skus=sum(item.scanned_skus for item in previews),
        valid_samples=sum(item.valid_samples for item in previews),
        overcharge_candidates=sum(item.overcharge_candidates for item in previews),
        would_create=sum(item.would_create for item in previews),
        already_exists=sum(item.already_exists for item in previews),
        review_required=sum(item.review_required for item in previews),
        skipped=sum(item.skipped for item in previews),
        failed=failed,
        stores=tuple(previews),
    )
