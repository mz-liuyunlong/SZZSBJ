"""Evidence-bound Walmart keyword V1.1 run orchestrator (pure Python, no I/O).

No NLP guesses, platform calls, bid fabrication, database writes or advertising actions.
The caller MUST load a published rule version and independently verified sources.
The original raw Excel rows and snapshots must be persisted before invoking this module.
Pending policy decisions D01-D08 remain fail-closed; no official export here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from .rule_gates import (
    COVERAGE,
    KEYWORD_TYPES,
    PAGE_POINTS,
    ColdStartLimits,
    KeywordDecision,
    KeywordEvidence,
    ProductConfirmation,
    ScoringProfile,
    allocate_ads,
    normalize_keyword,
    product_confirmation_errors,
)

# Explicit, reviewed assessments from V1 §15. These values are not inferred from a title.
MATCH_SCORES: Mapping[str, int] = {
    "exact_identity": 30,
    "verified_synonym": 26,
    "verified_material_spec_pack": 24,
    "verified_use_scene": 22,
    "secondary_scene": 18,
    "operator_verified_test": 16,
    "broad_category": 10,
    "weak_product_relation": 5,
}
INTENT_SCORES: Mapping[str, int] = {
    "buy_exact_item": 20,
    "buy_with_verified_modifier": 18,
    "buy_category": 16,
    "use_scene": 14,
    "secondary_use_scene": 12,
    "generic_demand": 8,
    "informational": 4,
}
ROOT_SCORES: Mapping[str, int] = {
    "R0": 15,
    "R1": 12,
    "R2": 10,
    "secondary": 7,
    "generic": 3,
}

# Source V1 §13.2. Position is the primary-type selection priority.
TYPE_PRIORITY = (
    "合规/认证风险词",
    "错货架词",
    "配件/替换词",
    "结构冲突词",
    "材质不符词",
    "规格/尺寸不符词",
    "Pack/数量不符词",
    "颜色/款式不符词",
    "品牌/竞品词",
    "机器设备词",
    "食材本身词",
    "泛流量词",
    "核心本体词",
    "核心材质长尾词",
    "核心规格/数量词",
    "核心场景长尾词",
    "精准长尾词",
    "同义表达词",
    "复数变体词",
    "拼写变体词",
    "相邻结构词",
    "相邻用途词",
    "次级场景词",
    "低价值重复词",
    "人工确认词",
)
assert set(TYPE_PRIORITY) == set(KEYWORD_TYPES)

# These are *candidate* high-risk types; a proof is required for hard-risk classification.
REVIEW_TYPES = frozenset(
    {
        "合规/认证风险词",
        "错货架词",
        "配件/替换词",
        "结构冲突词",
        "材质不符词",
        "规格/尺寸不符词",
        "Pack/数量不符词",
        "颜色/款式不符词",
        "机器设备词",
        "食材本身词",
    }
)


@dataclass(frozen=True)
class VerifiedLabel:
    name: str
    evidence_ref: str
    # A label can be known as a candidate without concluding there is a hard mismatch.
    hard_risk_proven: bool = False


@dataclass(frozen=True)
class ReviewedScore:
    """Operator/approved-engine judgment, tied to an immutable evidence source."""

    level: str
    evidence_ref: str


@dataclass(frozen=True)
class MarketPoints:
    """Only an upstream approved comparison strategy can assign 0..15 data points."""

    value: int
    observation_refs: tuple[str, ...]
    aggregation_rule_version: str
    # No cross-period or cross-platform 'max' aggregation is allowed here.
    comparable: bool


@dataclass(frozen=True)
class VerifiedRoot:
    canonical: str
    grade: str
    evidence_ref: str
    # True only after product-semantic verification. Never take the first two words.
    semantically_verified: bool


@dataclass(frozen=True)
class WalmartPageEvidence:
    snapshot_id: str
    item_id: str
    source_account_ref: str
    status: Literal["verified", "partial", "failed", "mismatch"]
    title: str = ""
    features: tuple[str, ...] = ()
    description: str = ""
    attributes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageReview:
    """Human review is allowed for non-literal coverage only, with provenance."""

    coverage: str
    evidence_ref: str
    matched_page_phrase: str | None = None


@dataclass(frozen=True)
class KeywordInput:
    keyword: str
    # Rank from an authenticated source sheet, not a generated output rank.
    source_rank: int | None
    source_row_refs: tuple[str, ...]
    labels: tuple[VerifiedLabel, ...]
    match: ReviewedScore | None
    intent: ReviewedScore | None
    root: VerifiedRoot | None
    data: MarketPoints | None
    market_observation_refs: tuple[str, ...] = ()
    market_evidence_status: Literal[
        "source_missing", "source_invalid", "multiple_observations_review", "formula_pending"
    ] = "source_missing"
    classification_origin: Literal["confirmed_fact", "reviewed_phrase", "manual_review"] = (
        "manual_review"
    )
    page_review: PageReview | None = None
    hard_risk_codes: tuple[str, ...] = ()
    hard_risk_evidence_refs: tuple[str, ...] = ()
    risk_penalty: int = 0
    risk_penalty_evidence_ref: str | None = None
    exact_requested: bool = False
    broad_requested: bool = False
    broad_role: Literal["root", "long_tail", "none"] = "none"
    broad_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    is_standard_expression: bool = True
    is_correct_spelling: bool = True
    is_low_value_duplicate: bool = False


@dataclass(frozen=True)
class PublishedPolicy:
    version_id: str
    status: Literal["draft", "published", "retired"]
    source_account_ref: str
    product_id: str
    limits: ColdStartLimits = ColdStartLimits()
    scoring: ScoringProfile = ScoringProfile()
    # Registry requires external confirmation records; full token match, not substrings.
    confirmed_brands: Mapping[str, str] | None = None
    suspected_brands: Mapping[str, str] | None = None
    review_risk_words: tuple[str, ...] = ()
    data_missing_strategy: Literal["null_review", "legacy_unknown_two"] = "null_review"
    d04_evidence_ref: str | None = None


@dataclass(frozen=True)
class EvaluatedRun:
    version_id: str
    decisions: tuple[KeywordDecision, ...]
    analyzed_top_ranks: tuple[int, ...]
    # This run is analysis-only. It NEVER confers permission to upload or create ads.
    official_export_authorized: bool = False


def _nonblank(ref: str | None) -> bool:
    return isinstance(ref, str) and bool(ref.strip())


def _contains_full_brand(keyword: str, brand: str) -> bool:
    """Match whole alphanumeric tokens, including multi-word brand names."""
    parts = re.findall(r"[a-z0-9]+", brand.casefold())
    if not parts:
        return False
    words = re.findall(r"[a-z0-9]+", keyword.casefold())
    width = len(parts)
    return any(words[i : i + width] == parts for i in range(len(words) - width + 1))


def classify_brand(
    keyword: str,
    policy: PublishedPolicy,
) -> Literal["none", "confirmed", "suspected"]:
    for name, ref in (policy.confirmed_brands or {}).items():
        if _nonblank(ref) and _contains_full_brand(keyword, name):
            return "confirmed"
    for name, ref in (policy.suspected_brands or {}).items():
        if _nonblank(ref) and _contains_full_brand(keyword, name):
            return "suspected"
    return "none"


def classify_type(labels: tuple[VerifiedLabel, ...]) -> tuple[str | None, tuple[str, ...]]:
    """Choose one of 25 types from attested multi-label input; do not hallucinate tags."""
    allowed = {item.name for item in labels if _nonblank(item.evidence_ref)}
    if any(item.name not in KEYWORD_TYPES for item in labels):
        return None, ("UNKNOWN_KEYWORD_TYPE",)
    if len(allowed) != len({item.name for item in labels}):
        return None, ("TYPE_PROOF_MISSING",)
    if not allowed:
        return None, ("TYPE_NOT_EVIDENCED",)
    return next(t for t in TYPE_PRIORITY if t in allowed), ()


def _literal_in(keyword: str, text: str) -> bool:
    """Casefolded exact phrase with word boundaries; no stemming or synonym guessing."""
    value = normalize_keyword(keyword)
    text = normalize_keyword(text)
    if not value or not text:
        return False
    pattern = r"(?<!\w)" + re.escape(value).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text) is not None


def page_coverage_for(
    keyword: str,
    page: WalmartPageEvidence | None,
    review: PageReview | None,
) -> tuple[str | None, str | None, bool, tuple[str, ...]]:
    if (
        page is None
        or page.status not in ("verified", "partial")
        or not _nonblank(page.snapshot_id)
    ):
        return None, None, False, ("PAGE_EVIDENCE_MISSING",)
    if review is not None and review.coverage == "页面不建议埋" and _nonblank(review.evidence_ref):
        # An explicit, evidenced negative fit assessment outranks literal text coverage.
        return "页面不建议埋", review.evidence_ref, True, ()
    if _literal_in(keyword, page.title):
        return "标题已埋词", f"{page.snapshot_id}:title", True, ()
    sections = (("feature", x) for x in page.features)
    sections = (
        list(sections)
        + [("description", page.description)]
        + [("attribute", x) for x in page.attributes]
    )
    for index, (kind, value) in enumerate(sections):
        if _literal_in(keyword, value):
            return "详情/属性已埋词", f"{page.snapshot_id}:{kind}:{index}", True, ()
    if review is None:
        return "页面看不出来", None, True, ()
    if review.coverage not in COVERAGE or not _nonblank(review.evidence_ref):
        return None, None, False, ("PAGE_REVIEW_UNVERIFIED",)
    if (
        review.coverage == "标题意思已覆盖"
        and _nonblank(review.matched_page_phrase)
        and _literal_in(review.matched_page_phrase or "", page.title)
    ):
        # The relation must be reviewed separately; this proves only the
        # page-side phrase. Product facts cannot stand in for page text.
        return review.coverage, f"{page.snapshot_id}:title:{review.evidence_ref}", True, ()
    # A manual assertion cannot claim actual title/feature placement.
    if review.coverage in ("标题已埋词", "标题意思已覆盖", "详情/属性已埋词"):
        return None, None, False, ("PAGE_TEXT_CLAIM_NOT_EVIDENCED",)
    return review.coverage, review.evidence_ref, True, ()


def _score_or_none(value: ReviewedScore | None, scale: Mapping[str, int]) -> int | None:
    if value is None or not _nonblank(value.evidence_ref):
        return None
    return scale.get(value.level)


def _market_or_none(value: MarketPoints | None, rule_version: str) -> int | None:
    if value is None or not value.comparable or not _nonblank(value.aggregation_rule_version):
        return None
    if value.aggregation_rule_version != rule_version:
        return None
    if not value.observation_refs or not all(_nonblank(x) for x in value.observation_refs):
        return None
    if type(value.value) is not int or not 0 <= value.value <= 15:
        return None
    return value.value


def market_points_for(value: MarketPoints | None, policy: PublishedPolicy) -> int | None:
    """D04 alternatives are executable only with independent published evidence."""
    observed = _market_or_none(value, policy.version_id)
    if observed is not None:
        return observed
    if (
        policy.status == "published"
        and policy.data_missing_strategy == "legacy_unknown_two"
        and _nonblank(policy.d04_evidence_ref)
    ):
        return 2
    return None


def build_evidence(
    row: KeywordInput,
    policy: PublishedPolicy,
    page: WalmartPageEvidence | None,
) -> KeywordEvidence:
    primary, type_errors = classify_type(row.labels)
    brand_status = classify_brand(row.keyword, policy)
    if primary == "品牌/竞品词" and brand_status != "confirmed":
        primary = "人工确认词"  # User or NLP text alone cannot verify a brand.
    if brand_status == "suspected":
        primary = "人工确认词"
    root = row.root
    root_proven = bool(
        root
        and root.semantically_verified
        and _nonblank(root.evidence_ref)
        and _nonblank(root.canonical)
        and root.grade in ROOT_SCORES
    )
    if not root_proven:
        root = None
    page_label, page_ref, verified, page_errors = page_coverage_for(
        row.keyword, page, row.page_review
    )
    hard_reasons = list(row.hard_risk_codes)
    # A risk label is not proof of a mismatch. Missing proof requires review instead.
    risk_labels = [x for x in row.labels if x.name in REVIEW_TYPES]
    for label in risk_labels:
        if label.hard_risk_proven and _nonblank(label.evidence_ref):
            hard_reasons.append("HARD_TYPE:" + label.name)
        else:
            type_errors += ("RISK_TYPE_REQUIRES_REVIEW",)
    if hard_reasons and (
        len(row.hard_risk_evidence_refs) < len(row.hard_risk_codes)
        or not all(_nonblank(ref) for ref in row.hard_risk_evidence_refs)
    ):
        # Unproven allegations cannot be presented as established risk; still block.
        type_errors += ("HARD_RISK_PROOF_MISSING",)
        hard_reasons = ["RISK_REVIEW_REQUIRED"]
    if type_errors or page_errors:
        primary = "人工确认词"
    if not row.source_row_refs or not all(_nonblank(ref) for ref in row.source_row_refs):
        primary = "人工确认词"
    risk_points = (
        row.risk_penalty
        if (
            type(row.risk_penalty) is int
            and -40 <= row.risk_penalty <= 0
            and (row.risk_penalty == 0 or _nonblank(row.risk_penalty_evidence_ref))
        )
        else None
    )
    return KeywordEvidence(
        keyword=row.keyword,
        primary_type=primary,
        core_root=root.canonical if root else None,
        root_grade=root.grade if root else None,
        page_coverage=page_label,
        page_snapshot_verified=verified,
        page_evidence_ref=page_ref,
        match_points=_score_or_none(row.match, MATCH_SCORES),
        intent_points=_score_or_none(row.intent, INTENT_SCORES),
        page_points=PAGE_POINTS.get(page_label) if page_label else None,
        root_points=ROOT_SCORES.get(root.grade) if root else None,
        data_points=market_points_for(row.data, policy),
        risk_points=risk_points,
        hard_risk_reasons=tuple(hard_reasons),
        brand_status=brand_status,
        exact_eligible=row.exact_requested and not type_errors and not page_errors,
        broad_eligible=row.broad_requested and root_proven and not type_errors and not page_errors,
        broad_role=row.broad_role if root_proven else "none",
        broad_risk=row.broad_risk,
        is_standard_expression=row.is_standard_expression,
        is_correct_spelling=row.is_correct_spelling,
        is_low_value_duplicate=row.is_low_value_duplicate,
    )


def run_published_v11(
    *,
    product: ProductConfirmation,
    policy: PublishedPolicy,
    candidates: tuple[KeywordInput, ...],
    source_total_rows: int,
    page: WalmartPageEvidence | None,
) -> EvaluatedRun:
    """Analyze an already-persisted source batch, with strict Top40 coverage checks.

    Caller must verify account scope, load the published policy from DB, and save
    immutable raw rows before invocation. Results are analysis-only, never upload-ready.
    """
    if policy.status not in ("published", "draft") or not all(
        (policy.version_id.strip(), policy.source_account_ref.strip(), policy.product_id.strip())
    ):
        raise ValueError("RULE_VERSION_NOT_PUBLISHED_OR_UNSCOPED")
    failures = product_confirmation_errors(product)
    if failures:
        raise ValueError("PRODUCT_NOT_CONFIRMED:" + ",".join(failures))
    policy.limits.validate()
    if type(source_total_rows) is not int or source_total_rows <= 0:
        raise ValueError("SOURCE_TOTAL_INVALID")
    if not candidates:
        raise ValueError("NO_SOURCE_KEYWORDS")
    ranks = [x.source_rank for x in candidates if x.source_rank is not None]
    if any(type(x) is not int or x <= 0 or x > source_total_rows for x in ranks):
        raise ValueError("SOURCE_RANK_INVALID")
    if len(set(ranks)) != len(ranks):
        # Identical raw rows must be preserved upstream and reconciled without guessing.
        raise ValueError("SOURCE_RANK_DUPLICATE_REVIEW_REQUIRED")
    needed = set(range(1, min(40, source_total_rows) + 1))
    if not needed.issubset(ranks):
        raise ValueError(
            "TOP40_NOT_FULLY_REVIEWED:" + ",".join(str(x) for x in sorted(needed - set(ranks)))
        )
    if page is not None and (
        page.item_id != product.item_id or page.source_account_ref != policy.source_account_ref
    ):
        raise ValueError("PAGE_SNAPSHOT_IDENTITY_OR_ACCOUNT_MISMATCH")
    evidence = tuple(build_evidence(x, policy, page) for x in candidates)
    decisions = allocate_ads(evidence, policy.limits, policy.scoring)
    if policy.status != "published":
        # Draft calculations are visible for review but cannot create an
        # executable Exact/Broad target or official output.
        decisions = tuple(
            replace(
                decision,
                exact_selected=False,
                broad_selected=False,
                broad_role="none",
                reasons=decision.reasons + ("RULE_PENDING_APPROVAL",),
            )
            for decision in decisions
        )
    return EvaluatedRun(policy.version_id, decisions, tuple(sorted(needed)))
