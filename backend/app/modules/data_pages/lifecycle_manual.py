"""Scoped, atomic manual Listing lifecycle writes with immutable change history.

Source-of-truth for manual overrides is a stable account/store/Item ID record.
The operational Listing MART is updated for current readers, but a full rebuild
must restore the manual override from this table before publishing results.
The future lifecycle automation MUST check this manual-state table before writing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart

EDITABLE_STAGES = frozenset(
    {
        "测品期",
        "打品期",
        "启动期",
        "上升期",
        "稳定期",
        "下滑期",
        "断货期",
        "修复期",
    }
)
PROTECTED_STAGES = frozenset({"清货期", "已归档"})


def set_manual_lifecycle(
    *,
    session: Session,
    listing_ids: list[UUID],
    stage: str,
    reason: str,
    actor_ref: str,
    account_refs: frozenset[str],
) -> tuple[int, int]:
    """Fail as a whole on missing/out-of-scope ids or workflow-controlled stages."""
    if stage not in EDITABLE_STAGES:
        raise ValueError("生命周期阶段无效或必须通过专项业务流程设置")
    ids = list(dict.fromkeys(listing_ids))
    if not ids or len(ids) > 200 or len(ids) != len(listing_ids):
        raise ValueError("请选择1至200个不重复Listing")
    if not account_refs:
        raise PermissionError("No source-account scope")
    if len(reason.strip()) < 2:
        raise ValueError("请填写修改原因")

    rows = list(
        session.scalars(
            select(ListingManagementCurrentMart)
            .where(
                ListingManagementCurrentMart.id.in_(ids),
                ListingManagementCurrentMart.source_account_ref.in_(account_refs),
            )
            .order_by(ListingManagementCurrentMart.id)
            .with_for_update()
        ).all()
    )
    if len(rows) != len(ids):
        raise PermissionError("Unrecognized or inaccessible Listing")

    # Existing archival/clearance workflows cannot be bypassed by this API.
    active_archive_ids = (
        session.execute(
            text("""
        SELECT listing_id FROM listing_archive_states
        WHERE listing_id = ANY(:listing_ids) AND is_archived = TRUE
    """),
            {"listing_ids": ids},
        )
        .scalars()
        .all()
    )
    if active_archive_ids or any(row.lifecycle_status in PROTECTED_STAGES for row in rows):
        raise ValueError("包含清货期或已归档Listing，不能人工覆盖")

    updated = 0
    unchanged = 0
    stamp = datetime.now(UTC)
    for row in rows:
        same_stage = row.lifecycle_status == stage
        previous = row.lifecycle_status
        # Stable business key survives SKU/MSKU changes.
        session.execute(
            text("""
            INSERT INTO biz_listing_lifecycle_manual_states
              (source_account_ref, store_id, item_id, stage, reason,
               updated_by, updated_at)
            VALUES (:account, :store, :item, :stage, :reason, :actor, :stamp)
            ON CONFLICT (source_account_ref, store_id, item_id)
            DO UPDATE SET stage = EXCLUDED.stage, reason = EXCLUDED.reason,
                          updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
        """),
            {
                "account": row.source_account_ref,
                "store": row.store_id,
                "item": row.item_id,
                "stage": stage,
                "reason": reason.strip(),
                "actor": actor_ref,
                "stamp": stamp,
            },
        )
        session.execute(
            text("""
            INSERT INTO biz_listing_lifecycle_manual_history
              (id, source_account_ref, store_id, item_id, msku, listing_id,
               previous_stage, new_stage, reason, actor_ref, changed_at)
            VALUES (:id, :account, :store, :item, :msku, :listing,
                    :old, :new, :reason, :actor, :stamp)
        """),
            {
                "id": uuid4(),
                "account": row.source_account_ref,
                "store": row.store_id,
                "item": row.item_id,
                "msku": row.msku,
                "listing": row.id,
                "old": previous,
                "new": stage,
                "reason": reason.strip(),
                "actor": actor_ref,
                "stamp": stamp,
            },
        )
        if same_stage:
            unchanged += 1
        else:
            row.lifecycle_status = stage
            updated += 1
    session.commit()
    return updated, unchanged
