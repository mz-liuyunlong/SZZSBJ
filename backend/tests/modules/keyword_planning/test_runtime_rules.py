"""V1.1 evidence-backed run gate regression suite; no database or platform access."""

from dataclasses import replace

import pytest

from app.modules.keyword_planning.rule_gates import ProductConfirmation, ProductField
from app.modules.keyword_planning.runtime_rules import (
    TYPE_PRIORITY,
    KeywordInput,
    MarketPoints,
    PageReview,
    PublishedPolicy,
    ReviewedScore,
    VerifiedLabel,
    VerifiedRoot,
    WalmartPageEvidence,
    build_evidence,
    classify_brand,
    classify_type,
    market_points_for,
    page_coverage_for,
    run_published_v11,
)


def product():
    fields = (
        "title",
        "item_type",
        "brand",
        "material",
        "color",
        "pack",
        "size",
        "structure",
        "use",
        "owner",
    )
    return ProductConfirmation(
        "123",
        True,
        "123",
        {x: ProductField("Verified " + x, "operator") for x in fields},
        True,
        "none",
    )


def policy(**kwargs):
    return replace(PublishedPolicy("rules:v3", "published", "store:1", "product:1"), **kwargs)


def row(keyword="drawer organizer", rank=1, **kwargs):
    result = KeywordInput(
        keyword=keyword,
        source_rank=rank,
        source_row_refs=(f"raw:1:{rank}",),
        labels=(VerifiedLabel("核心本体词", "product:material"),),
        match=ReviewedScore("exact_identity", "product:identity"),
        intent=ReviewedScore("buy_exact_item", "review:purchase"),
        root=VerifiedRoot("drawer organizer", "R0", "review:root", True),
        data=MarketPoints(15, ("raw:obs:1",), "rules:v3", True),
        exact_requested=True,
        broad_requested=True,
        broad_role="long_tail",
        broad_risk="low",
    )
    return replace(result, **kwargs)


PAGE = WalmartPageEvidence(
    "page:1", "123", "store:1", "verified", title="Drawer Organizer for Kitchen"
)


def test_d04_missing_data_strategies_are_versioned_and_unapproved_never_score():
    assert market_points_for(None, policy()) is None
    assert market_points_for(None, policy(data_missing_strategy="legacy_unknown_two")) is None
    assert (
        market_points_for(
            None,
            policy(
                data_missing_strategy="legacy_unknown_two", d04_evidence_ref="decision:synthetic"
            ),
        )
        == 2
    )
    assert (
        market_points_for(
            None,
            policy(
                status="draft",
                data_missing_strategy="legacy_unknown_two",
                d04_evidence_ref="decision:synthetic",
            ),
        )
        is None
    )
    assert (
        market_points_for(MarketPoints(11, ("observation:synthetic",), "rules:v3", True), policy())
        == 11
    )


def test_run_produces_ad_decision_only_for_verified_evidence():
    run = run_published_v11(
        product=product(), policy=policy(), candidates=(row(),), source_total_rows=1, page=PAGE
    )
    assert len(run.decisions) == 1
    assert run.decisions[0].score == 100
    assert run.decisions[0].allocation_grade == "P0"
    assert run.decisions[0].exact_selected
    assert run.decisions[0].broad_selected
    assert run.official_export_authorized is False


def test_top40_cannot_be_skipped_even_when_missing_keyword_ranks_are_risky():
    with pytest.raises(ValueError, match="TOP40_NOT_FULLY_REVIEWED"):
        run_published_v11(
            product=product(),
            policy=policy(),
            candidates=(row(rank=1),),
            source_total_rows=40,
            page=PAGE,
        )


def test_full_top40_can_be_scored_without_changing_raw_order():
    src = tuple(
        row(f"drawer organizer {i:02d}", rank=i, broad_requested=False, exact_requested=False)
        for i in range(1, 41)
    )
    run = run_published_v11(
        product=product(), policy=policy(), candidates=src, source_total_rows=40, page=PAGE
    )
    assert len(run.decisions) == 40
    assert run.analyzed_top_ranks == tuple(range(1, 41))
    assert not any(x.exact_selected or x.broad_selected for x in run.decisions)


def test_all_25_types_have_deterministic_priority_but_require_proof():
    assert len(TYPE_PRIORITY) == 25
    assert (
        classify_type((VerifiedLabel("核心本体词", "p1"), VerifiedLabel("材质不符词", "p2")))[0]
        == "材质不符词"
    )
    assert classify_type((VerifiedLabel("核心本体词", ""),))[0] is None


