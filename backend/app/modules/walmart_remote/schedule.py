"""Explicitly gated twice-weekly nine-store scheduler, read-only jobs only."""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.walmart.remote_dispatch import STORES, parse_routes
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.walmart_remote.models import WalmartRemoteJob

PACIFIC = ZoneInfo("America/Los_Angeles")


def eligible_schedule(now: datetime) -> str | None:
    """Wednesday/Saturday at 09:00 Pacific, once per local calendar date."""
    if now.tzinfo is None:
        raise ValueError("SCHEDULE_TIMEZONE_REQUIRED")
    local = now.astimezone(PACIFIC)
    if local.weekday() not in (2, 5) or local.hour != 9:
        return None
    return local.strftime("%Y%m%d")


def queue_due_stores(session: Session, *, now: datetime) -> list[str]:
    """Return pending job IDs, never secrets. Caller enqueues after commit.

    All nine stores must resolve to distinct approved hosts and exact persisted
    Walmart store identities. Missing CN2502 route blocks batch creation.
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
        mapping = json.loads(os.getenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", "{}"))
    except (ValueError, TypeError):
        return []
    if (
        set(routes) != STORES
        or not isinstance(mapping, dict)
        or set(mapping.values()) != STORES
        or len(mapping) != 9
    ):
        return []
    by_store = {code: sid for sid, code in mapping.items()}
    existing = session.scalars(
        select(LingxingStoreDimension).where(
            LingxingStoreDimension.store_id.in_(list(mapping)),
            LingxingStoreDimension.platform_code == "walmart",
            LingxingStoreDimension.is_sync.is_(True),
        )
    ).all()
    if len(existing) != 9 or len({item.store_id for item in existing}) != 9:
        return []
    if any(
        not (item.store_name or "").startswith(mapping[item.store_id] + "-")
        for item in existing
    ):
        return []
    jobs: list[WalmartRemoteJob] = []
    for row in existing:
        key = "scheduled-" + date_key + "-" + mapping[row.store_id]
        prior = session.scalar(
            select(WalmartRemoteJob.id).where(
                WalmartRemoteJob.source_account_ref == row.source_account_ref,
                WalmartRemoteJob.store_id == row.store_id,
                WalmartRemoteJob.request_key == key,
            )
        )
        if prior is not None:
            continue
        jobs.append(
            WalmartRemoteJob(
                source_account_ref=row.source_account_ref,
                store_id=row.store_id,
                store_code=mapping[row.store_id],
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
    return [str(job.id) for job in jobs]
