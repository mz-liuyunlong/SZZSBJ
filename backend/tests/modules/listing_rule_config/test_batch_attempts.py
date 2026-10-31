"""Retries retain diagnostic evidence from earlier Listing evaluation attempts."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.modules.listing_rule_config.batch import ListingEvaluationBatchService
from app.modules.listing_rule_config.models import ListingEvaluationRun
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


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


def test_successful_day_replay_requires_explicit_flag_and_keeps_rule_version() -> None:
    session = MagicMock(spec=Session)
    prior = ListingEvaluationRun(
        id=uuid4(),
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        status="succeeded",
        rule_version=7,
        attempt_count=1,
    )
    session.scalar.side_effect = [prior, 2]
    session.get.side_effect = [
        SimpleNamespace(config_json=ListingGradeRuleConfig().model_dump()),
        SimpleNamespace(processed_listings=2, total_listings=2),
    ]
    next_id = uuid4()
    session.add.side_effect = lambda run: setattr(run, "id", next_id)
    service = ListingEvaluationBatchService(session)
    service._evaluate_pages = MagicMock()

    result = service.run_daily_diagnostic(
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        replay_succeeded=True,
    )

    assert result == next_id
    attempt = session.add.call_args.args[0]
    assert attempt.attempt_count == 2
    assert attempt.rule_version == 7
    assert prior.status == "succeeded"
    service._evaluate_pages.assert_called_once()


def test_replay_rejects_different_cutoff_for_existing_schedule_date() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = ListingEvaluationRun(
        id=uuid4(),
        schedule_date_cn=date(2026, 1, 15),
        cutoff_date_la=date(2026, 1, 14),
        status="succeeded",
        attempt_count=1,
    )

    with pytest.raises(ValueError, match="cutoff is fixed"):
        ListingEvaluationBatchService(session).run_daily_diagnostic(
            schedule_date_cn=date(2026, 1, 15),
            cutoff_date_la=date(2026, 1, 13),
            replay_succeeded=True,
        )

    session.add.assert_not_called()