@pytest.mark.parametrize("keyword_type", TYPE_PRIORITY)
def test_each_of_25_evidence_labels_has_a_distinct_primary_contract(keyword_type):
    # This validates the allowlist and priority gate, not an unapproved NLP classifier.
    primary, errors = classify_type((VerifiedLabel(keyword_type, "synthetic:review"),))
    assert primary == keyword_type
    assert errors == ()


@pytest.mark.parametrize(
    "coverage",
    (
        "场景/用途能接住",
        "用户确认能接住",
        "页面没埋但可优化",
        "页面埋得弱，先验证",
        "页面看不出来",
        "页面不建议埋",
    ),
)
def test_nonliteral_page_review_requires_attested_evidence(coverage):
    page = replace(PAGE, title="Unrelated page text")
    label, ref, verified, errors = page_coverage_for(
        "drawer organizer",
        page,
        PageReview(coverage, "synthetic:review"),
    )
    assert (label, ref, verified, errors) == (
        coverage,
        "synthetic:review",
        True,
        (),
    )


def test_inferred_risk_type_alone_does_not_claim_confirmed_hard_mismatch():
    x = row(labels=(VerifiedLabel("配件/替换词", "candidate:1", False),))
    decision = run_published_v11(
        product=product(), policy=policy(), candidates=(x,), source_total_rows=1, page=PAGE
    ).decisions[0]
    assert not decision.exact_selected and not decision.broad_selected
    assert decision.score is None
    assert decision.allocation_grade == "候选复查"


def test_proven_risk_blocks_both_targets():
    x = row(labels=(VerifiedLabel("材质不符词", "verified:conflict", True),))
    decision = run_published_v11(
        product=product(), policy=policy(), candidates=(x,), source_total_rows=1, page=PAGE
    ).decisions[0]
    assert decision.allocation_grade == "不投放"
    assert not decision.exact_selected and not decision.broad_selected


def test_missing_market_value_never_invents_points():
    x = row(data=None)
    decision = run_published_v11(
        product=product(), policy=policy(), candidates=(x,), source_total_rows=1, page=PAGE
    ).decisions[0]
    assert decision.score is None
    assert "DATA_POINTS_MISSING_OR_INVALID" in decision.reasons


def test_market_points_must_match_rule_version_and_comparability():
    x = row(data=MarketPoints(15, ("obs",), "rules:old", True))
    assert build_evidence(x, policy(), PAGE).data_points is None
    x = row(data=MarketPoints(15, ("obs",), "rules:v3", False))
    assert build_evidence(x, policy(), PAGE).data_points is None


def test_literal_page_phrase_is_not_derived_from_synonym_or_subword():
    p = WalmartPageEvidence("page:1", "123", "store:1", "verified", title="Drawer Organizers")
    label, _, _, _ = page_coverage_for("drawer organizer", p, None)
    assert label == "页面看不出来"
    p = WalmartPageEvidence("page:1", "123", "store:1", "verified", title="Amazing Pineapple")
    label, _, _, _ = page_coverage_for("apple", p, None)
    assert label == "页面看不出来"


def test_missing_page_snapshot_blocks_final_score():
    decision = run_published_v11(
        product=product(), policy=policy(), candidates=(row(),), source_total_rows=1, page=None
    ).decisions[0]
    assert decision.score is None
    assert not decision.exact_selected


def test_manual_cannot_falsely_claim_title_placement():
    label, _, valid, errors = page_coverage_for(
        "drawer organizer",
        WalmartPageEvidence("page:1", "123", "store:1", "verified", title="Other item"),
        PageReview("标题已埋词", "operator:note"),
    )
    assert label is None and not valid and "PAGE_TEXT_CLAIM_NOT_EVIDENCED" in errors


def test_confirmed_brand_token_match_without_substring_false_positive():
    p = policy(confirmed_brands={"Apple": "brand:list:1"})
    assert classify_brand("apple watch band", p) == "confirmed"
    assert classify_brand("pineapple cutlery", p) == "none"


def test_suspected_brand_is_not_uploaded():
    p = policy(suspected_brands={"ExampleCo": "brand:candidate:1"})
    decision = run_published_v11(
        product=product(),
        policy=p,
        candidates=(row("ExampleCo drawer organizer"),),
        source_total_rows=1,
        page=PAGE,
    ).decisions[0]
    assert decision.allocation_grade == "候选复查"
    assert not decision.exact_selected


