"""Offline pure business rule validation without a production database."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig, ListingGradeRuleUpdate
from app.modules.listing_rule_config.service import next_rating_time_utc


def test_defaults_match_owner_approved_v1() -> None:
    rule = ListingGradeRuleConfig()
    assert (rule.short_days, rule.medium_days) == (7, 14)
    assert (rule.short_weight_percent, rule.medium_weight_percent) == (60, 40)
    assert (rule.short_min_valid_days, rule.medium_min_valid_days) == (4, 8)
    assert (rule.c_min_percent, rule.b_min_percent, rule.a_above_percent) == (5, 10, 15)
    assert "清货期" not in rule.included_stages


@pytest.mark.parametrize(
    "patch",
    [
        {"short_weight_percent": 70},
        {"short_days": 14},
        {"short_min_valid_days": 8},
        {"medium_min_valid_days": 15},
        {"c_min_percent": 12},
        {"included_stages": ["清货期"]},
        {"included_stages": []},
        {"included_stages": ["打品期", "打品期"]},
        {"closing_lag_days": 1},
    ],
)
def test_rejects_invalid_or_protected_fields(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ListingGradeRuleConfig.model_validate({**ListingGradeRuleConfig().model_dump(), **patch})


def test_update_rejects_overriding_fixed_schedule() -> None:
    with pytest.raises(ValidationError):
        ListingGradeRuleUpdate.model_validate(
            {
                "expected_version": 0,
                "change_reason": "test edit",
                "config": ListingGradeRuleConfig().model_dump(),
                "execution_timezone": "America/Los_Angeles",
            }
        )


def test_next_china_rating_boundary() -> None:
    # 14:00 UTC == 22:00 China, so the same day 22:30 is next.
    assert next_rating_time_utc(datetime(2026, 10, 25, 14, 0, tzinfo=UTC)) == datetime(
        2026, 10, 25, 14, 30, tzinfo=UTC
    )
    # Exactly 22:30 China waits until the following day.
    assert next_rating_time_utc(datetime(2026, 10, 25, 14, 30, tzinfo=UTC)) == datetime(
        2026, 10, 26, 14, 30, tzinfo=UTC
    )
