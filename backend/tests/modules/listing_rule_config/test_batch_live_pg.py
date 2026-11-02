"""Opt-in diagnostic replay acceptance against a disposable PostgreSQL database."""

import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_diagnostic_retries_preserve_previous_snapshots_in_postgres() -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            assert session.scalar(select(ListingEvaluationRun.id).limit(1)) is None
            listing = ListingManagementCurrentMart(
                source_account_ref="synthetic-account",
                store_id="synthetic-store",
                item_id="SYNTHETIC-DIAGNOSTIC",
                fulfillment_type="2",  # Non-WFS is explicitly excluded from grading.
                calculated_at=datetime.now(UTC),
            )
            session.add(listing)
            session.commit()
            original_grade = listing.product_grade
            original_lifecycle = listing.lifecycle_status

            service = ListingEvaluationBatchService(session)
            schedule_date = date(2026, 1, 15)
            cutoff_date = date(2026, 1, 13)
            first_id = service.run_daily_diagnostic(
                schedule_date_cn=schedule_date, cutoff_date_la=cutoff_date
            )
            first_snapshot = session.scalar(
                select(ListingEvaluationSnapshot).where(
                    ListingEvaluationSnapshot.run_id == first_id
                )
            )
            assert first_snapshot is not None
            first_snapshot_id = first_snapshot.id
            assert first_snapshot.publication_status == "blocked"
            assert "NON_WFS_EXCLUDED" in first_snapshot.evidence_json
            assert first_snapshot.published is False

            first_run = session.get(ListingEvaluationRun, first_id)
            assert first_run is not None
            first_run.status = "partial"
            session.commit()
            second_id = service.run_daily_diagnostic(
                schedule_date_cn=schedule_date, cutoff_date_la=cutoff_date
            )
            assert second_id != first_id
            assert (
                service.run_daily_diagnostic(
                    schedule_date_cn=schedule_date, cutoff_date_la=cutoff_date
                )
                == second_id
            )
            third_id = service.run_daily_diagnostic(
                schedule_date_cn=schedule_date,
                cutoff_date_la=cutoff_date,
                replay_succeeded=True,
            )
            assert len({first_id, second_id, third_id}) == 3
            runs = session.scalars(
                select(ListingEvaluationRun).order_by(ListingEvaluationRun.attempt_count)
            ).all()
            assert [run.attempt_count for run in runs] == [1, 2, 3]
            assert [run.status for run in runs] == ["partial", "succeeded", "succeeded"]
            snapshots = session.scalars(
                select(ListingEvaluationSnapshot).order_by(ListingEvaluationSnapshot.created_at)
            ).all()
            assert {snapshot.run_id for snapshot in snapshots} == {first_id, second_id, third_id}
            assert session.get(ListingEvaluationSnapshot, first_snapshot_id) is not None
            assert all(not snapshot.published for snapshot in snapshots)
            session.refresh(listing)
            assert listing.product_grade == original_grade
            assert listing.lifecycle_status == original_lifecycle
    finally:
        engine.dispose()
