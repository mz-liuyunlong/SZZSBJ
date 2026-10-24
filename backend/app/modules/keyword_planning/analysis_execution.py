"""Atomic persistence boundary for *server-reviewed* Walmart keyword analysis.

This module deliberately has no public API. The caller must be a trusted backend
ingestion/review service. It refuses to infer product facts or publish rules.

The transaction is PostgreSQL-specific: advisory-lock idempotency and 0055 FK/
immutability triggers are required. Run only after the isolated Alembic chain is
approved; never use this module against an unreviewed production database.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import (
    AiKwAnalysisRun,
    AiKwProductFactSnapshot,
    AiKwRuleSet,
    AiKwRuleVersion,
    AiKwRunAsin,
    AiKwRunFile,
    AiKwRunKeyword,
    BizKwMarketObservation,
    BizSkuAsinReference,
    DimKwTerm,
    RawKwAsinSnapshot,
    RawKwUploadFile,
    RawKwUploadRow,
    RawKwWalmartPageSnapshot,
)
from .rule_gates import (
    REQUIRED_PRODUCT_FIELDS,
    ProductConfirmation,
    ScoringProfile,
    normalize_keyword,
)
from .runtime_rules import (
    KeywordInput,
    PublishedPolicy,
    WalmartPageEvidence,
    run_published_v11,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class AnalysisBlocked(ValueError):
    """Safe, non-sensitive error code, never a platform error or raw payload."""


@dataclass(frozen=True)
class ReviewedCandidate:
    """Term and assessment created by a trusted ingestion/review workflow.

    source_row_refs MUST contain one or more stored raw_kw_upload_row UUIDs.
    Direct HTTP clients must never be allowed to populate this structure.
    """

    term_id: UUID
    assessment: KeywordInput


@dataclass(frozen=True)
class AnalysisCommand:
    source_account_ref: str
    product_id: UUID
    product_fact_snapshot_id: UUID
    rule_version_id: UUID
    item_id: str
    request_key: str
    input_sha256: str
    actor_ref: str
    engine_version: str
    parser_version: str
    normalizer_version: str
    source_total_rows: int
    candidates: tuple[ReviewedCandidate, ...]
    walmart_page_snapshot_id: UUID | None = None
    store_id: str | None = None
    asin_snapshot_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ExecutionReceipt:
    run_id: UUID
    status: str
    created: bool
    keyword_count: int


def _digest(value: object) -> str:
    """Canonical payload digest. Ingestion MUST use this exact encoding contract."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def calculate_input_sha256(
    command: AnalysisCommand,
    product: ProductConfirmation,
    policy: PublishedPolicy,
) -> str:
    """Bind request identity to all reviewed evidence; never hash request_key itself."""
    inputs = {
        "source_account_ref": command.source_account_ref,
        "product_id": str(command.product_id),
        "item_id": command.item_id,
        "product_fact_snapshot_id": str(command.product_fact_snapshot_id),
        "walmart_page_snapshot_id": str(command.walmart_page_snapshot_id)
        if command.walmart_page_snapshot_id
        else None,
        "rule_version_id": str(command.rule_version_id),
        "store_id": command.store_id,
        "asin_snapshot_ids": [str(value) for value in command.asin_snapshot_ids],
        "engine_version": command.engine_version,
        "parser_version": command.parser_version,
        "normalizer_version": command.normalizer_version,
        "source_total_rows": command.source_total_rows,
        "candidates": [asdict(row) for row in command.candidates],
        "product_confirmation": asdict(product),
        "published_policy": asdict(policy),
    }
    return _digest(inputs)


