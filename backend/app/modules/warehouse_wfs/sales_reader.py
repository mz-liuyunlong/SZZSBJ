"""Authoritative new-system lifetime sales reader for WFS detection."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart, WalmartListingDimension
from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunWorkItem
from app.modules.warehouse_wfs.anomaly_detection import WfsSalesEvidence


class WfsSalesReadError(ValueError):
    """Safe identity or data-quality error."""


WfsSalesIdentity = tuple[str, str, str, str]


def read_walmart_lifetime_sales_batch(
    session: Session,
    *,
    identities: frozenset[WfsSalesIdentity],
    required_coverage_start: date | None = None,
    required_coverage_end: date | None = None,
) -> dict[WfsSalesIdentity, WfsSalesEvidence]:
    """Read exact listing sales and coverage proof with three bounded queries."""

    if not identities:
        return {}
    if any(
        not all(value and value == value.strip() for value in identity) for identity in identities
    ):
        raise WfsSalesReadError("WFS_INVALID_SALES_IDENTITY")

    listing_rows = session.execute(
        select(
            WalmartListingDimension.source_account_ref,
            WalmartListingDimension.store_id,
            WalmartListingDimension.item_id,
            WalmartListingDimension.msku,
            WalmartListingDimension.listing_start_at_utc,
        ).where(
            tuple_(
                WalmartListingDimension.source_account_ref,
                WalmartListingDimension.store_id,
                WalmartListingDimension.item_id,
                WalmartListingDimension.msku,
            ).in_(identities)
        )
    ).all()
    listing_starts: dict[WfsSalesIdentity, list[datetime | None]] = {}
    for account_ref, store_id, item_id, msku, listing_start in listing_rows:
        listing_starts.setdefault((account_ref, store_id, item_id, msku), []).append(listing_start)

    aggregate_rows = session.execute(
        select(
            DailySalesItemDayMart.source_account_ref,
            DailySalesItemDayMart.store_id,
            DailySalesItemDayMart.item_id,
            DailySalesItemDayMart.msku,
            func.sum(DailySalesItemDayMart.sales_qty),
            func.min(DailySalesItemDayMart.business_date_la),
            func.max(DailySalesItemDayMart.business_date_la),
            func.count(),
        )
        .where(
            tuple_(
                DailySalesItemDayMart.source_account_ref,
                DailySalesItemDayMart.store_id,
                DailySalesItemDayMart.item_id,
                DailySalesItemDayMart.msku,
            ).in_(identities),
            func.lower(DailySalesItemDayMart.platform_code) == "walmart",
        )
        .group_by(
            DailySalesItemDayMart.source_account_ref,
            DailySalesItemDayMart.store_id,
            DailySalesItemDayMart.item_id,
            DailySalesItemDayMart.msku,
        )
    ).all()
    aggregates: dict[WfsSalesIdentity, tuple[object, object, object, object]] = {}
    for row in aggregate_rows:
        account_ref, store_id, item_id, msku, total, first_date, last_date, row_count = row
        aggregates[(account_ref, store_id, item_id, msku)] = (
            total,
            first_date,
            last_date,
            row_count,
        )

    account_refs = frozenset(identity[0] for identity in identities)
    store_ids = frozenset(identity[1] for identity in identities)
    sync_rows = session.execute(
        select(
            IntegrationSyncRun.source_account_ref,
            IntegrationSyncRun.window_start,
            IntegrationSyncRun.window_end,
            IntegrationSyncRunWorkItem.request_safe_params,
        )
        .join(
            IntegrationSyncRunWorkItem,
            IntegrationSyncRunWorkItem.run_id == IntegrationSyncRun.id,
        )
        .where(
            IntegrationSyncRun.provider == "lingxing",
            IntegrationSyncRun.interface_key == "saleStatPageList",
            IntegrationSyncRun.source_account_ref.in_(account_refs),
            IntegrationSyncRun.status == "succeeded",
            IntegrationSyncRunWorkItem.status == "succeeded",
            IntegrationSyncRunWorkItem.request_safe_params["store_id"].as_string().in_(store_ids),
        )
        .order_by(
            IntegrationSyncRun.source_account_ref,
            IntegrationSyncRun.window_start,
        )
    ).all()
    windows_by_scope: dict[tuple[str, str], list[tuple[date, date]]] = {}
    for account_ref, start, end, safe_params in sync_rows:
        store_id = str((safe_params or {}).get("store_id") or "").strip()
        if not store_id or start is None or end is None:
            continue
        windows_by_scope.setdefault((account_ref, store_id), []).append((start.date(), end.date()))

    results: dict[WfsSalesIdentity, WfsSalesEvidence] = {}
    for identity in identities:
        starts = listing_starts.get(identity, [])
        if len(starts) != 1:
            continue
        aggregate = aggregates.get(identity)
        if aggregate is None:
            results[identity] = WfsSalesEvidence(
                historical_units=None,
                sales_start_date=None,
                sales_end_date=None,
                coverage_status="missing",
                coverage_reason="no_daily_sales_rows",
            )
            continue
        total, first_date, last_date, row_count = aggregate
        if not row_count:
            continue
        try:
            units = Decimal(str(total))
        except (InvalidOperation, ValueError):
            raise WfsSalesReadError("WFS_INVALID_LIFETIME_SALES") from None
        if units < 0 or units != units.to_integral_value():
            raise WfsSalesReadError("WFS_INVALID_LIFETIME_SALES")
        if not isinstance(first_date, date) or not isinstance(last_date, date):
            raise WfsSalesReadError("WFS_INVALID_SALES_COVERAGE")

        lifecycle_start = required_coverage_start
        listing_start_at = starts[0]
        if lifecycle_start is None and isinstance(listing_start_at, datetime):
            if listing_start_at.tzinfo is None:
                results[identity] = WfsSalesEvidence(
                    historical_units=units,
                    sales_start_date=first_date,
                    sales_end_date=last_date,
                    coverage_status="unknown",
                    coverage_reason="listing_start_timezone_unproven",
                )
                continue
            lifecycle_start = listing_start_at.astimezone(ZoneInfo("America/Los_Angeles")).date()

        if lifecycle_start is None or required_coverage_end is None:
            results[identity] = WfsSalesEvidence(
                historical_units=units,
                sales_start_date=first_date,
                sales_end_date=last_date,
                coverage_status="unknown",
                coverage_reason=(
                    "product_lifecycle_start_unproven"
                    if lifecycle_start is None
                    else "required_coverage_end_unproven"
                ),
            )
            continue
        if lifecycle_start > required_coverage_end:
            raise WfsSalesReadError("WFS_INVALID_REQUIRED_COVERAGE")

        windows = windows_by_scope.get((identity[0], identity[1]), [])
        covered = _covers_date_range(
            windows,
            required_start=lifecycle_start,
            required_end=required_coverage_end,
        )
        coverage_start = min((start for start, _ in windows), default=None)
        coverage_end = max((end for _, end in windows), default=None)
        results[identity] = WfsSalesEvidence(
            historical_units=units,
            sales_start_date=first_date,
            sales_end_date=last_date,
            coverage_status="complete" if covered else "partial",
            coverage_start_date=coverage_start,
            coverage_end_date=coverage_end,
            coverage_reason=("verified_contiguous_sync_windows" if covered else "sync_window_gap"),
            source_watermark=(
                f"saleStatPageList:{coverage_start.isoformat()}:{coverage_end.isoformat()}"
                if coverage_start is not None and coverage_end is not None
                else None
            ),
        )
    return results


def read_walmart_lifetime_sales(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str,
    item_id: str,
    msku: str,
    required_coverage_start: date | None = None,
    required_coverage_end: date | None = None,
) -> WfsSalesEvidence:
    """Return lifetime Walmart sales for one exact confirmed listing identity.

    A missing mart row means coverage is unknown, not zero. Settlement evidence
    units are calculated separately from order-level fee samples.
    """

    identity = (source_account_ref, store_id, item_id, msku)
    if not all(value and value == value.strip() for value in identity):
        raise WfsSalesReadError("WFS_INVALID_SALES_IDENTITY")
    result = read_walmart_lifetime_sales_batch(
        session,
        identities=frozenset({identity}),
        required_coverage_start=required_coverage_start,
        required_coverage_end=required_coverage_end,
    ).get(identity)
    if result is None:
        raise WfsSalesReadError("WFS_SALES_IDENTITY_UNRESOLVED")
    return result


def _covers_date_range(
    windows: list[tuple[date, date]],
    *,
    required_start: date,
    required_end: date,
) -> bool:
    cursor = required_start
    for start, end in sorted(windows):
        if end < cursor:
            continue
        if start > cursor:
            return False
        cursor = date.fromordinal(end.toordinal() + 1)
        if cursor > required_end:
            return True
    return cursor > required_end
