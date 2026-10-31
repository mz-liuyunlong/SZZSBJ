"""Idempotent, evidence-preserving batch diagnostics for Listing evaluation.

All generated snapshots are unpublished candidates. This service never mutates
mart_listing_management_current and never creates C/D follow-up work before
publication has an explicit, trusted financial-completeness contract.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeFollowUpTask,
    ListingGradeRuleVersion,
)
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


class ListingEvaluationBatchService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run_daily_diagnostic(
        self,
        *,
        schedule_date_cn: date,
        cutoff_date_la: date,
        batch_size: int = 50,
        replay_succeeded: bool = False,
    ) -> UUID:
        """Preserve prior attempts; a successful day replays only when explicitly requested."""
        if not 1 <= batch_size <= 200:
            raise ValueError("batch_size must be between 1 and 200")
        existing = self.session.scalar(
            select(ListingEvaluationRun)
            .where(ListingEvaluationRun.schedule_date_cn == schedule_date_cn)
            .order_by(ListingEvaluationRun.attempt_count.desc())
            .limit(1)
        )
        if existing is not None and existing.cutoff_date_la != cutoff_date_la:
            raise ValueError("Listing evaluation cutoff is fixed for each schedule date")
        if existing is not None and (
            existing.status in {"queued", "running"}
            or (existing.status == "succeeded" and not replay_succeeded)
        ):
            return existing.id
        selected_rule = self._latest_effective_rule() if existing is None else None
        total = (
            self.session.scalar(select(func.count()).select_from(ListingManagementCurrentMart)) or 0
        )
        run = ListingEvaluationRun(
            schedule_date_cn=schedule_date_cn,
            cutoff_date_la=cutoff_date_la,
            status="queued",
            rule_version=(
                existing.rule_version
                if existing is not None
                else selected_rule.version
                if selected_rule is not None
                else 0
            ),
            total_listings=total,
            attempt_count=(existing.attempt_count + 1 if existing is not None else 1),
            last_dispatch_at=datetime.now(UTC),
        )
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ListingEvaluationRun)
                .where(ListingEvaluationRun.schedule_date_cn == schedule_date_cn)
                .order_by(ListingEvaluationRun.attempt_count.desc())
                .limit(1)
            )
            if concurrent is None or concurrent.attempt_count < run.attempt_count:
                raise
            return concurrent.id
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self.session.commit()
        run_id = run.id
        try:
            selected_rule = (
                self.session.get(ListingGradeRuleVersion, run.rule_version)
                if run.rule_version
                else None
            )
            config = (
                ListingGradeRuleConfig.model_validate(selected_rule.config_json)
                if selected_rule is not None
                else ListingGradeRuleConfig()
            )
            self._evaluate_pages(
                run_id=run_id,
                cutoff=cutoff_date_la,
                batch_size=batch_size,
                config=config,
                rule_version=run.rule_version,
            )
            self.session.refresh(run)
            run.finished_at = datetime.now(UTC)
            run.status = "succeeded" if run.processed_listings == run.total_listings else "partial"
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

    def _latest_effective_rule(self) -> ListingGradeRuleVersion | None:
        return self.session.scalar(
            select(ListingGradeRuleVersion)
            .where(ListingGradeRuleVersion.effective_from <= datetime.now(UTC))
            .order_by(ListingGradeRuleVersion.version.desc())
            .limit(1)
        )

    def _evaluate_pages(
        self,
        *,
        run_id: UUID,
        cutoff: date,
        batch_size: int,
        config: ListingGradeRuleConfig,
        rule_version: int,
    ) -> None:
        run = self.session.get(ListingEvaluationRun, run_id)
        if run is None:
            raise RuntimeError("Listing evaluation run disappeared")
        evaluator = ListingEvaluationPreviewService(self.session)
        last_id: UUID | None = None
        while True:
            statement = select(ListingManagementCurrentMart).order_by(
                ListingManagementCurrentMart.id
            )
            if last_id is not None:
                statement = statement.where(ListingManagementCurrentMart.id > last_id)
            listings = list(self.session.scalars(statement.limit(batch_size)).all())
            if not listings:
                break
            for listing in listings:
                result = evaluator.evaluate(
                    listing_id=listing.id,
                    account_refs=frozenset({listing.source_account_ref}),
                    cutoff=cutoff,
                    config=config,
                    rule_version=rule_version,
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
            last_id = listings[-1].id
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
