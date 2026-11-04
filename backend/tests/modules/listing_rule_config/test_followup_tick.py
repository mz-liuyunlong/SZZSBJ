"""Synthetic reminder planning never calls an external provider."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.listing_rule_config import tasks
from app.modules.listing_rule_config.models import ListingGradeRuleVersion
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


def test_disabled_followup_tick_does_not_open_database(monkeypatch) -> None:
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(
            listing_evaluation_followup_notifications_enabled=False,
            listing_evaluation_publish_enabled=True,
        ),
    )
    monkeypatch.setattr(
        tasks,
        "get_engine",
        lambda: (_ for _ in ()).throw(AssertionError("disabled task must not access DB")),
    )
    tasks.followup_tick()


def test_followup_tick_queues_generic_reminder_and_overdue_once_per_event(monkeypatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 15, 10, 30, tzinfo=tz)

    config = ListingGradeRuleConfig()
    config.follow_up.reminder_time = "09:00"
    config.follow_up.deadline_time = "10:00"
    config.follow_up.overdue_notice = True
    rule = ListingGradeRuleVersion(
        version=1,
        config_json=config.model_dump(mode="json"),
        effective_from=datetime(2025, 1, 1, tzinfo=tasks.UTC),
        created_at=datetime(2025, 1, 1, tzinfo=tasks.UTC),
        created_by="synthetic-operator",
        change_reason="synthetic followup rule",
    )
    session = MagicMock()
    session.scalar.side_effect = [rule, 1]
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    monkeypatch.setattr(tasks, "datetime", FrozenDateTime)
    monkeypatch.setattr(tasks, "Session", lambda _engine: session_context)
    monkeypatch.setattr(tasks, "get_engine", lambda: object())
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(
            listing_evaluation_followup_notifications_enabled=True,
            listing_evaluation_publish_enabled=True,
        ),
    )
    queued = []
    monkeypatch.setattr(
        tasks, "queue_notification", lambda payload, *, actor: queued.append((payload, actor))
    )

    tasks.followup_tick()

    assert [row.event_key for row, _actor in queued] == [
        "listing_grade_followup_reminder",
        "listing_grade_followup_overdue",
    ]
    assert len({row.source_event_id for row, _actor in queued}) == 2
    assert all("SYNTHETIC-ITEM" not in row.text for row, _actor in queued)
    assert all(actor == "system:listing-evaluation" for _row, actor in queued)
