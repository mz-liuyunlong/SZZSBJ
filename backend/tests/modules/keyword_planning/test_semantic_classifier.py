"""Synthetic evidence fixtures: no real item, account, brand or market amount."""

import pytest

from app.modules.keyword_planning.rule_gates import ProductConfirmation, ProductField
from app.modules.keyword_planning.runtime_rules import (
    TYPE_PRIORITY,
    PublishedPolicy,
    build_evidence,
    classify_type,
)
from app.modules.keyword_planning.semantic_classifier import (
    ReviewedPhrase,
    classify_from_evidence,
    parse_reviewed_phrases,
)


def _product():
    values = {
        "title": "Synthetic Silicone Spatula",
        "item_type": "spatula",
        "brand": "Invented",
        "material": "silicone",
        "color": "blue",
        "pack": "two pack",
        "size": "small",
        "structure": "solid",
        "use": "baking",
        "owner": "operator",
    }
    return ProductConfirmation(
        "synthetic-item",
        True,
        "synthetic-item",
        {
            name: ProductField(value, "operator", f"synthetic:fact:{name}")
            for name, value in values.items()
        },
        True,
        "none",
    )


def _policy():
    return PublishedPolicy("synthetic-rule", "published", "synthetic-account", "synthetic-product")


def _classify(keyword, reviewed=()):
    return classify_from_evidence(
        keyword=keyword,
        source_rank=1,
        source_row_refs=("synthetic:row",),
        product=_product(),
        policy=_policy(),
        reviewed_phrases=reviewed,
    )


@pytest.mark.parametrize("kind", TYPE_PRIORITY)
def test_each_type_requires_a_matching_verified_phrase_or_product_fact(kind):
    if kind == "人工确认词":
        result = _classify("unrelated opaque request")
        assert classify_type(result.labels)[0] == kind
        assert result.classification_origin == "manual_review"
        return
    if kind == "核心本体词":
        result = _classify("spatula")
    elif kind == "品牌/竞品词":
        result = classify_from_evidence(
            keyword="Verified Brand tool",
            source_rank=1,
            source_row_refs=("synthetic:row",),
            product=_product(),
            policy=PublishedPolicy(
                "synthetic-rule",
                "published",
                "synthetic-account",
                "synthetic-product",
                confirmed_brands={"Verified Brand": "synthetic:registry:1"},
            ),
        )
    else:
        # The fixture is an operator-reviewed relationship, not a bare enum:
        # the exact phrase must be present, and its ref must be in frozen facts.
        proof = ReviewedPhrase(
            "synthetic relation",
            kind,
            "synthetic:review:1",
            hard_risk_proven=kind
            in {
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
            },
        )
        result = _classify("synthetic relation", (proof,))
        assert classify_type(_classify("different relation", (proof,)).labels)[0] == "人工确认词"
    assert classify_type(result.labels)[0] == kind
    assert all(label.evidence_ref for label in result.labels)
    assert result.classification_origin == (
        "confirmed_fact" if kind in {"核心本体词", "品牌/竞品词"} else "reviewed_phrase"
    )


def test_confirmed_product_phrases_classify_without_review_label_injection():
    row = _classify("blue silicone spatula two pack for baking")
    assert {x.name for x in row.labels} >= {
        "核心本体词",
        "核心材质长尾词",
        "核心规格/数量词",
        "核心场景长尾词",
    }
    assert row.match is not None and row.intent is not None and row.root is not None
    assert row.data is None  # No approved market scoring/aggregation rule.
    assert row.classification_origin == "confirmed_fact"
    evidence = build_evidence(row, _policy(), None)
    assert evidence.match_points == 24
    assert evidence.intent_points == 18
    assert evidence.root_points == 15
    assert evidence.data_points is None


def test_reviewed_phrase_must_match_whole_phrase_and_have_valid_provenance():
    records = parse_reviewed_phrases(
        [
            {
                "phrase": "wrong shelf",
                "keyword_type": "错货架词",
                "evidence_ref": "synthetic:review:1",
                "hard_risk_proven": True,
            },
            {
                "phrase": "bad",
                "keyword_type": "not a V1.1 type",
                "evidence_ref": "synthetic:review:2",
            },
        ]
    )
    assert len(records) == 1
    assert classify_type(_classify("wrong shelf utensil", records).labels)[0] == "错货架词"
    assert classify_type(_classify("wrong shelving unit", records).labels)[0] == "人工确认词"


def test_confirmed_brand_is_token_bound_and_suspected_brand_stays_review():
    policy = PublishedPolicy(
        "synthetic-rule",
        "published",
        "synthetic-account",
        "synthetic-product",
        confirmed_brands={"Example Brand": "synthetic:registry:1"},
        suspected_brands={"Maybe Brand": "synthetic:registry:2"},
    )
    row = classify_from_evidence(
        keyword="Example Brand tool",
        source_rank=1,
        source_row_refs=("synthetic:row",),
        product=_product(),
        policy=policy,
    )
    assert classify_type(row.labels)[0] == "品牌/竞品词"
    assert row.classification_origin == "confirmed_fact"
    suspected = classify_from_evidence(
        keyword="Maybe Brand spatula",
        source_rank=1,
        source_row_refs=("synthetic:row",),
        product=_product(),
        policy=policy,
    )
    assert suspected.classification_origin == "manual_review"
    assert (
        classify_type(
            classify_from_evidence(
                keyword="Preexample Brand tool",
                source_rank=1,
                source_row_refs=("synthetic:row",),
                product=_product(),
                policy=policy,
            ).labels
        )[0]
        == "人工确认词"
    )
