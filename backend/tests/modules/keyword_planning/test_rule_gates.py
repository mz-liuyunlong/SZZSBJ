from dataclasses import replace

import pytest

from app.modules.keyword_planning.rule_gates import (
    ColdStartLimits,
    KeywordEvidence,
    ProductConfirmation,
    ProductField,
    allocate_ads,
    can_generate_official_file,
    normalize_keyword,
    parse_asins,
    product_confirmation_errors,
    score_evidence,
)


def base_evidence(keyword: str = "drawer organizer", **kwargs: object) -> KeywordEvidence:
    e = KeywordEvidence(
        keyword=keyword,
        primary_type="核心本体词",
        core_root="drawer organizer",
        root_grade="R0",
        page_coverage="标题已埋词",
        page_snapshot_verified=True,
        page_evidence_ref="page:abc:title:2-18",
        match_points=30,
        intent_points=20,
        page_points=20,
        root_points=15,
        data_points=15,
        risk_points=0,
        exact_eligible=True,
        broad_eligible=True,
        broad_role="long_tail",
        broad_risk="low",
    )
    return replace(e, **kwargs)


def test_normalization_and_asin_are_strict_and_conservative() -> None:
    assert normalize_keyword(" Drawer   Organizer ") == "drawer organizer"
    assert normalize_keyword("coasters for drinks") == "coasters for drinks"
    assert normalize_keyword("drawer-organizer") != normalize_keyword("drawer organizer")
    valid, invalid = parse_asins("B012345678\nB012345678\nINVALID\nB012345679")
    assert valid == ("B012345678", "B012345679")
    assert invalid == ("INVALID",)


def test_product_confirmation_is_fail_closed_for_missing_or_unverified_fields() -> None:
    value = ProductConfirmation(
        item_id="123456789",
        item_verified=False,
        source_item_id=None,
        facts={"title": ProductField("Nice product", "walmart", "page:0")},
        risk_boundary_acknowledged=False,
        risk_boundary_mode="unreviewed",
    )
    errors = product_confirmation_errors(value)
    assert "ITEM_ID_UNVERIFIED" in errors
    assert "PRODUCT_REQUIRED_MISSING:material" in errors
    assert "RISK_BOUNDARY_NOT_REVIEWED" in errors