def _validate_bound_facts(fact: AiKwProductFactSnapshot, product: ProductConfirmation) -> None:
    """Client/operator claims are not proof; every verified field must match frozen DB."""
    raw = fact.facts_with_sources_json
    if not isinstance(raw, dict):
        raise AnalysisBlocked("FROZEN_FACT_DOCUMENT_INVALID")
    for name in REQUIRED_PRODUCT_FIELDS:
        db_value = raw.get(name)
        provided = product.facts.get(name)
        if not isinstance(db_value, dict) or provided is None:
            raise AnalysisBlocked("FROZEN_FACT_FIELD_MISSING")
        if (
            db_value.get("value") != provided.value
            or db_value.get("source") != provided.source
            or db_value.get("evidence_ref") != provided.evidence_ref
        ):
            raise AnalysisBlocked("FROZEN_FACT_FIELD_MISMATCH")
    risk = raw.get("risk_boundary")
    if (
        not isinstance(risk, dict)
        or risk.get("acknowledged") is not True
        or risk.get("mode") != product.risk_boundary_mode
        or product.risk_boundary_acknowledged is not True
    ):
        raise AnalysisBlocked("FROZEN_RISK_BOUNDARY_NOT_CONFIRMED")
    if _digest(raw) != fact.facts_sha256:
        raise AnalysisBlocked("FROZEN_FACT_HASH_MISMATCH")


