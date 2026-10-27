"""Tests for the opt-in Listing evaluation scheduler."""
from types import SimpleNamespace

from app.modules.listing_rule_config import tasks


def test_scheduler_does_not_open_database_when_disabled(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(listing_evaluation_scheduler_enabled=False),
    )
    monkeypatch.setattr(
        tasks,
        "get_session_factory",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be opened when disabled")),
    )
    tasks.scheduler_tick()


def test_schedule_default_is_china_2230():
    from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

    assert ListingGradeRuleConfig().execution_time == "22:30"
