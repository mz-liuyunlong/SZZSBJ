"""Retries retain diagnostic evidence from earlier Listing evaluation attempts."""

from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.models import ListingEvaluationRun


@pytest.mark.parametrize("status", ["queued", "running", "succeeded"])
def test_existing_non_retryable_attempt_is_reused(status: str) -> None:
    session = MagicMock(spec=Session)
    existing = ListingEvaluationRun(
        id=uuid4(),
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        status=status,
        attempt_count=1,
    )
    session.scalar.return_value = existing

    result = ListingEvaluationBatchService(session).run_daily_diagnostic(
        schedule_date_cn=date(2026, 1, 15), cutoff_date_la=date(2026, 1, 14)
    )

    assert result == existing.id
    session.add.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_retry_creates_new_attempt_without_deleting_prior_snapshots(status: str) -> None:
    session = MagicMock(spec=Session)
    prior_id = uuid4()
    next_id = uuid4()
    prior = ListingEvaluationRun(
        id=prior_id,
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        status=status,
        rule_version=0,
        attempt_count=1,
    )
    session.scalar.side_effect = [prior, 2]
    session.add.side_effect = lambda run: setattr(run, "id", next_id)
    service = ListingEvaluationBatchService(session)
    service._evaluate_pages = MagicMock()

    result = service.run_daily_diagnostic(
        schedule_date_cn=date(2026, 1, 15), cutoff_date_la=date(2026, 1, 14)
    )

    assert result == next_id
    attempt = session.add.call_args.args[0]
    assert attempt.id != prior.id
    assert attempt.attempt_count == 2
    assert attempt.rule_version == prior.rule_version
    assert prior.status == status
    session.execute.assert_not_called()
