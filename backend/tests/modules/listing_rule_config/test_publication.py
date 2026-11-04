"""A frozen snapshot never overwrites changed or unverified Listing data."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.listing_rule_config import publish
from app.modules.listing_rule_config.models import (
    ListingEvaluationSnapshot,
    ListingGradeRuleVersion,
)
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService
from app.modules.listing_rule_config.publish import ListingEvaluationPublisher
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

LISTING_ID = UUID(int=51)
CUTOFF = date(2026, 1, 15)


def snapshot() -> ListingEvaluationSnapshot:
    return ListingEvaluationSnapshot(
        id=UUID(int=52),
        run_id=UUID(int=53),
        listing_id=LISTING_ID,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku=None,
        cutoff_date_la=CUTOFF,
        current_lifecycle=None,
        current_grade=None,
        lifecycle_candidate="启动期",
        grade_candidate="B",
        valid_short=7,
        valid_medium=14,
        valid_stock_days_30=30,
        weighted_margin_percent=None,
        rule_version=1,
        evidence_json=[],
        publication_status="candidate_only",
        published=False,
    )


def listing():
    return SimpleNamespace(
        id=LISTING_ID,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku=None,
        lifecycle_status=None,
        product_grade=None,
    )


def rule():
    return ListingGradeRuleVersion(
        version=1,
        config_json=ListingGradeRuleConfig().model_dump(mode="json"),
        effective_from=datetime(1970, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_by="system",
        change_reason="synthetic rule",
    )


def test_publication_rechecks_evidence_and_writes_both_fields(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    current = listing()
    candidate = snapshot()
    session.scalar.side_effect = [current, None]
    session.get.return_value = rule()
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
    assert ListingEvaluationPublisher(session)._publish_one(candidate) is None
    assert (current.lifecycle_status, current.product_grade) == ("启动期", "B")
    assert candidate.published is True
    assert candidate.published_by == "system:listing-evaluation"


def test_publish_run_persists_published_counter(monkeypatch) -> None:
    session = MagicMock(spec=Session)
    candidate = snapshot()
    run = SimpleNamespace(status="succeeded", rule_version=1, published_count=0)
    session.get.return_value = run
    session.scalars.return_value.all.return_value = [candidate.id]
    session.scalar.return_value = candidate
    monkeypatch.setattr(
        publish,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_publish_enabled=True),
    )
    monkeypatch.setattr(ListingEvaluationPublisher, "_publish_one", lambda self, row: None)
    assert ListingEvaluationPublisher(session).publish_run(run_id=candidate.run_id) == 1
    assert run.published_count == 1
    assert session.commit.call_count == 2


@pytest.mark.parametrize(
    "change",
    ["identity", "current_stage", "missing_evidence", "manual_conflict"],
)
def test_publication_rejects_stale_or_unverified_snapshots(monkeypatch, change: str) -> None:
    session = MagicMock(spec=Session)
    current = listing()
    candidate = snapshot()
    if change == "identity":
        current.store_id = "synthetic-other"
    if change == "current_stage":
        current.lifecycle_status = "稳定期"
    if change == "missing_evidence":
        candidate.evidence_json = ["SYNTHETIC_MISSING"]
    if change == "manual_conflict":
        session.scalar.side_effect = [current, UUID(int=54)]
    else:
        session.scalar.return_value = current
    session.get.return_value = rule()
    monkeypatch.setattr(
        ListingEvaluationPreviewService,
        "evaluate",
        lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("must not re-evaluate")),
    )
    assert ListingEvaluationPublisher(session)._publish_one(candidate) is not None
    assert current.product_grade is None
    assert candidate.published is False
