"""Read-only, source-scoped preflight for V1.1 analysis; never returns invented scores."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from .analysis_entrypoint import prepare_verified_analysis
from .analysis_execution import AnalysisBlocked


@dataclass(frozen=True)
class PreflightResult:
    can_create_review_run: bool
    can_generate_scored_results: bool
    can_generate_official_upload: bool
    candidate_count: int
    automatic_evidence_count: int
    reviewed_evidence_count: int
    manual_review_count: int
    top40_review_required: int
    review_reason_codes: tuple[str, ...]
    source_account_ref: str
    product_id: UUID
    rule_version_id: UUID


def inspect_readiness(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    item_id: str,
    fact_id: UUID,
    rule_version_id: UUID,
    upload_id: UUID,
    actor: str,
) -> PreflightResult:
    """Inspect frozen rows; no PostgreSQL write and no fallback to guessed data."""
    if not account or not actor or not item_id:
        raise ValueError("PREFLIGHT_SCOPE_REQUIRED")
    try:
        command, _, _ = prepare_verified_analysis(
            session,
            account=account,
            product_id=product_id,
            item_id=item_id,
            fact_id=fact_id,
            rule_version_id=rule_version_id,
            upload_id=upload_id,
            request_key="preflight-only",
            actor=actor,
        )
        candidates = command.candidates
        reasons = {
            "AUTOMATIC_SEMANTIC_REVIEW_NOT_APPROVED",
            "D01_D08_BUSINESS_DECISIONS_NOT_APPROVED",
        }
        # Existing entrypoint conservatively assigns no match/intent/root/market
        # scores to unreviewed uploads. An analysis may be stored as BLOCKED.
        incomplete = sum(
            item.assessment.match is None
            or item.assessment.intent is None
            or item.assessment.root is None
            or item.assessment.data is None
            for item in candidates
        )
        if incomplete:
            reasons.add("KEYWORD_SCORE_EVIDENCE_REQUIRED")
        origins = [item.assessment.classification_origin for item in candidates]
        return PreflightResult(
            can_create_review_run=True,
            can_generate_scored_results=False,
            can_generate_official_upload=False,
            candidate_count=len(candidates),
            automatic_evidence_count=origins.count("confirmed_fact"),
            reviewed_evidence_count=origins.count("reviewed_phrase"),
            manual_review_count=origins.count("manual_review"),
            top40_review_required=min(40, len(candidates)),
            review_reason_codes=tuple(sorted(reasons)),
            source_account_ref=account,
            product_id=product_id,
            rule_version_id=rule_version_id,
        )
    except AnalysisBlocked as exc:
        return PreflightResult(
            can_create_review_run=False,
            can_generate_scored_results=False,
            can_generate_official_upload=False,
            candidate_count=0,
            automatic_evidence_count=0,
            reviewed_evidence_count=0,
            manual_review_count=0,
            top40_review_required=0,
            review_reason_codes=(str(exc),),
            source_account_ref=account,
            product_id=product_id,
            rule_version_id=rule_version_id,
        )
    finally:
        # prepare_verified_analysis issues SELECTs and therefore starts an
        # implicit SQLAlchemy transaction; this endpoint never commits writes.
        session.rollback()