def test_product_placeholder_is_not_real_data() -> None:
    keys = (
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
    facts = {key: ProductField("Verified", "operator") for key in keys}
    facts["pack"] = ProductField("未知", "operator")
    value = ProductConfirmation("123", True, "123", facts, True, "none")
    assert "PRODUCT_REQUIRED_MISSING:pack" in product_confirmation_errors(value)
    assert not product_confirmation_errors(
        replace(value, facts={**facts, "pack": ProductField("2-pack", "operator")})
    )


def test_page_text_cannot_be_claimed_without_page_evidence() -> None:
    decision = score_evidence(base_evidence(page_snapshot_verified=False, page_evidence_ref=None))
    assert "PAGE_TEXT_CLAIM_NOT_EVIDENCED" in decision.reasons
    assert decision.score is None
    assert decision.base_grade == "候选复查"


def test_unknown_market_signal_never_becomes_fabricated_points() -> None:
    decision = score_evidence(base_evidence(data_points=None))
    assert decision.score is None
    assert "DATA_POINTS_MISSING_OR_INVALID" in decision.reasons


def test_hard_risk_blocks_exact_and_broad_even_if_nominal_score_is_100() -> None:
    evidence = base_evidence(
        "replacement drawer parts",
        primary_type="配件/替换词",
        hard_risk_reasons=("PRODUCT_NOT_REPLACEMENT_PART",),
    )
    result = allocate_ads((evidence,))[0]
    assert result.allocation_grade == "不投放"
    assert result.exact_selected is False and result.broad_selected is False


def test_suspected_brand_cannot_pass_ad_selection() -> None:
    decision = allocate_ads((base_evidence(brand_status="suspected"),))[0]
    assert decision.allocation_grade == "候选复查"
    assert not decision.exact_selected


def test_level_overflow_preserves_original_grade_and_caps() -> None:
    items = tuple(
        base_evidence(f"drawer organizer {i:02d}", core_root=f"drawer organizer {i:02d}")
        for i in range(50)
    )
    result = allocate_ads(items)
    assert sum(d.allocation_grade == "P0" for d in result) == 5
    assert sum(d.allocation_grade == "P1" for d in result) == 10
    assert sum(d.allocation_grade == "P2" for d in result) == 30
    assert sum(d.allocation_grade == "候选复查" for d in result) == 5
    assert all(d.base_grade == "P0" for d in result)
    assert sum(d.exact_selected for d in result) == 20
    assert sum(d.broad_selected for d in result) == 15


def test_broad_roots_and_long_tail_are_separate_not_all_p0_auto_broad() -> None:
    roots = tuple(
        base_evidence(f"root {i}", core_root=f"root {i}", broad_role="root") for i in range(12)
    )
    tails = tuple(
        base_evidence(f"tail {i}", core_root=f"tail {i}", broad_role="long_tail") for i in range(25)
    )
    out = allocate_ads(roots + tails, limits=ColdStartLimits())
    assert sum(d.broad_selected and d.broad_role == "root" for d in out) <= 5
    assert sum(d.broad_selected and d.broad_role == "long_tail" for d in out) <= 15
    assert sum(d.broad_selected for d in out) <= 20


def test_no_auto_padding_unsupported_exact_and_broad() -> None:
    e = base_evidence(exact_eligible=False, broad_eligible=False)
    r = allocate_ads((e,))[0]
    assert not r.exact_selected and not r.broad_selected


def test_order_and_decisions_stable_independent_of_input_order() -> None:
    data = tuple(base_evidence(f"kw {i:02d}") for i in range(26))
    a = allocate_ads(data)
    b = allocate_ads(tuple(reversed(data)))
    assert [(x.keyword, x.allocation_grade, x.exact_selected, x.broad_selected) for x in a] == [
        (x.keyword, x.allocation_grade, x.exact_selected, x.broad_selected) for x in b
    ]


def test_duplicates_still_raise_for_analysis_but_not_upload_raw() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_KEYWORDS"):
        allocate_ads((base_evidence("Drawer  Organizer"), base_evidence("drawer organizer")))


def test_formal_export_requires_all_approval_gates() -> None:
    true = dict(
        run_succeeded=True,
        input_snapshot_unchanged=True,
        user_confirmed=True,
        template_verified=True,
        all_hard_checks_passed=True,
    )
    assert can_generate_official_file(**true)
    assert not can_generate_official_file(**{**true, "template_verified": False})
    assert not can_generate_official_file(**{**true, "user_confirmed": False})


def test_unknown_type_never_enters_exact_even_if_someone_claims_100_points() -> None:
    out = allocate_ads((base_evidence(primary_type="人工确认词"),))[0]
    assert out.score is None
    assert not out.exact_selected and not out.broad_selected


def test_page_unsuitable_is_blocked_even_with_high_score() -> None:
    out = allocate_ads((base_evidence(page_coverage="页面不建议埋", page_points=0),))[0]
    assert out.allocation_grade == "不投放"
    assert not out.exact_selected and not out.broad_selected


def test_explicit_rule_version_and_all_four_bids_required() -> None:
    from decimal import Decimal

    from app.modules.keyword_planning.rule_gates import ExecutionParams, execution_parameter_errors

    good = ExecutionParams(
        Decimal(".31"), Decimal(".21"), Decimal("10"), Decimal("10"), "2026-10-23", "rules:v3"
    )
    assert execution_parameter_errors(good) == ()
    assert "EXECUTION_US_DATE_INVALID" in execution_parameter_errors(
        replace(good, start_date_us_eastern="2026-02-30")
    )
    assert "EXECUTION_PARAMETER_MISSING:auto_bid" in execution_parameter_errors(
        replace(good, auto_bid=None)
    )
    assert "EXECUTION_RULE_NOT_PUBLISHED" in execution_parameter_errors(
        replace(good, published_rule_version_ref="")
    )
