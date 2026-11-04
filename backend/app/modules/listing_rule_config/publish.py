"""Conservative per-Listing publication of frozen evaluation snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeFollowUpTask,
    ListingGradeRuleVersion,
    ListingLifecycleAdjustment,
)
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


class ListingEvaluationPublisher:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish_run(self, *, run_id: UUID) -> int:
        """Each Listing either publishes atomically or retains its prior MART values."""
        if not get_settings().listing_evaluation_publish_enabled:
            return 0
        run = self.session.get(ListingEvaluationRun, run_id)
        if run is None or run.status != "succeeded" or run.rule_version <= 0:
            return 0
        snapshot_ids = list(
            self.session.scalars(
                select(ListingEvaluationSnapshot.id)
                .where(ListingEvaluationSnapshot.run_id == run_id)
                .order_by(ListingEvaluationSnapshot.id)
            ).all()
        )
        self.session.commit()
        published = 0
        for snapshot_id in snapshot_ids:
            try:
                self.session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                snapshot = self.session.scalar(
                    select(ListingEvaluationSnapshot)
                    .where(ListingEvaluationSnapshot.id == snapshot_id)
                    .with_for_update()
                )
                if (
                    snapshot is None
                    or snapshot.published
                    or snapshot.publication_status != "candidate_only"
                ):
                    self.session.rollback()
                    continue
                error = self._publish_one(snapshot)
                if error is not None:
                    snapshot.publication_status = "blocked"
                    snapshot.publication_error_code = error
                else:
                    current_run = self.session.get(ListingEvaluationRun, run_id)
                    if current_run is None:
                        raise RuntimeError("Listing evaluation run disappeared")
                    current_run.published_count += 1
                    published += 1
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
        return published

    def _publish_one(self, snapshot: ListingEvaluationSnapshot) -> str | None:
        listing = self.session.scalar(
            select(ListingManagementCurrentMart)
            .where(ListingManagementCurrentMart.id == snapshot.listing_id)
            .with_for_update()
        )
        if listing is None or (
            listing.source_account_ref,
            listing.store_id,
            listing.item_id,
            listing.msku,
        ) != (
            snapshot.source_account_ref,
            snapshot.store_id,
            snapshot.item_id,
            snapshot.msku,
        ):
            return "LISTING_EVALUATION_IDENTITY_CHANGED"
        if (
            listing.lifecycle_status != snapshot.current_lifecycle
            or listing.product_grade != snapshot.current_grade
        ):
            return "LISTING_EVALUATION_CURRENT_STATE_CHANGED"
        rule = self.session.get(ListingGradeRuleVersion, snapshot.rule_version)
        if rule is None or rule.version <= 0 or rule.effective_from > datetime.now(UTC):
            return "LISTING_EVALUATION_RULE_UNAVAILABLE"
        if snapshot.evidence_json or snapshot.grade_candidate not in {"A", "B", "C", "D"}:
            return "LISTING_EVALUATION_EVIDENCE_INCOMPLETE"
        if snapshot.lifecycle_candidate is None:
            return "LISTING_EVALUATION_LIFECYCLE_UNCONFIRMED"
        manual = self.session.scalar(
            select(ListingLifecycleAdjustment.id)
            .where(
                ListingLifecycleAdjustment.listing_id == listing.id,
                ListingLifecycleAdjustment.status == "approved",
            )
            .limit(1)
        )
        if manual is not None and snapshot.lifecycle_candidate != listing.lifecycle_status:
            return "LISTING_EVALUATION_MANUAL_STAGE_PROTECTED"
        result = ListingEvaluationPreviewService(self.session).evaluate(
            listing_id=listing.id,
            account_refs=frozenset({listing.source_account_ref}),
            cutoff=snapshot.cutoff_date_la,
            config=ListingGradeRuleConfig.model_validate(rule.config_json),
            rule_version=rule.version,
        )
        if (
            result.missing_evidence
            or result.rule_version != snapshot.rule_version
            or result.lifecycle_candidate != snapshot.lifecycle_candidate
            or result.grade_candidate != snapshot.grade_candidate
            or result.valid_short != snapshot.valid_short
            or result.valid_medium != snapshot.valid_medium
            or result.valid_stock_days_30 != snapshot.valid_stock_days_30
            or result.weighted_margin_percent != snapshot.weighted_margin_percent
        ):
            return "LISTING_EVALUATION_EVIDENCE_CHANGED"
        listing.lifecycle_status = snapshot.lifecycle_candidate
        listing.product_grade = snapshot.grade_candidate
        snapshot.publication_status = "published"
        snapshot.published = True
        snapshot.published_at = datetime.now(UTC)
        snapshot.published_by = "system:listing-evaluation"
        return None

    def revert_snapshot(
        self,
        *,
        snapshot_id: UUID,
        actor: str,
        reason: str,
        account_refs: frozenset[str],
    ) -> ListingEvaluationSnapshot:
        """Compensate one latest publication without erasing its audit history."""
        from app.core.api import ApiError, ErrorCode

        try:
            snapshot = self.session.scalar(
                select(ListingEvaluationSnapshot)
                .where(
                    ListingEvaluationSnapshot.id == snapshot_id,
                    ListingEvaluationSnapshot.source_account_ref.in_(account_refs),
                )
                .with_for_update()
            )
            if snapshot is None:
                raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
            if (
                not snapshot.published
                or snapshot.reverted_at is not None
                or snapshot.published_at is None
            ):
                raise ApiError(code="LISTING_EVALUATION_NOT_ACTIVE", status_code=409)
            listing = self.session.scalar(
                select(ListingManagementCurrentMart)
                .where(
                    ListingManagementCurrentMart.id == snapshot.listing_id,
                    ListingManagementCurrentMart.source_account_ref.in_(account_refs),
                )
                .with_for_update()
            )
            if listing is None or (
                listing.source_account_ref,
                listing.store_id,
                listing.item_id,
                listing.msku,
                listing.lifecycle_status,
                listing.product_grade,
            ) != (
                snapshot.source_account_ref,
                snapshot.store_id,
                snapshot.item_id,
                snapshot.msku,
                snapshot.lifecycle_candidate,
                snapshot.grade_candidate,
            ):
                raise ApiError(code="LISTING_EVALUATION_STATE_CHANGED", status_code=409)
            newer = self.session.scalar(
                select(ListingEvaluationSnapshot.id)
                .where(
                    ListingEvaluationSnapshot.listing_id == listing.id,
                    ListingEvaluationSnapshot.id != snapshot.id,
                    ListingEvaluationSnapshot.published.is_(True),
                    ListingEvaluationSnapshot.reverted_at.is_(None),
                    ListingEvaluationSnapshot.published_at >= snapshot.published_at,
                )
                .limit(1)
            )
            manual_after = self.session.scalar(
                select(ListingLifecycleAdjustment.id)
                .where(
                    ListingLifecycleAdjustment.listing_id == listing.id,
                    ListingLifecycleAdjustment.status == "approved",
                    ListingLifecycleAdjustment.decided_at >= snapshot.published_at,
                )
                .limit(1)
            )
            if newer is not None or manual_after is not None:
                raise ApiError(code="LISTING_EVALUATION_LATER_CHANGE", status_code=409)
            listing.lifecycle_status = snapshot.current_lifecycle
            listing.product_grade = snapshot.current_grade
            snapshot.publication_status = "reverted"
            snapshot.reverted_at = datetime.now(UTC)
            snapshot.reverted_by = actor
            snapshot.revert_reason = reason.strip()
            run = self.session.get(ListingEvaluationRun, snapshot.run_id)
            if run is not None:
                run.published_count = max(0, run.published_count - 1)
            tasks = self.session.scalars(
                select(ListingGradeFollowUpTask)
                .where(
                    ListingGradeFollowUpTask.snapshot_id == snapshot.id,
                    ListingGradeFollowUpTask.status.in_(("pending", "in_progress")),
                )
                .with_for_update()
            ).all()
            for task in tasks:
                task.status = "canceled"
                task.resolved_at = snapshot.reverted_at
                task.resolved_by = actor
                task.resolution_note = "Publication reverted"
            self.session.commit()
            return snapshot
        except Exception:
            self.session.rollback()
            raise
