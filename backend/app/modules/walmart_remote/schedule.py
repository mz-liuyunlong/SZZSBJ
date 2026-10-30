"""Explicitly gated twice-weekly eight-store remote scheduler, read-only jobs only."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.integrations.walmart.remote_dispatch import (
    REMOTE_COLLECTION_STORES,
    DispatchRejected,
    parse_routes,
)
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.walmart_remote.models import WalmartRemoteJob
from app.modules.walmart_remote.store_mapping import remote_store_mapping

PACIFIC = ZoneInfo("America/Los_Angeles")


def eligible_schedule(now: datetime) -> str | None:
    """Wednesday/Saturday at 09:00 Pacific, once per local calendar date."""
    if now.tzinfo is None:
        raise ValueError("SCHEDULE_TIMEZONE_REQUIRED")
    local = now.astimezone(PACIFIC)
    # Reconciliation ticks can arrive late; the date key prevents reruns.
    if local.weekday() not in (2, 5) or local.hour < 9:
        return None
    return local.strftime("%Y%m%d")


def queue_due_stores(session: Session, *, now: datetime) -> list[str]:
    """Return pending job IDs, never secrets. Caller enqueues after commit.

    All eight selected stores must have distinct approved hosts and verified persisted
    Walmart identities. CN2502 can remain in the legacy store map but is not scheduled.
    """
    date_key = eligible_schedule(now)
    if date_key is None:
        return []
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        return []
    if os.getenv("SZZSBJ_WALMART_REMOTE_SCHEDULE_ENABLED") != "1":
        return []
    try:
        routes = parse_routes(os.getenv("SZZSBJ_WALMART_REMOTE_ROUTES", ""))
        mapping = remote_store_mapping()
    except (ApiError, DispatchRejected):
        return []
    approved = frozenset(
        code.strip()
        for code in os.getenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", "").split(",")
        if code.strip()
    )
    active_mapping = {
        store_id: code for store_id, code in mapping.items() if code in REMOTE_COLLECTION_STORES
    }
    if (
        set(routes) != REMOTE_COLLECTION_STORES
        or approved != REMOTE_COLLECTION_STORES
        or set(active_mapping.values()) != REMOTE_COLLECTION_STORES
        or len(active_mapping) != len(REMOTE_COLLECTION_STORES)
    ):
        return []
    existing = session.scalars(
        select(LingxingStoreDimension).where(
            LingxingStoreDimension.store_id.in_(list(active_mapping)),
            LingxingStoreDimension.platform_code == "walmart",
            LingxingStoreDimension.is_sync.is_(True),
        )
    ).all()
    if len(existing) != len(REMOTE_COLLECTION_STORES) or len(
        {item.store_id for item in existing}
    ) != len(REMOTE_COLLECTION_STORES):
        return []
    if any(
        not (item.store_name or "").startswith(active_mapping[item.store_id] + "-")
        for item in existing
    ):
        return []
    jobs: list[WalmartRemoteJob] = []
    queued_ids: list[str] = []
    for row in existing:
        key = "scheduled-" + date_key + "-" + active_mapping[row.store_id]
        prior = session.scalar(
            select(WalmartRemoteJob).where(
                WalmartRemoteJob.source_account_ref == row.source_account_ref,
                WalmartRemoteJob.store_id == row.store_id,
                WalmartRemoteJob.request_key == key,
            )
        )
        if prior is not None:
            if prior.status == "queued":
                queued_ids.append(str(prior.id))
            continue
        jobs.append(
            WalmartRemoteJob(
                source_account_ref=row.source_account_ref,
                store_id=row.store_id,
                store_code=active_mapping[row.store_id],
                requested_by="system:walmart-remote-schedule",
                request_key=key,
                operations=[
                    "wfs_inventory",
                    "inbound_shipments",
                    "inbound_shipment_items",
                    "inventory_log",
                ],
                status="queued",
            )
        )
    session.add_all(jobs)
    session.flush()
    return queued_ids + [str(job.id) for job in jobs]
