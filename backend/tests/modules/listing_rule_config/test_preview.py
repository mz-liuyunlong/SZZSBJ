"""Safety checks for the provisional financial and stockout candidates."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.listing_rule_config.preview import (
    ListingEvaluationPreviewService,
    archive_has_post_cutoff_event,
    basic_financial_candidate,
    lifecycle_allows_grade,
    stockout_candidate,
)
from app.modules.listing_rule_config.preview_router import list_evaluation_runs
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CUTOFF = date(2026, 10, 24)


def _financial(i: int, profit: str = "20"):
    return SimpleNamespace(
        business_date_la=CUTOFF - timedelta(days=i),
        sales_amount=Decimal("100"),
        sales_qty=Decimal("1"),
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
        unconfirmed_account_ad_days=frozenset(),
    )
    assert (grade, short, medium, margin) == (None, 2, 2, None)


def test_financial_candidate_requires_explicit_currency():
    rows = [_financial(i) for i in range(14)]
    rows[0].sales_currency_code = None
    grade, short, medium, margin = basic_financial_candidate(
        rows,
        cutoff=CUTOFF,
        config=ListingGradeRuleConfig(),
        unconfirmed_account_ad_days=frozenset(),
    )
    assert (grade, short, medium, margin) == ("A", 6, 13, Decimal("20"))


def test_account_day_zero_ad_spend_blocks_diagnostic_grade() -> None:
    grade, short, medium, margin = basic_financial_candidate(
        [_financial(i) for i in range(14)],
        cutoff=CUTOFF,
        config=ListingGradeRuleConfig(),
        unconfirmed_account_ad_days=frozenset({CUTOFF - timedelta(days=3)}),
    )
    assert (grade, short, medium, margin) == (None, 7, 14, None)


def test_wfs_preview_reports_account_day_ad_blocker() -> None:
    listing = SimpleNamespace(
        id=UUID(int=2),
        fulfillment_type="1",
        lifecycle_status="稳定期",
        product_grade=None,
    )
    result = ListingEvaluationPreviewService._from_evidence(
        listing=listing,
        cutoff=CUTOFF,
        config=ListingGradeRuleConfig(),
        rule_version=1,
        sales=[_financial(i) for i in range(14)],
        stock=[],
        prior=None,
        archive=None,
        monitor_rows=[],
        unconfirmed_account_ad_days=frozenset({CUTOFF - timedelta(days=3)}),
    )
    assert result.grade_candidate is None
    assert "DAILY_SALES_ACCOUNT_DAY_AD_SPEND_UNCONFIRMED" in result.missing_evidence


def test_account_day_ad_total_is_scoped_and_includes_sem() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE mart_daily_sales_item_day ("
                "source_account_ref TEXT, business_date_la DATE, "
                "ad_spend_amount NUMERIC, sem_ad_spend_amount NUMERIC)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mart_daily_sales_item_day VALUES "
                "('synthetic-a', '2026-10-24', 0, 0), "
                "('synthetic-a', '2026-10-23', 0, 0), "
                "('synthetic-a', '2026-10-23', 0, 3), "
                "('synthetic-b', '2026-10-24', 5, 0), "
                "('synthetic-b', '2026-10-23', 0, 0)"
            )
        )
    with Session(engine) as session:
        unconfirmed = ListingEvaluationPreviewService(session)._unconfirmed_account_ad_days(
            {"synthetic-a", "synthetic-b"}, cutoff=CUTOFF, window_days=3
        )
    assert unconfirmed == {
        "synthetic-a": frozenset({CUTOFF, CUTOFF - timedelta(days=2)}),
        "synthetic-b": frozenset({CUTOFF - timedelta(days=1), CUTOFF - timedelta(days=2)}),
    }


def test_grade_candidate_honors_configured_lifecycle_scope() -> None:
    config = ListingGradeRuleConfig(included_stages=["启动期", "稳定期"])

    assert lifecycle_allows_grade("启动期", archived=False, config=config)
    assert not lifecycle_allows_grade("测品期", archived=False, config=config)
    assert not lifecycle_allows_grade("断货期", archived=False, config=config)
    assert not lifecycle_allows_grade("启动期", archived=True, config=config)


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
        prior_effective_stock=True,
        fulfillment_type="1",
        currently_archived=False,
    )
    assert result == ("断货期", 7, 7)
    for kwargs in (
        {"prior_effective_stock": True, "fulfillment_type": "2", "currently_archived": False},
        {"prior_effective_stock": True, "fulfillment_type": "0", "currently_archived": False},
        {"prior_effective_stock": False, "fulfillment_type": "1", "currently_archived": False},
        {"prior_effective_stock": True, "fulfillment_type": "1", "currently_archived": True},
    ):
        assert stockout_candidate(rows, cutoff=CUTOFF, **kwargs)[0] is None


def test_fbm_is_excluded_from_listing_evaluation() -> None:
    listing = SimpleNamespace(
        id=UUID(int=1),
        fulfillment_type="0",
        lifecycle_status="启动期",
        product_grade=None,
    )
    result = ListingEvaluationPreviewService._from_evidence(
        listing=listing,
        cutoff=CUTOFF,
        config=ListingGradeRuleConfig(),
        rule_version=1,
        sales=[],
        stock=[],
        prior=None,
        archive=None,
        monitor_rows=[],
        unconfirmed_account_ad_days=frozenset(),
    )
    assert result.grade_candidate is None
    assert result.lifecycle_candidate is None
    assert result.missing_evidence == ["NON_WFS_EXCLUDED"]


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


def test_run_list_does_not_expose_global_attempt_state_to_scoped_viewer() -> None:
    run_id = UUID("00000000-0000-0000-0000-000000000066")
    started_at = datetime(2026, 1, 15, tzinfo=UTC)
    run = SimpleNamespace(
        id=run_id,
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        status="failed",
        rule_version=7,
        total_listings=20,
        processed_listings=19,
        grade_candidate_count=10,
        lifecycle_candidate_count=10,
        blocked_count=9,
        published_count=0,
        attempt_count=3,
        started_at=started_at,
        finished_at=started_at,
        error_code="GLOBAL_SYNTHETIC_FAILURE",
    )
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = [run]
    session.scalar.return_value = 1
    session.execute.return_value.all.return_value = [(run_id, 1, 0, 1, 1, 0)]
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/listings/evaluation-runs", "headers": []}
    )

    response = list_evaluation_runs(
        request=request,
        session=session,
        account_refs=frozenset({"synthetic-visible-account"}),
        limit=20,
    )

    item = response.data.items[0]
    assert response.data.total == 1
    assert (item.total_listings, item.processed_listings) == (1, 1)
    assert (item.grade_candidate_count, item.lifecycle_candidate_count, item.blocked_count) == (
        0,
        1,
        1,
    )
    assert item.status == "scoped_snapshots"
    assert item.attempt_count is None
    assert item.started_at is None and item.finished_at is None
    assert item.error_code is None
    assert "source_account_ref IN" in str(session.execute.call_args.args[0])


def test_low_positive_stock_does_not_qualify_as_stockout() -> None:
    rows = [
        SimpleNamespace(
            snapshot_date_la=CUTOFF - timedelta(days=i),
            wfs_available_quantity=Decimal("3"),
        )
        for i in range(7)
    ]
    stage, observed, zero_days = stockout_candidate(
        rows,
        cutoff=CUTOFF,
        prior_effective_stock=True,
        fulfillment_type="1",
        currently_archived=False,
    )
    assert (stage, observed, zero_days) == (None, 7, 0)


def test_restore_after_historical_cutoff_requires_archive_evidence() -> None:
    cutoff = date(2026, 1, 15)
    archived_at = datetime(2026, 1, 14, 8, tzinfo=UTC)
    restored_at = datetime(2026, 1, 17, 8, tzinfo=UTC)

    assert archive_has_post_cutoff_event(
        archived_at=archived_at, restored_at=restored_at, cutoff=cutoff
    )
    assert not archive_has_post_cutoff_event(
        archived_at=archived_at, restored_at=None, cutoff=cutoff
    )