def test_draft_policy_is_internal_review_without_ad_targets():
    run = run_published_v11(
        product=product(),
        policy=policy(status="draft"),
        candidates=(row(),),
        source_total_rows=1,
        page=PAGE,
    )
    assert run.decisions[0].score == 100
    assert run.decisions[0].exact_selected is False
    assert run.decisions[0].broad_selected is False
    assert "RULE_PENDING_APPROVAL" in run.decisions[0].reasons
    assert run.official_export_authorized is False


def test_unverified_product_must_block_run():
    with pytest.raises(ValueError, match="PRODUCT_NOT_CONFIRMED"):
        run_published_v11(
            product=replace(product(), item_verified=False),
            policy=policy(),
            candidates=(row(),),
            source_total_rows=1,
            page=PAGE,
        )


def test_missing_root_proof_never_gets_broad_slot():
    x = row(root=VerifiedRoot("drawer organizer", "R0", "", False))
    d = run_published_v11(
        product=product(), policy=policy(), candidates=(x,), source_total_rows=1, page=PAGE
    ).decisions[0]
    assert not d.broad_selected
    assert d.score is None


def test_duplicate_source_ranks_are_not_silently_reconciled():
    with pytest.raises(ValueError, match="SOURCE_RANK_DUPLICATE"):
        run_published_v11(
            product=product(),
            policy=policy(),
            candidates=(row("abc", rank=1), row("def", rank=1)),
            source_total_rows=2,
            page=PAGE,
        )


def test_batch_order_invariant_when_all_evidence_is_fixed():
    src = tuple(
        row(f"word {i:02d}", rank=i, broad_requested=False, exact_requested=False)
        for i in range(1, 8)
    )
    a = run_published_v11(
        product=product(), policy=policy(), candidates=src, source_total_rows=7, page=PAGE
    )
    b = run_published_v11(
        product=product(),
        policy=policy(),
        candidates=tuple(reversed(src)),
        source_total_rows=7,
        page=PAGE,
    )
    assert [(d.keyword, d.score, d.allocation_grade) for d in a.decisions] == [
        (d.keyword, d.score, d.allocation_grade) for d in b.decisions
    ]


def test_cross_account_or_wrong_item_page_is_rejected():
    with pytest.raises(ValueError, match="PAGE_SNAPSHOT_IDENTITY_OR_ACCOUNT_MISMATCH"):
        run_published_v11(
            product=product(),
            policy=policy(),
            candidates=(row(),),
            source_total_rows=1,
            page=replace(PAGE, source_account_ref="store:2"),
        )
    with pytest.raises(ValueError, match="PAGE_SNAPSHOT_IDENTITY_OR_ACCOUNT_MISMATCH"):
        run_published_v11(
            product=product(),
            policy=policy(),
            candidates=(row(),),
            source_total_rows=1,
            page=replace(PAGE, item_id="different"),
        )


def test_runtime_enforces_p0_p1_p2_exact_broad_caps_without_padding():
    rows = tuple(
        row(
            f"drawer organizer {i:02d}",
            rank=i,
            broad_role=("root" if i % 2 else "long_tail"),
            root=VerifiedRoot(f"drawer organizer {i:02d}", "R0", f"proof:{i}", True),
            page_review=PageReview("用户确认能接住", f"operator:page:{i}"),
        )
        for i in range(1, 51)
    )
    run = run_published_v11(
        product=product(), policy=policy(), candidates=rows, source_total_rows=50, page=PAGE
    )
    ds = run.decisions
    assert sum(x.allocation_grade == "P0" for x in ds) == 5
    assert sum(x.allocation_grade == "P1" for x in ds) == 10
    assert sum(x.allocation_grade == "P2" for x in ds) == 30
    assert sum(x.exact_selected for x in ds) == 20
    assert sum(x.broad_selected and x.broad_role == "root" for x in ds) <= 5
    assert sum(x.broad_selected and x.broad_role == "long_tail" for x in ds) <= 15
    assert sum(x.broad_selected for x in ds) <= 20


def test_unknown_root_and_data_do_not_obtain_numeric_grade():
    x = row(root=None, data=None)
    d = run_published_v11(
        product=product(), policy=policy(), candidates=(x,), source_total_rows=1, page=PAGE
    ).decisions[0]
    assert d.score is None
    assert d.allocation_grade == "候选复查"


def test_evidenced_page_unsuitable_overrides_literal_title_match():
    label, ref, _, errors = page_coverage_for(
        "drawer organizer", PAGE, PageReview("页面不建议埋", "operator:review")
    )
    assert label == "页面不建议埋" and ref == "operator:review" and not errors
