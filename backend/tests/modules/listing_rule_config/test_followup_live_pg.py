"""Opt-in published C/D follow-up test against disposable PostgreSQL."""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.models import (
    ListingEvaluationRun,
    ListingEvaluationSnapshot,
    ListingGradeFollowUpTask,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_published_cd_snapshot_creates_one_scoped_followup() -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            listing = ListingManagementCurrentMart(
                source_account_ref="synthetic-followup-account",
                store_id="synthetic-store",
                item_id=f"SYNTHETIC-{uuid4()}",
                owner_ref="synthetic-owner",
                fulfillment_type="1",
                calculated_at=datetime.now(UTC),
            )
            run = ListingEvaluationRun(
                schedule_date_cn=date(2025, 1, 15),
                cutoff_date_la=date(2025, 1, 13),
                status="succeeded",
                rule_version=1,
                attempt_count=uuid4().int % 1_000_000_000,
                total_listings=1,
                processed_listings=1,
                published_count=1,
            )
            session.add_all((listing, run))
            session.flush()
            snapshot = ListingEvaluationSnapshot(
                run_id=run.id,
                listing_id=listing.id,
                source_account_ref=listing.source_account_ref,
                store_id=listing.store_id,
                item_id=listing.item_id,
                cutoff_date_la=run.cutoff_date_la,
                grade_candidate="C",
                lifecycle_candidate="启动期",
                rule_version=1,
                evidence_json=[],
                publication_status="published",
                published=True,
                published_at=datetime.now(UTC),
                published_by="system:listing-evaluation",
            )
            session.add(snapshot)
            session.commit()
            assert (
                ListingEvaluationBatchService(session).create_followups_for_published_run(
                    run_id=run.id
                )
                == 1
            )
            assert (
                ListingEvaluationBatchService(session).create_followups_for_published_run(
                    run_id=run.id
                )
                == 0
            )
            task = session.scalar(
                select(ListingGradeFollowUpTask).where(
                    ListingGradeFollowUpTask.snapshot_id == snapshot.id
                )
            )
            assert task is not None
            assert (task.source_account_ref, task.owner_ref, task.grade) == (
                "synthetic-followup-account",
                "synthetic-owner",
                "C",
            )
    finally:
        engine.dispose()
