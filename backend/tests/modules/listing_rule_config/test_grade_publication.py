"""Listing grade publishing must fail closed without audited ads and costs."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.modules.listing_rule_config.grade_publication import (
    PROOF_KEY,
    PROOF_ORIGIN,
    ListingGradePublicationService,
    _day_is_attested,
    _all_stores_day_ad_spend_positive,
)


def _financial_day(**kwargs):
    row = {
        "source_lineage_json": {
            PROOF_KEY: {
                "origin": PROOF_ORIGIN,
                "financial_complete": True,
                "advertising_complete": True,
                "zero_sales_coverage_confirmed": True,
                "evidence_sha256": "a" * 64,
            }
        },
        "sales_currency_code": "USD",
        "gross_profit_currency_code": "USD",
        "ad_spend_currency_code": "USD",
        "ad_spend_amount": 0,
        "sem_ad_spend_amount": 0,
        "cost_status": "complete",
        "missing_cost_codes_json": [],
        "gross_profit_amount": 2,
    }
    row.update(kwargs)
    return SimpleNamespace(**row)


def test_all_stores_zero_ad_spend_blocks_rating_day_not_single_store_zero():
    from decimal import Decimal

    assert not _all_stores_day_ad_spend_positive(None)
    assert not _all_stores_day_ad_spend_positive(Decimal("0"))
    assert _all_stores_day_ad_spend_positive(Decimal("0.01"))
    # One store with zero may be legitimate when other stores spent money.
    # The publication guard checks the aggregate across ALL stores/day.


def test_evidence_must_prove_both_finance_and_ads():
    assert _day_is_attested(_financial_day())
    assert not _day_is_attested(_financial_day(source_lineage_json={}))
    assert not _day_is_attested(_financial_day(ad_spend_amount=None))
    assert not _day_is_attested(_financial_day(cost_status="missing"))
    assert not _day_is_attested(_financial_day(gross_profit_currency_code="CNY"))
    incomplete_proof = _financial_day().source_lineage_json
    incomplete_proof[PROOF_KEY]["advertising_complete"] = False
    assert not _day_is_attested(_financial_day(source_lineage_json=incomplete_proof))


def test_zero_ads_is_not_proof_of_zero_advertising():
    assert not _day_is_attested(
        _financial_day(
            source_lineage_json={
                PROOF_KEY: {
                    "origin": PROOF_ORIGIN,
                    "financial_complete": True,
                    "advertising_complete": False,
                    "zero_sales_coverage_confirmed": True,
                    "evidence_sha256": "a" * 64,
                }
            }
        )
    )


def test_publisher_disabled_by_default_cannot_write():
    session = MagicMock(spec=Session)
    with patch("app.modules.listing_rule_config.grade_publication.get_settings") as settings:
        settings.return_value.listing_evaluation_publish_enabled = False
        with pytest.raises(RuntimeError, match="LISTING_GRADE_PUBLICATION_NOT_ENABLED"):
            ListingGradePublicationService(session).publish_run(run_id=uuid4())
    session.assert_not_called()
    session.get.assert_not_called()
