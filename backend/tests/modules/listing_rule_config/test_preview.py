"""Safety checks for the provisional financial and stockout candidates."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.listing_rule_config.preview import (
    basic_financial_candidate,
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


def test_stockout_requires_prior_stock_and_wfs_fulfillment():
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
    for kwargs in (
        {"prior_effective_stock": True, "fulfillment_type": "2", "currently_archived": False},
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
