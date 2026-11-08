"""Approval-only clearance lifecycle publisher, atomic with application approval.

When local write storage is separate, an override is recorded ONLY in local
55433 tables. Real Listing MART (15432) remains unchanged and never flushed.
Production reuses the same transaction for override + Listing MART + approval.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session


def publish_approved_lifecycle(
    storage: Session, *, listing: object, actor: str, application_id: object,
    read_only_source: bool,
) -> None:
    now = datetime.now(UTC)
    previous = getattr(listing, "lifecycle_status", None)
    reason = f"WFS清货审批通过 {application_id}"
    key = {
        "account": listing.source_account_ref,
        "store": listing.store_id,
        "item": listing.item_id,
        "listing": listing.id,
        "msku": listing.msku,
        "previous": previous,
        "stage": "清货期",
        "reason": reason[:200],
        "actor": actor,
        "timestamp": now,
        "id": uuid4(),
    }
    # These two writes AND the approval decision must commit atomically.
    storage.execute(text("""
        INSERT INTO biz_listing_lifecycle_manual_states
          (source_account_ref,store_id,item_id,stage,reason,updated_by,updated_at)
        VALUES (:account,:store,:item,:stage,:reason,:actor,:timestamp)
        ON CONFLICT (source_account_ref,store_id,item_id) DO UPDATE
        SET stage=excluded.stage,reason=excluded.reason,
            updated_by=excluded.updated_by,updated_at=excluded.updated_at
    """), key)
    storage.execute(text("""
        INSERT INTO biz_listing_lifecycle_manual_history
          (id,source_account_ref,store_id,item_id,listing_id,msku,
           previous_stage,new_stage,reason,actor_ref,changed_at)
        VALUES (:id,:account,:store,:item,:listing,:msku,
                :previous,:stage,:reason,:actor,:timestamp)
    """), key)
    if not read_only_source:
        # Only same-DB production transaction changes real Listing immediately.
        listing.lifecycle_status = "清货期"
