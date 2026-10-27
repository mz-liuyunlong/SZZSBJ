"""Idempotent, evidence-preserving batch diagnostics for Listing evaluation.

All generated snapshots are unpublished candidates. This service never mutates
mart_listing_management_current and never creates C/D follow-up work before
publication has an explicit, trusted financial-completeness contract.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.models import ListingGradeFollowUpTask
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
)
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService


class ListingEvaluationBatchService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run_daily_diagnostic(
        self,
        *,
        schedule_date_cn: date,
        cutoff_date_la: date,
        batch_size: int = 50,
    ) -> UUID:
        """Create/reuse one run per China date and persist unpublished snapshots."""
        if not 1 <= batch_size <= 200:
            raise ValueError("batch_size must be between 1 and 200")
        existing = self.session.scalar(
            select(ListingEvaluationRun).where(
                ListingEvaluationRun.schedule_date_cn == schedule_date_cn
            )
        )
        if existing is not None and existing.status in {"succeeded", "partial"}:
            return existing.id
        retry_existing = existing is not None
        if existing is None:
            latest_rule_version = self._latest_effective_rule_version()
            total = self.session.scalar(
                select(func.count()).select_from(ListingManagementCurrentMart)
            ) or 0
            run = ListingEvaluationRun(
                schedule_date_cn=schedule_date_cn,
                cutoff_date_la=cutoff_date_la,
                status="queued",
                rule_version=latest_rule_version,
                total_listings=total,
                attempt_count=1,
            )
            self.session.add(run)
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
                existing = self.session.scalar(
                    select(ListingEvaluationRun).where(
                        ListingEvaluationRun.schedule_date_cn == schedule_date_cn
                    )
                )
                if existing is None:
                    raise
                if existing.status in {"succeeded", "partial"}:
                    return existing.id
                run = existing
                retry_existing = True
        else:
            run = existing
            run.attempt_count += 1
            run.error_code = None

        if retry_existing:
            self.session.execute(
                delete(ListingEvaluationSnapshot).where(
                    ListingEvaluationSnapshot.run_id == run.id
                )
            )
            run.processed_listings = 0
            run.grade_candidate_count = 0
            run.lifecycle_candidate_count = 0
            run.blocked_count = 0
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self.session.commit()
        run_id = run.id
        try:
            self._evaluate_pages(run_id=run_id, cutoff=cutoff_date_la, batch_size=batch_size)
            self.session.refresh(run)
            run.finished_at = datetime.now(UTC)
            run.status = "partial" if run.blocked_count else "succeeded"
            self.session.commit()
        except Exception:
            self.session.rollback()
            failed = self.session.get(ListingEvaluationRun, run_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_code = "LISTING_EVALUATION_BATCH_FAILED"
                failed.finished_at = datetime.now(UTC)
                self.session.commit()
            raise
        return run_id

    def _latest_effective_rule_version(self) -> int:
        from app.modules.listing_rule_config.models import ListingGradeRuleVersion

        row = self.session.scalar(
            select(ListingGradeRuleVersion)
            .where(ListingGradeRuleVersion.effective_from <= datetime.now(UTC))
            .order_by(ListingGradeRuleVersion.version.desc())
            .limit(1)
        )
        return row.version if row else 0

    def _evaluate_pages(self, *, run_id: UUID, cutoff: date, batch_size: int) -> None:
        run = self.session.get(ListingEvaluationRun, run_id)
        if run is None:
            raise RuntimeError("Listing evaluation run disappeared")
        evaluator = ListingEvaluationPreviewService(self.session)
        offset = 0
        while True:
            listings = list(
                self.session.scalars(
                    select(ListingManagementCurrentMart)
                    .order_by(ListingManagementCurrentMart.id)
                    .offset(offset)
                    .limit(batch_size)
                ).all()
            )
            if not listings:
                break
            for listing in listings:
                result = evaluator.evaluate(
                    listing_id=listing.id,
                    account_refs=frozenset({listing.source_account_ref}),
                    cutoff=cutoff,
                )
                evidence = list(result.missing_evidence)
                # This run is deliberately diagnostic-only until upstream ad/cost
                # completeness and historical workflow contracts are approved.
                if "ADS_COST_PUBLICATION_PROOF_MISSING" not in evidence:
                    evidence.append("ADS_COST_PUBLICATION_PROOF_MISSING")
                blocked = bool(evidence)
                snapshot = ListingEvaluationSnapshot(
                    run_id=run_id,
                    listing_id=listing.id,
                    source_account_ref=listing.source_account_ref,
                    store_id=listing.store_id,
                    item_id=listing.item_id,
                    msku=listing.msku,
                    cutoff_date_la=cutoff,
                    current_lifecycle=result.current_lifecycle,
                    current_grade=result.current_grade,
                    lifecycle_candidate=result.lifecycle_candidate,
                    grade_candidate=result.grade_candidate,
                    valid_short=result.valid_short,
                    valid_medium=result.valid_medium,
                    weighted_margin_percent=result.weighted_margin_percent,
                    valid_stock_days_30=result.valid_stock_days_30,
                    observed_stock_days_7=result.observed_stock_days_7,
                    low_stock_days_7=result.low_stock_days_7,
                    prior_effective_stock=result.prior_effective_stock,
                    currently_archived=result.currently_archived,
                    rule_version=result.rule_version,
                    rule_source=result.rule_source,
                    evidence_json=evidence,
                    publication_status="blocked" if blocked else "candidate_only",
                    published=False,
                )
                self.session.add(snapshot)
                run.processed_listings += 1
                run.blocked_count += int(blocked)
                run.grade_candidate_count += int(result.grade_candidate is not None)
                run.lifecycle_candidate_count += int(result.lifecycle_candidate is not None)
            self.session.commit()
            offset += len(listings)
        run = self.session.get(ListingEvaluationRun, run_id)
        if run is not None and run.processed_listings != run.total_listings:
            run.error_code = "LISTING_COUNT_CHANGED_DURING_EVALUATION"
            run.blocked_count += abs(run.total_listings - run.processed_listings)
        self.session.commit()


    def create_followups_for_published_run(self, *, run_id: UUID) -> int:
        """Idempotently create daily C/D tasks only for explicitly published snapshots."""
        from app.modules.listing_rule_config.models import ListingEvaluationSnapshot

        today_cn = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        rows = self.session.execute(
            select(ListingEvaluationSnapshot, ListingManagementCurrentMart.owner_ref)
            .join(
                ListingManagementCurrentMart,
                ListingManagementCurrentMart.id == ListingEvaluationSnapshot.listing_id,
            )
            .where(
                ListingEvaluationSnapshot.run_id == run_id,
                ListingEvaluationSnapshot.published.is_(True),
                ListingEvaluationSnapshot.grade_candidate.in_(("C", "D")),
            )
        ).all()
        created = 0
        for snapshot, owner_ref in rows:
            existing = self.session.scalar(
                select(ListingGradeFollowUpTask.id).where(
                    ListingGradeFollowUpTask.snapshot_id == snapshot.id
                )
            )
            if existing is not None:
                continue
            self.session.add(
                ListingGradeFollowUpTask(
                    snapshot_id=snapshot.id,
                    listing_id=snapshot.listing_id,
                    source_account_ref=snapshot.source_account_ref,
                    store_id=snapshot.store_id,
                    item_id=snapshot.item_id,
                    msku=snapshot.msku,
                    grade=snapshot.grade_candidate,
                    cutoff_date_la=snapshot.cutoff_date_la,
                    due_date_cn=today_cn,
                    owner_ref=owner_ref,
                    status="pending",
                )
            )
            created += 1
        if created:
            self.session.commit()
        return created
