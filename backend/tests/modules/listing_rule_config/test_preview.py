"""Safety checks for the provisional financial and stockout candidates."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.listing_rule_config.preview import (
    basic_financial_candidate,
    lifecycle_allows_grade,
    stockout_candidate,
)
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CUTOFF = date(2026, 10, 24)


def _financial(i: int, profit: str = "20"):
    return SimpleNamespace(
        business_date_la=CUTOFF - timedelta(days=i),
        sales_amount=Decimal("100"),
        gross_profit_amount=Decimal(profit),
        cost_status="complete",
        missing_cost_codes_json=[],
        sales_currency_code="USD",
        gross_profit_currency_code="USD",
    )


def test_financial_diagnostic_does_not_impute_missing_days():
    grade, short, medium, margin = basic_financial_candidate(
        [_financial(i) for i in range(2)],
        cutoff=CUTOFF,
        config=ListingGradeRuleConfig(),
    )
    assert (grade, short, medium, margin) == (None, 2, 2, None)


def test_financial_candidate_requires_explicit_currency():
    rows = [_financial(i) for i in range(14)]
    rows[0].sales_currency_code = None
    grade, short, medium, margin = basic_financial_candidate(
        rows, cutoff=CUTOFF, config=ListingGradeRuleConfig()
    )
    assert (grade, short, medium, margin) == ("A", 6, 13, Decimal("20"))


def test_grade_candidate_honors_configured_lifecycle_scope() -> None:
    config = ListingGradeRuleConfig(included_stages=["启动期", "稳定期"])

    assert lifecycle_allows_grade("启动期", archived=False, config=config)
    assert not lifecycle_allows_grade("测品期", archived=False, config=config)
    assert not lifecycle_allows_grade("断货期", archived=False, config=config)
    assert not lifecycle_allows_grade("启动期", archived=True, config=config)


def test_stockout_requires_actual_wfs_inventory_not_erp_fulfillment():
    rows = [
        SimpleNamespace(
            snapshot_date_la=CUTOFF - timedelta(days=i),
            wfs_available_quantity=Decimal("0"),
        )
        for i in range(7)
    ]
    result = stockout_candidate(
        rows,
        cutoff=CUTOFF,
        low_limit=5,
        prior_effective_stock=True,
        fulfillment_type="1",
        currently_archived=False,
    )
    assert result == ("断货期", 7, 7)
    # A stale seller-fulfillment label never invalidates measured WFS stock.
    for fulfillment_type in ("0", "2", None):
        assert stockout_candidate(
            rows, cutoff=CUTOFF, low_limit=5,
            prior_effective_stock=True, fulfillment_type=fulfillment_type,
            currently_archived=False,
        )[0] == "断货期"
    for kwargs in (
        {"prior_effective_stock": False, "fulfillment_type": "1", "currently_archived": False},
        {"prior_effective_stock": True, "fulfillment_type": "1", "currently_archived": True},
    ):
        assert stockout_candidate(rows, cutoff=CUTOFF, low_limit=5, **kwargs)[0] is None


def test_openapi_contains_preview_route():
    from app.main import create_app

    assert "/api/listings/evaluation-preview" in create_app().openapi()["paths"]


def test_batch_input_limits_and_duplicates() -> None:
    from uuid import UUID

    from pydantic import ValidationError

    from app.modules.listing_rule_config.preview_router import ListingEvaluationBatchRequest

    listing_id = UUID("00000000-0000-0000-0000-000000000001")
    assert ListingEvaluationBatchRequest(listing_ids=[listing_id]).listing_ids == [listing_id]
    with pytest.raises(ValidationError):
        ListingEvaluationBatchRequest(listing_ids=[])
    with pytest.raises(ValidationError):
        ListingEvaluationBatchRequest(listing_ids=[listing_id] * 51)


def test_openapi_contains_batch_preview_route() -> None:
    from app.main import create_app

    assert "/api/listings/evaluation-preview/batch" in create_app().openapi()["paths"]

def test_preview_uses_authoritative_wfs_decision_even_for_stale_fbm_label() -> None:
    from unittest.mock import MagicMock, patch
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from app.modules.listing_rule_config.automation import LifecycleDecision
    from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService

    listing = SimpleNamespace(
        id=uuid4(),
        source_account_ref="account-1",
        store_id="store-1",
        item_id="item-1",
        msku="A",
        lifecycle_status="启动期",
        product_grade=None,
        fulfillment_type="0",  # ERP says seller-fulfilled, WFS facts win.
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [listing, None, None, None]
    session.scalars.return_value.all.return_value = []
    decision = LifecycleDecision(
        stage="稳定期",
        reason="WFS趋势已证实",
        valid_stock_days_30=21,
        consecutive_low_stock_days=0,
        evidence_complete=True,
        first_positive_date_la=CUTOFF - timedelta(days=40),
    )
    with patch("app.modules.listing_rule_config.preview.evaluate_listing", return_value=decision) as evaluator:
        result = ListingEvaluationPreviewService(session).evaluate(
            listing_id=listing.id,
            account_refs=frozenset({"account-1"}),
            cutoff=CUTOFF,
        )
    evaluator.assert_called_once()
    assert result.lifecycle_candidate == "稳定期"
    assert result.lifecycle_evidence_reason == "WFS趋势已证实"
    assert result.valid_stock_days_30 == 21
    assert "NON_WFS_OR_UNKNOWN_FULFILLMENT" not in result.missing_evidence
