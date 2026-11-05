"""Fail-closed, one-shot Listing grade publisher.

A grade candidate is NEVER proof. Official grades require a per-day, upstream
financial AND advertising closure contract written by trusted reconciliation.
This module does not issue attestations, enable schedules or modify lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingArchiveState,
    ListingManagementCurrentMart,
)
from app.modules.listing_rule_config.evaluation import FinancialDay, grade_listing
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeRuleVersion,
)
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

PROOF_KEY = "listing_grade_finance_ads_closure_v1"
PROOF_ORIGIN = "trusted_finance_ads_reconciliation"


@dataclass(frozen=True)
class GradePublishOutcome:
    examined: int
    published: int
    blocked: int
    already_published: int


def _store_day_ad_spend_positive(value: Decimal | None) -> bool:
    """A full-store zero-advertising day is an incomplete source day, not a valid zero."""
    return value is not None and value > Decimal("0")


def _store_day_ad_spend_totals(
    session: Session, listing: ListingManagementCurrentMart, start, cutoff
) -> dict:
    """Only the exact account/store/LA dates; include standard and SEM advertising."""
    return {
        day: spend
        for day, spend in session.execute(
            select(
                DailySalesItemDayMart.business_date_la,
                func.sum(
                    func.coalesce(DailySalesItemDayMart.ad_spend_amount, 0)
                    + func.coalesce(DailySalesItemDayMart.sem_ad_spend_amount, 0)
                ),
            )
            .where(
                DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                DailySalesItemDayMart.store_id == listing.store_id,
                DailySalesItemDayMart.business_date_la.between(start, cutoff),
            )
            .group_by(DailySalesItemDayMart.business_date_la)
        ).all()
    }


def _day_is_attested(row: DailySalesItemDayMart) -> bool:
    """A numeric zero ad-spend is NOT evidence of source-day completeness."""
    lineage = row.source_lineage_json
    if not isinstance(lineage, dict):
        return False
    proof = lineage.get(PROOF_KEY)
    if not isinstance(proof, dict):
        return False
    token = proof.get("evidence_sha256")
    return bool(
        proof.get("origin") == PROOF_ORIGIN
        and proof.get("financial_complete") is True
        and proof.get("advertising_complete") is True
        and proof.get("zero_sales_coverage_confirmed") is True
        and isinstance(token, str)
        and len(token) == 64
        and all(c in "0123456789abcdef" for c in token)
        and row.sales_currency_code == "USD"
        and row.gross_profit_currency_code == "USD"
        and row.ad_spend_currency_code == "USD"
        and row.ad_spend_amount is not None
        and row.sem_ad_spend_amount is not None
        and row.cost_status == "complete"
        and not row.missing_cost_codes_json
        and row.gross_profit_amount is not None
    )


class ListingGradePublicationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish_run(self, *, run_id: UUID) -> GradePublishOutcome:
        """Explicit invocation only; no scheduler or implicit backfill.

        Each Listing is committed independently. A failed run stops; prior
        commits remain in immutable snapshots so retry is idempotent.
        """
        settings = get_settings()
        if not settings.listing_evaluation_publish_enabled:
            raise RuntimeError("LISTING_GRADE_PUBLICATION_NOT_ENABLED")

        run = self.session.get(ListingEvaluationRun, run_id)
        if run is None or run.status != "succeeded":
            raise ValueError("LISTING_GRADE_DIAGNOSTIC_RUN_NOT_COMPLETE")

        if run.rule_version:
            rule_row = self.session.get(ListingGradeRuleVersion, run.rule_version)
            if rule_row is None:
                raise ValueError("LISTING_GRADE_RULE_VERSION_NOT_FOUND")
            config = ListingGradeRuleConfig.model_validate(rule_row.config_json)
        else:
            config = ListingGradeRuleConfig()

        if not run.cutoff_date_la:
            raise ValueError("LISTING_GRADE_CUTOFF_REQUIRED")
        snapshot_ids = list(
            self.session.scalars(
                select(ListingEvaluationSnapshot.id)
                .where(ListingEvaluationSnapshot.run_id == run_id)
                .order_by(ListingEvaluationSnapshot.listing_id)
            )
        )
        self.session.commit()

        examined = published = blocked = already_published = 0
        for snapshot_id in snapshot_ids:
            with self.session.begin():
                snap = self.session.scalar(
                    select(ListingEvaluationSnapshot)
                    .where(ListingEvaluationSnapshot.id == snapshot_id)
                    .with_for_update()
                )
                if snap is None:
                    continue
                examined += 1
                if snap.published:
                    already_published += 1
                    continue
                listing = self.session.scalar(
                    select(ListingManagementCurrentMart)
                    .where(
                        ListingManagementCurrentMart.id == snap.listing_id,
                        ListingManagementCurrentMart.source_account_ref == snap.source_account_ref,
                        ListingManagementCurrentMart.store_id == snap.store_id,
                        ListingManagementCurrentMart.item_id == snap.item_id,
                    )
                    .with_for_update()
                )
                if listing is None:
                    blocked += 1
                    continue
                if (
                    listing.lifecycle_status not in config.included_stages
                    or listing.lifecycle_status in {"清货期", "已归档"}
                    or snap.cutoff_date_la != run.cutoff_date_la
                    or snap.rule_version != run.rule_version
                ):
                    blocked += 1
                    continue
                archived = self.session.scalar(
                    select(ListingArchiveState.is_archived).where(
                        ListingArchiveState.listing_id == listing.id
                    )
                )
                if archived:
                    blocked += 1
                    continue

                start = run.cutoff_date_la - timedelta(days=config.medium_days - 1)
                rows = list(
                    self.session.scalars(
                        select(DailySalesItemDayMart).where(
                            DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                            DailySalesItemDayMart.store_id == listing.store_id,
                            DailySalesItemDayMart.item_id == listing.item_id,
                            DailySalesItemDayMart.msku.is_not_distinct_from(listing.msku),
                            DailySalesItemDayMart.business_date_la.between(
                                start, run.cutoff_date_la
                            ),
                        )
                    )
                )
                days_seen = {row.business_date_la for row in rows}
                if len(days_seen) != len(rows):
                    blocked += 1
                    continue
                # A store-wide zero advertising day signals an upstream outage
                # in this business, even if one Listing legitimately has zero ads.
                # Exclude those days from independently confirmed financial inputs.
                store_ad_totals = _store_day_ad_spend_totals(
                    self.session, listing, start, run.cutoff_date_la
                )
                days = [
                    FinancialDay(
                        day=row.business_date_la,
                        sales=row.sales_amount if row.sales_amount is not None else Decimal("-1"),
                        profit=row.gross_profit_amount,
                        cost_status=row.cost_status,
                        missing_cost_codes=tuple(row.missing_cost_codes_json or ()),
                        upstream_confirmed=(
                            _day_is_attested(row)
                            and _store_day_ad_spend_positive(
                                store_ad_totals.get(row.business_date_la)
                            )
                        ),
                    )
                    for row in rows
                ]
                result = grade_listing(
                    cutoff=run.cutoff_date_la,
                    stage=listing.lifecycle_status,
                    days=days,
                    config=config,
                )
                # Never promote provisional candidates when the independently
                # attested financial calculation is different or insufficient.
                if result.grade not in {"A", "B", "C", "D"} or result.grade != snap.grade_candidate:
                    blocked += 1
                    continue

                # Prevent an older run from overwriting a newer publication.
                newer = self.session.scalar(
                    select(ListingEvaluationSnapshot.id)
                    .where(
                        ListingEvaluationSnapshot.listing_id == listing.id,
                        ListingEvaluationSnapshot.published.is_(True),
                        ListingEvaluationSnapshot.cutoff_date_la >= snap.cutoff_date_la,
                    )
                    .limit(1)
                )
                if newer is not None:
                    blocked += 1
                    continue

                listing.product_grade = result.grade
                snap.published = True
                snap.publication_status = "published"
                # Preserve the original diagnostic rejection evidence and
                # append immutable provenance for the later verified release.
                proof_tokens = sorted(
                    str(row.source_lineage_json[PROOF_KEY]["evidence_sha256"])
                    for row in rows
                    if _day_is_attested(row)
                )
                proof_digest = sha256("|".join(proof_tokens).encode("ascii")).hexdigest()
                snap.evidence_json = [
                    *(snap.evidence_json or []),
                    f"GRADE_PUBLISHED_FINANCE_ADS_SHA256:{proof_digest}",
                ]
                published += 1

        # The follow-up service is already idempotent and creates C/D actions
        # only for snapshots whose official publication committed successfully.
        if published:
            from app.modules.listing_rule_config.batch import ListingEvaluationBatchService

            ListingEvaluationBatchService(self.session).create_followups_for_published_run(
                run_id=run_id
            )
        return GradePublishOutcome(examined, published, blocked, already_published)
