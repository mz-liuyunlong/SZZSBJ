"""Authoritative new-system lifetime sales reader for WFS detection."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart, WalmartListingDimension
from app.modules.warehouse_wfs.anomaly_detection import WfsSalesEvidence


class WfsSalesReadError(ValueError):
    """Safe identity or data-quality error."""


def read_walmart_lifetime_sales(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str,
    item_id: str,
    msku: str,
) -> WfsSalesEvidence:
    """Return lifetime Walmart sales for one exact confirmed listing identity.

    A missing mart row means coverage is unknown, not zero. Settlement evidence
    units are calculated separately from order-level fee samples.
    """

    identities = (source_account_ref, store_id, item_id, msku)
    if not all(value and value == value.strip() for value in identities):
        raise WfsSalesReadError("WFS_INVALID_SALES_IDENTITY")

    listing_count = session.scalar(
        select(func.count())
        .select_from(WalmartListingDimension)
        .where(
            WalmartListingDimension.source_account_ref == source_account_ref,
            WalmartListingDimension.store_id == store_id,
            WalmartListingDimension.item_id == item_id,
            WalmartListingDimension.msku == msku,
        )
    )
    if listing_count != 1:
        raise WfsSalesReadError("WFS_SALES_IDENTITY_UNRESOLVED")

    total, first_date, last_date, row_count = session.execute(
        select(
            func.sum(DailySalesItemDayMart.sales_qty),
            func.min(DailySalesItemDayMart.business_date_la),
            func.max(DailySalesItemDayMart.business_date_la),
            func.count(),
        ).where(
            DailySalesItemDayMart.source_account_ref == source_account_ref,
            DailySalesItemDayMart.store_id == store_id,
            DailySalesItemDayMart.item_id == item_id,
            DailySalesItemDayMart.msku == msku,
            func.lower(DailySalesItemDayMart.platform_code) == "walmart",
        )
    ).one()

    if not row_count:
        return WfsSalesEvidence(
            historical_units=None,
            sales_start_date=None,
            sales_end_date=None,
            coverage_status="missing",
        )

    units = Decimal(total)
    if units < 0 or units != units.to_integral_value():
        raise WfsSalesReadError("WFS_INVALID_LIFETIME_SALES")
    if not isinstance(first_date, date) or not isinstance(last_date, date):
        raise WfsSalesReadError("WFS_INVALID_SALES_COVERAGE")

    return WfsSalesEvidence(
        historical_units=units,
        sales_start_date=first_date,
        sales_end_date=last_date,
        coverage_status="complete",
    )
