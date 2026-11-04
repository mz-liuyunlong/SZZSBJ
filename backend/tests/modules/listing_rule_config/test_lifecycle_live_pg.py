"""Opt-in lifecycle approval test against a disposable migrated PostgreSQL database."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.lifecycle import ListingLifecycleAdjustmentService
from app.modules.listing_rule_config.models import ListingLifecycleAdjustment

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_manual_decision_is_atomic_and_account_scoped_in_postgres() -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    item_id = f"SYNTHETIC-{uuid4()}"
    try:
        with Session(engine) as session:
            listing = ListingManagementCurrentMart(
                source_account_ref="synthetic-account",
                store_id="synthetic-store",
                item_id=item_id,
                fulfillment_type="1",
                lifecycle_status="测品期",
                calculated_at=datetime.now(UTC),
            )
            session.add(listing)
            session.commit()
            listing_id = listing.id
            service = ListingLifecycleAdjustmentService(session)
            row = service.request(
                listing_id=listing_id,
                requested_stage="启动期",
                reason="synthetic manual lifecycle evidence",
                actor="synthetic-requester",
                account_refs=frozenset({"synthetic-account"}),
            )
            adjustment_id = row.id
            with pytest.raises(ApiError):
                service.decide(
                    adjustment_id=adjustment_id,
                    approve=True,
                    note="synthetic reviewer decision",
                    actor="synthetic-requester",
                    account_refs=frozenset({"synthetic-account"}),
                )
            assert (
                session.get(ListingManagementCurrentMart, listing_id).lifecycle_status == "测品期"
            )
            with pytest.raises(ApiError):
                service.decide(
                    adjustment_id=adjustment_id,
                    approve=True,
                    note="synthetic reviewer decision",
                    actor="synthetic-approver",
                    account_refs=frozenset({"synthetic-other"}),
                )
            decided = service.decide(
                adjustment_id=adjustment_id,
                approve=True,
                note="synthetic reviewer decision",
                actor="synthetic-approver",
                account_refs=frozenset({"synthetic-account"}),
            )
            assert decided.status == "approved"
        with Session(engine) as session:
            stored = session.scalar(
                select(ListingLifecycleAdjustment).where(
                    ListingLifecycleAdjustment.id == adjustment_id
                )
            )
            assert stored is not None
            assert stored.decided_by == "synthetic-approver"
            assert (
                session.get(ListingManagementCurrentMart, listing_id).lifecycle_status == "启动期"
            )
    finally:
        engine.dispose()
