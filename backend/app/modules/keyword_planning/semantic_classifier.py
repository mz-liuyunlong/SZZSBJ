"""Conservative, evidence-derived V1.1 keyword assessments.

Only confirmed product fields and explicitly reviewed semantic phrases are
authority. A phrase match is token-boundary aware; an unknown phrase never
becomes a product claim or a safe advertising target.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rule_gates import KEYWORD_TYPES, ProductConfirmation, normalize_keyword
from .runtime_rules import (
    INTENT_SCORES,
    MATCH_SCORES,
    ROOT_SCORES,
    TYPE_PRIORITY,
    KeywordInput,
    PageReview,
    PublishedPolicy,
    ReviewedScore,
    VerifiedLabel,
    VerifiedRoot,
    _contains_full_brand,
    _literal_in,
    classify_brand,
)


@dataclass(frozen=True)
class ReviewedPhrase:
    """A phrase-to-product relationship confirmed outside the classifier."""

    phrase: str
    keyword_type: str
    evidence_ref: str
    hard_risk_proven: bool = False
    page_phrase: str | None = None


def parse_reviewed_phrases(value: object) -> tuple[ReviewedPhrase, ...]:
    """Reject malformed attestations instead of silently accepting a label."""
    if not isinstance(value, list) or len(value) > 500:
        return ()
    parsed: list[ReviewedPhrase] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        phrase, kind, ref = (item.get(key) for key in ("phrase", "keyword_type", "evidence_ref"))
        if (
            not all(isinstance(x, str) and x.strip() for x in (phrase, kind, ref))
            or kind not in KEYWORD_TYPES
            or len(phrase) > 200
            or len(ref) > 255
        ):
            continue
        if type(item.get("hard_risk_proven", False)) is not bool:
            continue
        page_phrase = item.get("page_phrase")
        if page_phrase is not None and (
            not isinstance(page_phrase, str) or not page_phrase.strip() or len(page_phrase) > 200
        ):
            continue
        parsed.append(
            ReviewedPhrase(
                phrase=phrase.strip(),
                keyword_type=kind,
                evidence_ref=ref.strip(),
                hard_risk_proven=item.get("hard_risk_proven", False),
                page_phrase=page_phrase.strip() if page_phrase else None,
            )
        )
    return tuple(parsed)


def _field(product: ProductConfirmation, name: str) -> tuple[str, str] | None:
    field = product.facts.get(name)
    if field is None or not field.value.strip():
        return None
    # The frozen product document is confirmed as a whole. Its hash and the
    # confirmed fact ID are checked in analysis_execution before persistence.
    return field.value.strip(), field.evidence_ref or f"confirmed-product:{name}"


def classify_from_evidence(
    *,
    keyword: str,
    source_rank: int,
    source_row_refs: tuple[str, ...],
    product: ProductConfirmation,
    policy: PublishedPolicy,
    reviewed_phrases: tuple[ReviewedPhrase, ...] = (),
    page_title: str = "",
    page_snapshot_id: str | None = None,
) -> KeywordInput:
    """Infer only relationships supported by confirmed fields or reviewed phrases.

    The output still passes through runtime_rules.build_evidence and the quota
    engine. Market scoring remains null until a versioned D04/D08 policy is
    approved; classification is useful for review without fabricating scores.
    """
    text = normalize_keyword(keyword)
    labels: list[tuple[VerifiedLabel, str]] = []
    item_type = _field(product, "item_type")
    title = _field(product, "title")
    material = _field(product, "material")
    pack = _field(product, "pack")
    size = _field(product, "size")
    use = _field(product, "use")
    item_match = bool(item_type and _literal_in(item_type[0], text))

    # Positive automatic classifications require the actual, confirmed phrase.
    if item_match and item_type:
        labels.append((VerifiedLabel("核心本体词", item_type[1]), "confirmed_fact"))
    if item_match and material and _literal_in(material[0], text):
        labels.append((VerifiedLabel("核心材质长尾词", material[1]), "confirmed_fact"))
    if item_match and pack and _literal_in(pack[0], text):
        labels.append((VerifiedLabel("核心规格/数量词", pack[1]), "confirmed_fact"))
    if item_match and size and _literal_in(size[0], text):
        labels.append((VerifiedLabel("核心规格/数量词", size[1]), "confirmed_fact"))
    if item_match and use and _literal_in(use[0], text):
        labels.append((VerifiedLabel("核心场景长尾词", use[1]), "confirmed_fact"))
    if title and normalize_keyword(title[0]) == text:
        labels.append((VerifiedLabel("精准长尾词", title[1]), "confirmed_fact"))
    for brand, ref in (policy.confirmed_brands or {}).items():
        if ref.strip() and _contains_full_brand(text, brand):
            labels.append((VerifiedLabel("品牌/竞品词", ref), "confirmed_fact"))
    page_review: PageReview | None = None
    for relation in reviewed_phrases:
        if _literal_in(relation.phrase, text):
            if relation.keyword_type == "品牌/竞品词":
                # A reviewed phrase alone cannot invent a confirmed brand.
                continue
            labels.append(
                (
                    VerifiedLabel(
                        relation.keyword_type,
                        relation.evidence_ref,
                        hard_risk_proven=relation.hard_risk_proven,
                    ),
                    "reviewed_phrase",
                )
            )
            if (
                relation.page_phrase
                and page_snapshot_id
                and _literal_in(relation.page_phrase, page_title)
            ):
                page_review = PageReview(
                    "标题意思已覆盖",
                    relation.evidence_ref,
                    matched_page_phrase=relation.page_phrase,
                )
    if not labels:
        labels.append((VerifiedLabel("人工确认词", source_row_refs[0]), "manual_review"))
    # One type may be supported by multiple distinct facts; retain the first
    # deterministic proof while keeping other types as auxiliary labels.
    unique: dict[str, tuple[VerifiedLabel, str]] = {}
    for label, origin in labels:
        unique.setdefault(label.name, (label, origin))
    primary = next(name for name in TYPE_PRIORITY if name in unique)

    match: ReviewedScore | None = None
    intent: ReviewedScore | None = None
    root: VerifiedRoot | None = None
    if item_match and item_type:
        modifier = any(
            _literal_in(value[0], text) for value in (material, pack, size, use) if value
        )
        match = ReviewedScore(
            "verified_material_spec_pack" if modifier else "exact_identity",
            item_type[1],
        )
        intent = ReviewedScore(
            "buy_with_verified_modifier" if modifier else "buy_exact_item",
            item_type[1],
        )
        root = VerifiedRoot(item_type[0], "R0", item_type[1], True)
    assert match is None or match.level in MATCH_SCORES
    assert intent is None or intent.level in INTENT_SCORES
    assert root is None or root.grade in ROOT_SCORES
    return KeywordInput(
        keyword=text,
        source_rank=source_rank,
        source_row_refs=source_row_refs,
        labels=tuple(label for label, _ in unique.values()),
        classification_origin="manual_review"
        if classify_brand(text, policy) == "suspected"
        else unique[primary][1],
        match=match,
        intent=intent,
        root=root,
        data=None,
        page_review=page_review,
        risk_penalty=0,
        exact_requested=item_match,
        broad_requested=item_match and root is not None,
        broad_role="root"
        if text == normalize_keyword(item_type[0])
        else "long_tail"
        if item_match
        else "none",
        broad_risk="unknown",  # independent Broad review is mandatory
    )
