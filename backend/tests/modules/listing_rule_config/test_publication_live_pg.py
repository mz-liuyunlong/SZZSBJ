"""Opt-in publication transaction test against disposable PostgreSQL."""

import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config import publish
from app.modules.listing_rule_config.models import ListingEvaluationRun, ListingEvaluationSnapshot
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService
from app.modules.listing_rule_config.publish import ListingEvaluationPublisher

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_publication_is_atomic_counted_and_idempotent(monkeypatch) -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    monkeypatch.setattr(
        publish,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_publish_enabled=True),
    )
    monkeypatch.setattr(
        ListingEvaluationPreviewService,
        "evaluate",
        lambda self, **kwargs: SimpleNamespace(
            missing_evidence=[],
            rule_version=1,
            lifecycle_candidate="启动期",
            grade_candidate="B",
            valid_short=7,
            valid_medium=14,
            valid_stock_days_30=30,
            weighted_margin_percent=None,
        ),
    )
    try:
        with Session(engine) as session:
            listing = ListingManagementCurrentMart(
                source_account_ref="synthetic-publication-account",
                store_id="synthetic-store",
                item_id=f"SYNTHETIC-{uuid4()}",
                fulfillment_type="1",
                calculated_at=datetime.now(UTC),
            )
            run = ListingEvaluationRun(
                schedule_date_cn=date(2025, 2, 15),
                cutoff_date_la=date(2025, 2, 13),
                status="succeeded",
                rule_version=1,
                attempt_count=uuid4().int % 1_000_000_000,
                total_listings=1,
                processed_listings=1,
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
                lifecycle_candidate="启动期",
                grade_candidate="B",
                valid_short=7,
                valid_medium=14,
                valid_stock_days_30=30,
                rule_version=1,
                evidence_json=[],
                publication_status="candidate_only",
                published=False,
            )
            session.add(snapshot)
            session.commit()
            listing_id, run_id, snapshot_id = listing.id, run.id, snapshot.id
            assert ListingEvaluationPublisher(session).publish_run(run_id=run_id) == 1
            assert ListingEvaluationPublisher(session).publish_run(run_id=run_id) == 0
        with Session(engine) as session:
            current = session.get(ListingManagementCurrentMart, listing_id)
            stored_run = session.get(ListingEvaluationRun, run_id)
            stored_snapshot = session.get(ListingEvaluationSnapshot, snapshot_id)
            assert current is not None and stored_run is not None and stored_snapshot is not None
            assert (current.lifecycle_status, current.product_grade) == ("启动期", "B")
            assert stored_run.published_count == 1
            assert stored_snapshot.publication_status == "published"
            assert stored_snapshot.published_at is not None
            with pytest.raises(ApiError):
                ListingEvaluationPublisher(session).revert_snapshot(
                    snapshot_id=snapshot_id,
                    actor="synthetic-reviewer",
                    reason="synthetic correction evidence",
                    account_refs=frozenset({"synthetic-other"}),
                )
            assert session.get(ListingManagementCurrentMart, listing_id).product_grade == "B"
            reverted = ListingEvaluationPublisher(session).revert_snapshot(
                snapshot_id=snapshot_id,
                actor="synthetic-reviewer",
                reason="synthetic correction evidence",
                account_refs=frozenset({"synthetic-publication-account"}),
            )
            assert reverted.publication_status == "reverted"
        with Session(engine) as session:
            current = session.get(ListingManagementCurrentMart, listing_id)
            stored_run = session.get(ListingEvaluationRun, run_id)
            stored_snapshot = session.get(ListingEvaluationSnapshot, snapshot_id)
            assert current.lifecycle_status is None and current.product_grade is None
            assert stored_run.published_count == 0
            assert stored_snapshot.reverted_by == "synthetic-reviewer"
            assert stored_snapshot.revert_reason == "synthetic correction evidence"
    finally:
        engine.dispose()
