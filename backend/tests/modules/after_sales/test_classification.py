from pathlib import Path

from app.modules.after_sales.classification.schemas import (
    ClassificationRule,
    ReasonDefinition,
    ResponsibilityDefinition,
)
from app.modules.after_sales.classification.service import AfterSalesReasonClassifier


def _classifier() -> AfterSalesReasonClassifier:
    reasons = {
        "PRODUCT_DEFECTIVE": ReasonDefinition(
            "PRODUCT_DEFECTIVE", "商品故障/损坏", "PRODUCT", "商品问题", "#FF4D4F"
        ),
        "SHIPPING_BOX_DAMAGED": ReasonDefinition(
            "SHIPPING_BOX_DAMAGED", "运输箱破损", "LOGISTICS", "物流问题", "#1677FF"
        ),
        "UNCLASSIFIED": ReasonDefinition("UNCLASSIFIED", "未分类", "PENDING", "待判定", "#8C8C8C"),
    }
    responsibilities = {
        "PRODUCT": ResponsibilityDefinition("PRODUCT", "商品问题", "#FF4D4F"),
        "LOGISTICS": ResponsibilityDefinition("LOGISTICS", "物流问题", "#1677FF"),
        "PENDING": ResponsibilityDefinition("PENDING", "待判定", "#8C8C8C"),
    }
    rules = [
        ClassificationRule(
            id="exact",
            raw_reason_code="OTHER",
            match_type="EXACT_PAIR",
            match_value="Shipping box damaged",
            keywords_all=(),
            keywords_any=(),
            keywords_exclude=(),
            normalized_reason_code="SHIPPING_BOX_DAMAGED",
            responsibility_code="LOGISTICS",
            priority=1000,
            confidence="HIGH",
            rule_version="v1",
        ),
        ClassificationRule(
            id="description",
            raw_reason_code=None,
            match_type="EXACT_DESCRIPTION",
            match_value="Shipping box damaged",
            keywords_all=(),
            keywords_any=(),
            keywords_exclude=(),
            normalized_reason_code="SHIPPING_BOX_DAMAGED",
            responsibility_code="LOGISTICS",
            priority=900,
            confidence="HIGH",
            rule_version="v1",
        ),
        ClassificationRule(
            id="keyword",
            raw_reason_code=None,
            match_type="KEYWORD",
            match_value=None,
            keywords_all=("shipping", "damaged"),
            keywords_any=(),
            keywords_exclude=(),
            normalized_reason_code="SHIPPING_BOX_DAMAGED",
            responsibility_code="LOGISTICS",
            priority=700,
            confidence="MEDIUM",
            rule_version="v1",
        ),
        ClassificationRule(
            id="code",
            raw_reason_code="DEFECTIVE",
            match_type="CODE_DEFAULT",
            match_value=None,
            keywords_all=(),
            keywords_any=(),
            keywords_exclude=(),
            normalized_reason_code="PRODUCT_DEFECTIVE",
            responsibility_code="PRODUCT",
            priority=300,
            confidence="HIGH",
            rule_version="v1",
        ),
    ]
    return AfterSalesReasonClassifier(
        reasons=reasons,
        responsibilities=responsibilities,
        rules=rules,
    )


def test_exact_pair_beats_keyword_and_normalizes_other_case() -> None:
    result = _classifier().classify("Other", " Shipping   box damaged ")
    assert result.classification_source == "EXACT_PAIR"
    assert result.normalized_reason_code == "SHIPPING_BOX_DAMAGED"
    assert result.responsibility_code == "LOGISTICS"
    assert result.classification_confidence == "HIGH"


def test_exact_description_handles_known_text_with_new_raw_code() -> None:
    result = _classifier().classify("PROVIDER_NEW_CODE", "Shipping box damaged")
    assert result.classification_source == "EXACT_DESCRIPTION"
    assert result.normalized_reason_code == "SHIPPING_BOX_DAMAGED"
    assert result.responsibility_code == "LOGISTICS"


def test_keyword_is_used_for_new_description() -> None:
    result = _classifier().classify("OTHER", "Package shipping damaged during delivery")
    assert result.classification_source == "KEYWORD"
    assert result.normalized_reason_code == "SHIPPING_BOX_DAMAGED"
    assert result.classification_confidence == "MEDIUM"


def test_code_default_is_lower_priority_fallback() -> None:
    result = _classifier().classify("DEFECTIVE", "Brand new provider wording")
    assert result.classification_source == "CODE_DEFAULT"
    assert result.normalized_reason_code == "PRODUCT_DEFECTIVE"
    assert result.responsibility_code == "PRODUCT"


def test_unknown_reason_falls_back_to_pending() -> None:
    result = _classifier().classify("NEW_REASON", "Unknown provider text")
    assert result.classification_source == "FALLBACK"
    assert result.normalized_reason_code == "UNCLASSIFIED"
    assert result.responsibility_code == "PENDING"
    assert result.classification_rule_id is None


def test_importers_do_not_reclassify_existing_fact_rows_on_conflict() -> None:
    backend_root = Path(__file__).resolve().parents[3]

    for relative_path in (
        "scripts/import_after_sales_refund_items.py",
        "scripts/import_walmart_return_orders_snapshot.py",
    ):
        importer = (backend_root / relative_path).read_text(encoding="utf-8")

        assert "normalized_reason_code = excluded.normalized_reason_code" not in importer
        assert "classification_rule_version = excluded.classification_rule_version" not in importer
        assert "classified_at = excluded.classified_at" not in importer
