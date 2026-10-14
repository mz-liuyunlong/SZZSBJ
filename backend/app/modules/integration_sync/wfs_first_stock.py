"""First WFS-stock launch-date safeguards for Walmart Listing Management.

This module records the first fresh observation where a newly monitored listing
has WFS inventory >= 1. It deliberately does not backfill existing listings:
current inventory can prove that a listing is in stock now, but cannot prove
when the listing first became available.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Date, DateTime, String, Text, Uuid, bindparam, text
from sqlalchemy.orm import Session

CHINA_TZ = ZoneInfo("Asia/Shanghai")


def listing_identity(
    store_id: str | None,
    item_id: str | None,
    msku: str | None,
) -> tuple[str, str, str] | None:
    """Return a strict, nonempty, case-sensitive Listing identity."""
    parts = (store_id, item_id, msku)
    if not all(isinstance(value, str) and value.strip() for value in parts):
        return None
    return (
        store_id.strip(),  # type: ignore[union-attr]
        item_id.strip(),  # type: ignore[union-attr]
        msku.strip(),  # type: ignore[union-attr]
    )


def chinese_observed_date(observed_at_utc: datetime) -> date:
    """Convert an aware observation instant to a China calendar date."""
    if observed_at_utc.tzinfo is None or observed_at_utc.utcoffset() is None:
        raise ValueError("WFS observation must be timezone aware")
    return observed_at_utc.astimezone(CHINA_TZ).date()


def stock_is_available(value: Decimal | None) -> bool:
    """Only a fresh, valid WFS quantity >= 1 triggers the first-stock transition."""
    return value is not None and value.is_finite() and value >= Decimal("1")


_COMMON_BINDS = (
    bindparam("account", type_=String(128)),
    bindparam("store_id", type_=String(128)),
    bindparam("item_id", type_=String(128)),
    bindparam("msku", type_=Text()),
    bindparam("observed_at", type_=DateTime(timezone=True)),
)

# Never seed monitoring for identities already present before this feature.
# This is an eligibility gate, not a fallback identity match or a date assignment.
_ENROLL_SQL = text(
    """
    INSERT INTO listing_wfs_first_stock
      (id, source_account_ref, store_id, item_id, msku,
       monitoring_started_at_utc, first_wfs_seen_at_utc,
       launch_date_cn, date_source, created_at)
    SELECT :id, :account, :store_id, :item_id, :msku,
           :observed_at, NULL, NULL, 'pending', :observed_at
    WHERE NOT EXISTS (
        SELECT 1 FROM dim_walmart_listings d
        WHERE d.source_account_ref = :account
          AND d.store_id = :store_id
          AND d.item_id = :item_id
    ) AND NOT EXISTS (
        SELECT 1 FROM mart_listing_management_current m
        WHERE m.source_account_ref = :account
          AND m.store_id = :store_id
          AND m.item_id = :item_id
    )
    ON CONFLICT (source_account_ref, store_id, item_id, msku) DO NOTHING
    """
).bindparams(
    bindparam("id", type_=Uuid(as_uuid=True)),
    *_COMMON_BINDS,
)

# A monitored identity remains eligible across an initial 0-stock snapshot.
# The update is atomic and fill-only; a historical corrected MART value wins.
_FIRST_STOCK_SQL = text(
    """
    UPDATE listing_wfs_first_stock AS f
    SET first_wfs_seen_at_utc = :observed_at,
        launch_date_cn = :launch_date_cn,
        date_source = 'wfs_first_stock'
    WHERE f.source_account_ref = :account
      AND f.store_id = :store_id
      AND f.item_id = :item_id
      AND f.msku = :msku
      AND f.first_wfs_seen_at_utc IS NULL
      AND f.launch_date_cn IS NULL
      AND f.monitoring_started_at_utc <= :observed_at
      AND NOT EXISTS (
          SELECT 1 FROM dim_walmart_listings d
          WHERE d.source_account_ref = :account
            AND d.store_id = :store_id
            AND d.item_id = :item_id
            AND (d.msku IS NULL OR trim(d.msku) <> :msku)
      )
      AND NOT EXISTS (
          SELECT 1 FROM mart_listing_management_current m
          WHERE m.source_account_ref = :account
            AND m.store_id = :store_id
            AND m.item_id = :item_id
            AND (
                m.listing_start_at_utc IS NOT NULL
                OR (m.msku IS NOT NULL AND trim(m.msku) <> :msku)
            )
      )
    """
).bindparams(
    *_COMMON_BINDS,
    bindparam("launch_date_cn", type_=Date()),
)


def observe_first_wfs_stock(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str | None,
    item_id: str | None,
    msku: str | None,
    wfs_quantity: Decimal | None,
    observed_at_utc: datetime,
) -> None:
    """Enroll only a new Listing and set its first stocked instant once.

    This function never commits, never calls external APIs, and never treats
    cached database inventory as a fresh observation.
    """
    identity = listing_identity(store_id, item_id, msku)
    if identity is None:
        return

    clean_store_id, clean_item_id, clean_msku = identity
    params = {
        "id": uuid4(),
        "account": source_account_ref,
        "store_id": clean_store_id,
        "item_id": clean_item_id,
        "msku": clean_msku,
        "observed_at": observed_at_utc,
        "launch_date_cn": chinese_observed_date(observed_at_utc),
    }

    session.execute(_ENROLL_SQL, params)
    if stock_is_available(wfs_quantity):
        session.execute(_FIRST_STOCK_SQL, params)
