"""DB-derived V1.1 analysis entry point (no client-invented scores or facts).

The POST API accepts only frozen source identifiers. It can produce a BLOCKED
review batch when evidence-backed match/intent/root/data scores are unavailable.
That is intentional: D01-D08 are not approved and market scoring is gated.
This module does not call external APIs or create Walmart ads.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis_execution import (
    AnalysisBlocked,
    AnalysisCommand,
    ExecutionReceipt,
    ReviewedCandidate,
    calculate_input_sha256,
    execute_reviewed_analysis,
)
from .models import (
    AiKwProductFactSnapshot,
    AiKwRuleDecision,
    AiKwRuleVersion,
    BizSkuAsinReference,
    DimKwTerm,
    RawKwUploadFile,
    RawKwUploadRow,
    RawKwWalmartPageSnapshot,
)
from .rule_gates import (
    ALGORITHM_VERSION,
    NORMALIZER_VERSION,
    ColdStartLimits,
    ProductConfirmation,
    ProductField,
    normalize_keyword,
)
from .runtime_rules import PublishedPolicy
from .semantic_classifier import classify_from_evidence, parse_reviewed_phrases

MAX_SOURCE_ROWS = 5000


def prepare_verified_analysis(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    item_id: str,
    fact_id: UUID,
    rule_version_id: UUID,
    upload_id: UUID,
    request_key: str,
    actor: str,
    selected_asins: tuple[str, ...] | None = None,
) -> tuple[AnalysisCommand, ProductConfirmation, PublishedPolicy]:
    """Prepare server-owned assessments; source rows are never deduplicated in DB.

    The conservative classifier can prove literal product relationships and
    reviewed phrases. Ambiguous terms and unapproved market scoring stay null.
    """
    fact = session.scalar(
        select(AiKwProductFactSnapshot).where(
            AiKwProductFactSnapshot.id == fact_id,
            AiKwProductFactSnapshot.product_id == product_id,
            AiKwProductFactSnapshot.source_account_ref == account,
        )
    )
    if (
        fact is None
        or fact.status != "confirmed"
        or fact.item_verified is not True
        or fact.item_id != item_id
        or not fact.facts_sha256
    ):
        raise AnalysisBlocked("PRODUCT_FACT_NOT_VERIFIED")
    if fact.walmart_page_snapshot_id is None:
        raise AnalysisBlocked("VERIFIED_WALMART_PAGE_REQUIRED")
    page = session.scalar(
        select(RawKwWalmartPageSnapshot).where(
            RawKwWalmartPageSnapshot.id == fact.walmart_page_snapshot_id,
            RawKwWalmartPageSnapshot.source_account_ref == account,
            RawKwWalmartPageSnapshot.product_id == product_id,
        )
    )
    if page is None or page.verification_status != "verified" or page.item_id != item_id:
        raise AnalysisBlocked("VERIFIED_WALMART_PAGE_REQUIRED")
    source_fields = fact.facts_with_sources_json
    if not isinstance(source_fields, dict):
        raise AnalysisBlocked("FROZEN_FACT_DOCUMENT_INVALID")
    try:
        fields = {
            name: ProductField(**value)
            for name, value in source_fields.items()
            if name != "risk_boundary" and isinstance(value, dict)
        }
        risk = source_fields["risk_boundary"]
        product = ProductConfirmation(
            item_id=item_id,
            source_item_id=page.item_id,
            item_verified=True,
            facts=fields,
            risk_boundary_mode=risk["mode"],
            risk_boundary_acknowledged=risk["acknowledged"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisBlocked("FROZEN_FACT_DOCUMENT_INVALID") from exc

    version = session.get(AiKwRuleVersion, rule_version_id)
    if version is None or version.status not in ("published", "draft"):
        raise AnalysisBlocked("RULE_VERSION_NOT_AVAILABLE")
    cfg = version.config_json
    if not isinstance(cfg, dict):
        raise AnalysisBlocked("RULE_CONFIGURATION_INVALID")
    try:
        limits = ColdStartLimits(**cfg["limits"])
        limits.validate()
        confirmed_brands = cfg["confirmed_brands"]
        suspected_brands = cfg["suspected_brands"]
        if not isinstance(confirmed_brands, dict) or not isinstance(suspected_brands, dict):
            raise ValueError("brand registry is not a map")
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisBlocked("RULE_CONFIGURATION_INVALID") from exc
    d04 = (
        session.scalar(
            select(AiKwRuleDecision).where(
                AiKwRuleDecision.rule_version_id == rule_version_id,
                AiKwRuleDecision.decision_key == "D04",
                AiKwRuleDecision.status == "approved",
                AiKwRuleDecision.config_sha256 == version.config_sha256,
            )
        )
        if version.status == "published"
        else None
    )
    d04_strategy = d04.decision_json.get("strategy") if d04 else "null_review"
    if d04_strategy not in ("null_review", "legacy_unknown_two"):
        raise AnalysisBlocked("D04_APPROVED_STRATEGY_INVALID")
    policy = PublishedPolicy(
        version_id=str(rule_version_id),
        status=version.status,
        source_account_ref=account,
        product_id=str(product_id),
        limits=limits,
        confirmed_brands=confirmed_brands,
        suspected_brands=suspected_brands,
        data_missing_strategy=d04_strategy,
        d04_evidence_ref=f"rule-decision:{d04.id}" if d04 else None,
    )

    upload = session.scalar(
        select(RawKwUploadFile).where(
            RawKwUploadFile.id == upload_id,
            RawKwUploadFile.product_id == product_id,
            RawKwUploadFile.source_account_ref == account,
            RawKwUploadFile.status == "parsed",
        )
    )
    if (
        upload is None
        or upload.status != "parsed"
        or upload.product_id != product_id
        or upload.source_account_ref != account
    ):
        raise AnalysisBlocked("VERIFIED_UPLOAD_REQUIRED")
    rows = list(
        session.scalars(
            select(RawKwUploadRow)
            .where(
                RawKwUploadRow.upload_id == upload_id,
                RawKwUploadRow.source_account_ref == account,
            )
            .order_by(RawKwUploadRow.sheet_name.asc(), RawKwUploadRow.row_number.asc())
        )
    )
    if not rows or len(rows) > MAX_SOURCE_ROWS:
        raise AnalysisBlocked("SOURCE_ROW_COUNT_OUT_OF_RANGE")
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    for row in rows:
        if row.parse_errors in (["HEADER_ROW"], ["NON_KEYWORD_SHEET"]):
            continue
        normalized = normalize_keyword(row.keyword_raw or "")
        if (
            not normalized
            or row.keyword_normalized != normalized
            or not isinstance(row.parse_errors, list)
            or row.parse_errors
        ):
            raise AnalysisBlocked("SOURCE_ROW_REQUIRES_REVIEW")
        grouped.setdefault(normalized, []).append(str(row.id))
    if not grouped:
        raise AnalysisBlocked("NO_ANALYZABLE_KEYWORDS")
    if len(grouped) > MAX_SOURCE_ROWS:
        raise AnalysisBlocked("CANDIDATE_COUNT_OUT_OF_RANGE")
    terms = list(
        session.scalars(
            select(DimKwTerm).where(
                DimKwTerm.normalized_keyword.in_(grouped),
            )
        )
    )
    by_keyword = {row.normalized_keyword: row for row in terms}
    if set(grouped) != set(by_keyword):
        # This factory never inserts unknown vocabulary on its own.
        raise AnalysisBlocked("STORED_TERM_MISSING")
    reviewed_phrases = parse_reviewed_phrases(source_fields.get("semantic_phrases", []))
    candidates = tuple(
        ReviewedCandidate(
            term_id=by_keyword[normalized].id,
            assessment=classify_from_evidence(
                keyword=normalized,
                source_rank=i,
                source_row_refs=tuple(refs),
                product=product,
                policy=policy,
                reviewed_phrases=reviewed_phrases,
                page_title=getattr(page, "page_title", None) or "",
                page_snapshot_id=str(page.id),
            ),
        )
        for i, (normalized, refs) in enumerate(grouped.items(), 1)
    )
    if selected_asins is not None and (
        not 1 <= len(selected_asins) <= 20
        or len(set(selected_asins)) != len(selected_asins)
        or any(re.fullmatch(r"[A-Z0-9]{10}", asin) is None for asin in selected_asins)
    ):
        raise AnalysisBlocked("SELECTED_ASIN_LIST_INVALID")
    asin_query = select(BizSkuAsinReference).where(
        BizSkuAsinReference.source_account_ref == account,
        BizSkuAsinReference.product_id == product_id,
        BizSkuAsinReference.is_active.is_(True),
        BizSkuAsinReference.latest_snapshot_id.is_not(None),
    )
    if selected_asins is not None:
        asin_query = asin_query.where(BizSkuAsinReference.asin.in_(selected_asins))
    references = list(session.scalars(asin_query))
    if selected_asins is not None and {ref.asin for ref in references} != set(selected_asins):
        raise AnalysisBlocked("SELECTED_ASIN_SNAPSHOT_MISSING")
    asin_snapshot_ids = tuple(sorted({ref.latest_snapshot_id for ref in references}))
    command = AnalysisCommand(
        source_account_ref=account,
        product_id=product_id,
        product_fact_snapshot_id=fact_id,
        rule_version_id=rule_version_id,
        item_id=item_id,
        request_key=request_key,
        input_sha256="0" * 64,
        actor_ref=actor,
        engine_version=ALGORITHM_VERSION,
        parser_version=upload.parser_version or "unversioned_parser",
        normalizer_version=NORMALIZER_VERSION,
        source_total_rows=len(grouped),
        candidates=candidates,
        walmart_page_snapshot_id=page.id,
        store_id=page.store_id,
        asin_snapshot_ids=asin_snapshot_ids,
    )
    return (
        replace(command, input_sha256=calculate_input_sha256(command, product, policy)),
        product,
        policy,
    )


def create_analysis_from_stored_sources(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    item_id: str,
    fact_id: UUID,
    rule_version_id: UUID,
    upload_id: UUID,
    request_key: str,
    actor: str,
    selected_asins: tuple[str, ...] | None = None,
) -> ExecutionReceipt:
    """Read frozen records, close implicit SELECT transaction, then write atomically.

    This endpoint must receive a *dedicated* SQLAlchemy request Session with no
    other pending writes. execute_reviewed_analysis independently revalidates its
    reference rows under the new transaction, and acquires the request advisory lock.
    """
    if session.new or session.dirty or session.deleted:
        raise AnalysisBlocked("SESSION_HAS_PENDING_WRITES")
    try:
        command, product, policy = prepare_verified_analysis(
            session,
            account=account,
            product_id=product_id,
            item_id=item_id,
            fact_id=fact_id,
            rule_version_id=rule_version_id,
            upload_id=upload_id,
            request_key=request_key,
            actor=actor,
            selected_asins=selected_asins,
        )
    finally:
        # SQLAlchemy 2.0 SELECT starts an implicit transaction. No side-effects here.
        session.rollback()
    return execute_reviewed_analysis(session, command=command, product=product, policy=policy)