def _validate_published_config(version: AiKwRuleVersion, policy: PublishedPolicy) -> None:
    raw = version.config_json
    if not isinstance(raw, dict) or _digest(raw) != version.config_sha256:
        raise AnalysisBlocked("RULE_VERSION_CONFIG_HASH_INVALID")
    if raw.get("limits") != asdict(policy.limits):
        raise AnalysisBlocked("RULE_VERSION_LIMITS_MISMATCH")
    for key, actual in (
        ("confirmed_brands", policy.confirmed_brands or {}),
        ("suspected_brands", policy.suspected_brands or {}),
    ):
        if not isinstance(raw.get(key), dict) or raw.get(key) != dict(actual):
            raise AnalysisBlocked("RULE_BRAND_REGISTRY_MISMATCH")
    editor = raw.get("editor_config") or {}
    try:
        expected_scoring = ScoringProfile.from_editor_config(editor)
        words = editor.get("riskWords", "")
        if not isinstance(words, str):
            raise ValueError("RULE_RISK_WORDS_INVALID")
        expected_words = tuple(
            word for line in words.splitlines() if (word := normalize_keyword(line))
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise AnalysisBlocked("RULE_EDITOR_CONFIG_INVALID") from exc
    if policy.scoring != expected_scoring or policy.review_risk_words != expected_words:
        raise AnalysisBlocked("RULE_SCORING_POLICY_MISMATCH")


def _valid_text(value: str, *, maxlen: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maxlen and value.strip() == value


def _validate(
    command: AnalysisCommand, policy: PublishedPolicy, product: ProductConfirmation
) -> None:
    for value, size in (
        (command.source_account_ref, 128),
        (command.item_id, 128),
        (command.request_key, 255),
        (command.actor_ref, 255),
        (command.engine_version, 64),
        (command.parser_version, 64),
        (command.normalizer_version, 64),
    ):
        if not _valid_text(value, maxlen=size):
            raise AnalysisBlocked("ANALYSIS_COMMAND_INVALID")
    if not isinstance(command.input_sha256, str) or not _SHA256.fullmatch(command.input_sha256):
        raise AnalysisBlocked("INPUT_HASH_INVALID")
    if (
        not command.candidates
        or type(command.source_total_rows) is not int
        or command.source_total_rows < 1
    ):
        raise AnalysisBlocked("SOURCE_ROWS_REQUIRED")
    if (
        policy.source_account_ref != command.source_account_ref
        or policy.product_id != str(command.product_id)
        or policy.version_id != str(command.rule_version_id)
    ):
        raise AnalysisBlocked("RULE_SCOPE_MISMATCH")
    if product.item_id != command.item_id:
        raise AnalysisBlocked("PRODUCT_ITEM_MISMATCH")
    if command.input_sha256 != calculate_input_sha256(command, product, policy):
        raise AnalysisBlocked("INPUT_HASH_MISMATCH")
    if command.asin_snapshot_ids != tuple(sorted(set(command.asin_snapshot_ids))):
        raise AnalysisBlocked("ASIN_SNAPSHOT_REFERENCES_INVALID")
    if any(not isinstance(item.term_id, UUID) for item in command.candidates):
        raise AnalysisBlocked("TERM_ID_INVALID")
    ids = [x.term_id for x in command.candidates]
    keys = [normalize_keyword(x.assessment.keyword) for x in command.candidates]
    if not all(keys) or len(set(ids)) != len(ids) or len(set(keys)) != len(keys):
        raise AnalysisBlocked("CANDIDATES_MUST_BE_DEDUPLICATED")
    if any(not x.assessment.source_row_refs for x in command.candidates):
        raise AnalysisBlocked("ORIGINAL_ROW_EVIDENCE_MISSING")
    if any(
        x.assessment.classification_origin
        not in ("confirmed_fact", "reviewed_phrase", "manual_review")
        for x in command.candidates
    ):
        raise AnalysisBlocked("CLASSIFICATION_ORIGIN_INVALID")


def _scoped_ref_query(model, row_id: UUID, account: str):
    return select(model).where(model.id == row_id, model.source_account_ref == account)


def _lock_key(account: str, request_key: str) -> int:
    # Signed bigint is required by pg_advisory_xact_lock(bigint).
    digest = hashlib.sha256((account + "\x00" + request_key).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _validate_persisted_sources(
    session: Session, cmd: AnalysisCommand, policy: PublishedPolicy, product: ProductConfirmation
) -> tuple[
    RawKwWalmartPageSnapshot | None,
    dict[UUID, DimKwTerm],
    tuple[UUID, ...],
    tuple[UUID, ...],
]:
    account = cmd.source_account_ref
    fact = session.scalar(
        _scoped_ref_query(AiKwProductFactSnapshot, cmd.product_fact_snapshot_id, account)
    )
    if (
        fact is None
        or fact.product_id != cmd.product_id
        or fact.item_id != cmd.item_id
        or fact.status != "confirmed"
        or fact.item_verified is not True
        or fact.confirmed_at is None
        or not fact.confirmed_by
        or not fact.facts_sha256
        or fact.missing_required_json != []
    ):
        raise AnalysisBlocked("PERSISTED_PRODUCT_FACTS_UNCONFIRMED")
    _validate_bound_facts(fact, product)

    version = session.get(AiKwRuleVersion, cmd.rule_version_id)
    if version is None or version.status not in ("published", "draft"):
        raise AnalysisBlocked("RULE_VERSION_NOT_AVAILABLE")
    if version.status == "published" and (not version.published_at or not version.published_by):
        raise AnalysisBlocked("RULE_VERSION_PUBLICATION_INVALID")
    if version.status != policy.status:
        raise AnalysisBlocked("RULE_VERSION_STATUS_MISMATCH")
    _validate_published_config(version, policy)
    ruleset = session.get(AiKwRuleSet, version.rule_set_id)
    if (
        ruleset is None
        or (version.status == "published" and not ruleset.is_enabled)
        or ruleset.rule_type != "scoring"
        or ruleset.scope_key not in ("global", account)
    ):
        raise AnalysisBlocked("RULE_SET_NOT_AUTHORIZED_FOR_ACCOUNT")

    page = None
    if cmd.walmart_page_snapshot_id is not None:
        page = session.scalar(
            _scoped_ref_query(RawKwWalmartPageSnapshot, cmd.walmart_page_snapshot_id, account)
        )
        if (
            page is None
            or page.product_id != cmd.product_id
            or page.item_id != cmd.item_id
            or page.verification_status not in ("verified", "partial")
            or (cmd.store_id is not None and page.store_id != cmd.store_id)
        ):
            raise AnalysisBlocked("PAGE_IDENTITY_UNVERIFIED")
    if (
        fact.walmart_page_snapshot_id is not None
        and fact.walmart_page_snapshot_id != cmd.walmart_page_snapshot_id
    ):
        raise AnalysisBlocked("FACT_PAGE_SNAPSHOT_MISMATCH")

    term_ids = {candidate.term_id for candidate in cmd.candidates}
    terms = dict(
        (term.id, term)
        for term in session.scalars(select(DimKwTerm).where(DimKwTerm.id.in_(term_ids)))
    )
    if set(terms) != term_ids:
        raise AnalysisBlocked("TERM_REFERENCE_NOT_FOUND")

    row_ids: set[UUID] = set()
    for candidate in cmd.candidates:
        if terms[candidate.term_id].normalized_keyword != normalize_keyword(
            candidate.assessment.keyword
        ):
            raise AnalysisBlocked("TERM_KEYWORD_MISMATCH")
        for ref in candidate.assessment.source_row_refs:
            try:
                row_ids.add(UUID(ref))
            except (ValueError, TypeError, AttributeError) as exc:
                raise AnalysisBlocked("SOURCE_ROW_REFERENCE_INVALID") from exc
    rows = list(
        session.scalars(
            select(RawKwUploadRow).where(
                RawKwUploadRow.id.in_(row_ids), RawKwUploadRow.source_account_ref == account
            )
        )
    )
    if len(rows) != len(row_ids):
        raise AnalysisBlocked("SOURCE_ROW_NOT_IN_ACCOUNT")
    uploads = {row.upload_id for row in rows}
    stored_uploads = list(
        session.scalars(
            select(RawKwUploadFile).where(
                RawKwUploadFile.id.in_(uploads),
                RawKwUploadFile.source_account_ref == account,
                RawKwUploadFile.product_id == cmd.product_id,
                RawKwUploadFile.status == "parsed",
            )
        )
    )
    if {x.id for x in stored_uploads} != uploads:
        raise AnalysisBlocked("SOURCE_UPLOAD_NOT_VERIFIED")
    row_by_id = {row.id: row for row in rows}
    for candidate in cmd.candidates:
        expected = normalize_keyword(candidate.assessment.keyword)
        if not all(
            row_by_id[UUID(ref)].keyword_normalized == expected
            for ref in candidate.assessment.source_row_refs
        ):
            raise AnalysisBlocked("SOURCE_ROW_KEYWORD_MISMATCH")
    market_references: dict[UUID, tuple[UUID, set[UUID]]] = {}
    for candidate in cmd.candidates:
        scored_refs = (
            candidate.assessment.data.observation_refs
            if candidate.assessment.data is not None
            else ()
        )
        for ref in (*candidate.assessment.market_observation_refs, *scored_refs):
            try:
                uid = UUID(ref)
            except (ValueError, TypeError, AttributeError) as exc:
                raise AnalysisBlocked("MARKET_EVIDENCE_REFERENCE_INVALID") from exc
            bound = (candidate.term_id, {UUID(row) for row in candidate.assessment.source_row_refs})
            if uid in market_references and market_references[uid] != bound:
                raise AnalysisBlocked("MARKET_EVIDENCE_TERM_CONFLICT")
            market_references[uid] = bound
    if market_references:
        observations = list(
            session.scalars(
                select(BizKwMarketObservation).where(
                    BizKwMarketObservation.id.in_(market_references),
                    BizKwMarketObservation.source_account_ref == account,
                    BizKwMarketObservation.product_id == cmd.product_id,
                )
            )
        )
        if len(observations) != len(market_references) or any(
            ob.id not in market_references
            or market_references[ob.id][0] != ob.term_id
            or ob.upload_row_id not in market_references[ob.id][1]
            for ob in observations
        ):
            raise AnalysisBlocked("MARKET_EVIDENCE_MISSING_OR_CROSS_SCOPED")
    asin_references = list(
        session.scalars(
            select(BizSkuAsinReference).where(
                BizSkuAsinReference.source_account_ref == account,
                BizSkuAsinReference.product_id == cmd.product_id,
                BizSkuAsinReference.is_active.is_(True),
                BizSkuAsinReference.latest_snapshot_id.in_(cmd.asin_snapshot_ids),
            )
        )
    )
    snapshot_ids = {ref.latest_snapshot_id for ref in asin_references if ref.latest_snapshot_id}
    if tuple(sorted(snapshot_ids)) != cmd.asin_snapshot_ids:
        raise AnalysisBlocked("ASIN_SNAPSHOT_REFERENCES_CHANGED")
    snapshots = (
        {
            snapshot.id: snapshot
            for snapshot in session.scalars(
                select(RawKwAsinSnapshot).where(
                    RawKwAsinSnapshot.source_account_ref == account,
                    RawKwAsinSnapshot.id.in_(snapshot_ids),
                )
            )
        }
        if snapshot_ids
        else {}
    )
    for ref in asin_references:
        if ref.latest_snapshot_id is None:
            continue
        snapshot = snapshots.get(ref.latest_snapshot_id)
        if snapshot is None or snapshot.asin != ref.asin:
            raise AnalysisBlocked("ASIN_SNAPSHOT_SCOPE_MISMATCH")
    return page, terms, tuple(sorted(uploads)), tuple(sorted(snapshot_ids))


def _page_evidence(
    page: RawKwWalmartPageSnapshot | None, account: str
) -> WalmartPageEvidence | None:
    if page is None:
        return None

    # Treat strings only as real text evidence; never stringify arbitrary JSON objects.
    def texts(value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(item for item in value if isinstance(item, str) and item.strip())

    attributes = page.attributes_json if isinstance(page.attributes_json, dict) else {}
    return WalmartPageEvidence(
        snapshot_id=str(page.id),
        item_id=page.item_id,
        source_account_ref=account,
        status=page.verification_status,
        title=page.page_title or "",
        features=texts(page.features_json),
        description=page.description_text or "",
        attributes=tuple(value for value in attributes.values() if isinstance(value, str)),
    )


def execute_reviewed_analysis(
    session: Session,
    *,
    command: AnalysisCommand,
    policy: PublishedPolicy,
    product: ProductConfirmation,
) -> ExecutionReceipt:
    """Persist a reviewed analysis atomically; no platform calls or export authority.

    Strong invariant: no work is written unless every uploaded-row/term/fact/rule
    reference is proved within source_account_ref, and the review passes V1.1 gates.
    The caller must supply *server-derived* product and policy data, never client JSON.
    """
    _validate(command, policy, product)
    account = command.source_account_ref
    with session.begin():
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _lock_key(account, command.request_key)},
        )
        existing = session.scalar(
            select(AiKwAnalysisRun).where(
                AiKwAnalysisRun.source_account_ref == account,
                AiKwAnalysisRun.request_key == command.request_key,
            )
        )
        if existing is not None:
            if (
                existing.input_sha256 != command.input_sha256
                or existing.product_id != command.product_id
                or existing.rule_version_id != command.rule_version_id
                or existing.item_id != command.item_id
            ):
                raise AnalysisBlocked("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT")
            return ExecutionReceipt(
                existing.id,
                existing.status,
                False,
                int((getattr(existing, "summary_json", {}) or {}).get("total", 0)),
            )

        stored_page, _terms, upload_ids, asin_snapshot_ids = _validate_persisted_sources(
            session, command, policy, product
        )
        output = run_published_v11(
            product=product,
            policy=policy,
            candidates=tuple(x.assessment for x in command.candidates),
            source_total_rows=command.source_total_rows,
            page=_page_evidence(stored_page, account),
        )
        if len(output.decisions) != len(command.candidates):
            raise AnalysisBlocked("ANALYSIS_RESULT_CARDINALITY_CHANGED")
        decisions_by_keyword = {normalize_keyword(d.keyword): d for d in output.decisions}
        candidates_by_keyword = {
            normalize_keyword(c.assessment.keyword): c for c in command.candidates
        }
        if len(decisions_by_keyword) != len(output.decisions) or set(decisions_by_keyword) != set(
            candidates_by_keyword
        ):
            raise AnalysisBlocked("ANALYSIS_RESULT_KEYWORD_MISMATCH")
        if output.official_export_authorized:
            raise AnalysisBlocked("AUTOMATIC_EXPORT_NOT_AUTHORIZED")
        now = datetime.now(UTC)
        # A partial run is persisted for review; it is not labelled fully succeeded.
        scored = sum(d.score is not None for d in output.decisions)
        review_required = sum(
            d.score is None and d.allocation_grade != "不投放" for d in output.decisions
        )
        origins = [candidate.assessment.classification_origin for candidate in command.candidates]
        status = "blocked" if review_required or policy.status != "published" else "succeeded"
        run = AiKwAnalysisRun(
            source_account_ref=account,
            product_id=command.product_id,
            item_id=command.item_id,
            store_id=command.store_id,
            product_fact_snapshot_id=command.product_fact_snapshot_id,
            walmart_page_snapshot_id=command.walmart_page_snapshot_id,
            rule_version_id=command.rule_version_id,
            status=status,
            request_key=command.request_key,
            input_sha256=command.input_sha256,
            engine_version=command.engine_version,
            parser_version=command.parser_version,
            normalizer_version=command.normalizer_version,
            requested_by=command.actor_ref,
            finished_at=now,
            started_at=now,
            error_code=(
                "KW_RULE_PENDING_APPROVAL"
                if policy.status != "published"
                else "KW_EVIDENCE_INSUFFICIENT"
                if review_required
                else None
            ),
            summary_json={
                "total": len(output.decisions),
                "scored": scored,
                "review_required": review_required,
                "automatic_evidence_count": origins.count("confirmed_fact"),
                "reviewed_evidence_count": origins.count("reviewed_phrase"),
                "manual_review_count": origins.count("manual_review"),
                "top40_checked": len(output.analyzed_top_ranks),
                "official_export_authorized": False,
            },
        )
        session.add(run)
        session.flush()
        for upload_id in upload_ids:
            session.add(AiKwRunFile(source_account_ref=account, run_id=run.id, upload_id=upload_id))
        for snapshot_id in asin_snapshot_ids:
            session.add(
                AiKwRunAsin(source_account_ref=account, run_id=run.id, asin_snapshot_id=snapshot_id)
            )
        for index, decision in enumerate(output.decisions, 1):
            candidate = candidates_by_keyword[normalize_keyword(decision.keyword)]
            evidence = decision.source
            if evidence is None or normalize_keyword(evidence.keyword) != normalize_keyword(
                candidate.assessment.keyword
            ):
                raise AnalysisBlocked("ANALYSIS_EVIDENCE_MISMATCH")
            session.add(
                AiKwRunKeyword(
                    source_account_ref=account,
                    run_id=run.id,
                    term_id=candidate.term_id,
                    keyword_primary_type=evidence.primary_type,
                    auxiliary_types_json=[label.name for label in candidate.assessment.labels],
                    core_root=evidence.core_root,
                    root_grade=evidence.root_grade,
                    page_coverage=evidence.page_coverage,
                    page_evidence_json=(
                        [{"snapshot_id": str(stored_page.id)}] if stored_page is not None else []
                    ),
                    component_evidence_json={
                        "source_row_refs": list(candidate.assessment.source_row_refs),
                        "classification_origin": candidate.assessment.classification_origin,
                        "match_evidence_ref": getattr(
                            candidate.assessment.match, "evidence_ref", None
                        ),
                        "intent_evidence_ref": getattr(
                            candidate.assessment.intent, "evidence_ref", None
                        ),
                        "root_evidence_ref": getattr(
                            candidate.assessment.root, "evidence_ref", None
                        ),
                        "market_observation_refs": list(
                            candidate.assessment.market_observation_refs
                        ),
                        "market_scoring_status": "scored"
                        if candidate.assessment.data is not None
                        else candidate.assessment.market_evidence_status,
                        "rule_version_id": str(command.rule_version_id),
                    },
                    match_points=evidence.match_points,
                    intent_points=evidence.intent_points,
                    page_points=evidence.page_points,
                    root_points=evidence.root_points,
                    data_points=evidence.data_points,
                    risk_points=evidence.risk_points,
                    score=decision.score,
                    base_grade=decision.base_grade,
                    allocation_grade=decision.allocation_grade,
                    hard_risk=bool(evidence.hard_risk_reasons),
                    risk_reasons_json=list(evidence.hard_risk_reasons),
                    exact_selected=decision.exact_selected,
                    broad_selected=decision.broad_selected,
                    broad_role=decision.broad_role if decision.broad_selected else None,
                    exact_reason=";".join(decision.reasons)
                    if not decision.exact_selected
                    else None,
                    broad_reason=";".join(decision.reasons)
                    if not decision.broad_selected
                    else None,
                    rank_index=index,
                    decision_status=(
                        "ready"
                        if policy.status == "published"
                        and decision.score is not None
                        and decision.allocation_grade in ("P0", "P1", "P2")
                        else "excluded"
                        if decision.allocation_grade == "不投放"
                        else "review"
                    ),
                )
            )
        return ExecutionReceipt(run.id, status, True, len(output.decisions))
