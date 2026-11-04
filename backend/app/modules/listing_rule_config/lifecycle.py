"""Manual Listing lifecycle decisions with separate requester and approver."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import ListingArchiveState, ListingManagementCurrentMart
from app.modules.listing_rule_config.models import ListingLifecycleAdjustment


class ListingLifecycleAdjustmentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _listing(
        self, listing_id: UUID, account_refs: frozenset[str], *, lock: bool = False
    ) -> ListingManagementCurrentMart:
        statement = select(ListingManagementCurrentMart).where(
            ListingManagementCurrentMart.id == listing_id,
            ListingManagementCurrentMart.source_account_ref.in_(account_refs),
        )
        row = self.session.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return row

    def request(
        self,
        *,
        listing_id: UUID,
        requested_stage: str,
        reason: str,
        actor: str,
        account_refs: frozenset[str],
    ) -> ListingLifecycleAdjustment:
        try:
            listing = self._listing(listing_id, account_refs, lock=True)
            if listing.fulfillment_type != "1":
                raise ApiError(code="LISTING_LIFECYCLE_WFS_ONLY", status_code=409)
            archived = self.session.scalar(
                select(ListingArchiveState.is_archived).where(
                    ListingArchiveState.listing_id == listing_id
                )
            )
            if archived:
                raise ApiError(code="LISTING_LIFECYCLE_ARCHIVED", status_code=409)
            if listing.lifecycle_status == requested_stage:
                raise ApiError(code="LISTING_LIFECYCLE_NO_CHANGE", status_code=409)
            row = ListingLifecycleAdjustment(
                listing_id=listing.id,
                source_account_ref=listing.source_account_ref,
                store_id=listing.store_id,
                item_id=listing.item_id,
                expected_stage=listing.lifecycle_status,
                requested_stage=requested_stage,
                reason=reason.strip(),
                status="pending",
                requested_by=actor,
                requested_at=datetime.now(UTC),
            )
            self.session.add(row)
            self.session.commit()
            return row
        except Exception:
            self.session.rollback()
            raise

    def decide(
        self,
        *,
        adjustment_id: UUID,
        approve: bool,
        note: str,
        actor: str,
        account_refs: frozenset[str],
    ) -> ListingLifecycleAdjustment:
        try:
            row = self.session.scalar(
                select(ListingLifecycleAdjustment)
                .where(
                    ListingLifecycleAdjustment.id == adjustment_id,
                    ListingLifecycleAdjustment.source_account_ref.in_(account_refs),
                )
                .with_for_update()
            )
            if row is None:
                raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
            if row.status != "pending":
                raise ApiError(code="LISTING_LIFECYCLE_ALREADY_DECIDED", status_code=409)
            if row.requested_by == actor:
                raise ApiError(code="LISTING_LIFECYCLE_SEPARATE_APPROVER_REQUIRED", status_code=403)
            listing = self._listing(row.listing_id, account_refs, lock=True)
            if (
                listing.source_account_ref != row.source_account_ref
                or listing.store_id != row.store_id
                or listing.item_id != row.item_id
                or listing.lifecycle_status != row.expected_stage
            ):
                raise ApiError(code="LISTING_LIFECYCLE_STALE_REQUEST", status_code=409)
            if approve:
                archived = self.session.scalar(
                    select(ListingArchiveState.is_archived).where(
                        ListingArchiveState.listing_id == row.listing_id
                    )
                )
                if listing.fulfillment_type != "1" or archived:
                    raise ApiError(code="LISTING_LIFECYCLE_SOURCE_CHANGED", status_code=409)
                listing.lifecycle_status = row.requested_stage
            row.status = "approved" if approve else "rejected"
            row.decided_by = actor
            row.decided_at = datetime.now(UTC)
            row.decision_note = note.strip()
            self.session.commit()
            return row
        except Exception:
            self.session.rollback()
            raise
