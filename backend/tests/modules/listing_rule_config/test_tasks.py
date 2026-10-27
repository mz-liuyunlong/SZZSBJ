"""Tests for the opt-in Listing evaluation scheduler."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.modules.listing_rule_config import tasks
from app.modules.listing_rule_config.models import ListingGradeRuleVersion


def test_scheduler_does_not_open_database_when_disabled(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_scheduler_enabled=False),
    )
    monkeypatch.setattr(
        tasks,
        "get_engine",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be opened when disabled")),
    )
    tasks.scheduler_tick()


def test_schedule_default_is_china_2230():
    from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

    assert ListingGradeRuleConfig().execution_time == "22:30"


def test_pending_schedule_supersedes_old_boundary_without_early_run() -> None:
    now = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)  # 22:30 China time
    pending = ListingGradeRuleVersion(
        version=2,
        config_json={"execution_time": "23:00"},
        effective_from=datetime(2026, 1, 15, 15, 0, tzinfo=UTC),
        created_at=now,
        created_by="synthetic-operator",
        change_reason="synthetic schedule change",
    )

    assert tasks.rule_is_due(pending, now) is False
    assert tasks.rule_is_due(pending, pending.effective_from) is True


def test_schedule_moved_earlier_does_not_catch_up_before_effective_date() -> None:
    now = datetime(2026, 1, 15, 15, 30, tzinfo=UTC)  # 23:30 China time
    pending = ListingGradeRuleVersion(
        version=2,
        config_json={"execution_time": "22:30"},
        effective_from=datetime(2026, 1, 16, 14, 30, tzinfo=UTC),
        created_at=now,
        created_by="synthetic-operator",
        change_reason="synthetic schedule change",
    )

    assert tasks.rule_is_due(pending, now) is False
