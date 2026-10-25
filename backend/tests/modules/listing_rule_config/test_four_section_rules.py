"""Four independent rule groups persist in a single validated version."""
import pytest
from pydantic import ValidationError
from app.modules.listing_rule_config.schemas import (
    ListingGradeRuleConfig,
    LifecycleRuleConfig,
    InventoryRepairRuleConfig,
    FollowUpRuleConfig,
    SalesTierPercents,
)


def test_all_sections_match_confirmed_defaults() -> None:
    x = ListingGradeRuleConfig()
    assert x.lifecycle.min_week_valid_days == 4
    assert (x.lifecycle.growth_min_valid_days_30, x.lifecycle.stable_min_valid_days_30,
            x.lifecycle.decline_min_valid_days_30) == (14, 21, 21)
    assert list(x.lifecycle.growth_threshold_pct.model_dump().values()) == [50, 40, 30, 25, 20]
    assert list(x.lifecycle.stable_tolerance_pct.model_dump().values()) == [60, 45, 35, 30, 25]
    assert (x.inventory_repair.low_stock_max_units,
            x.inventory_repair.stockout_consecutive_days,
            x.inventory_repair.long_stockout_days) == (5, 7, 25)
    assert (x.inventory_repair.stockout_repair_valid_days,
            x.inventory_repair.abnormal_recovery_days) == (15, 7)
    assert x.follow_up.deadline_time is None and not x.follow_up.overdue_notice


@pytest.mark.parametrize("section,patch", [
    ("lifecycle", {"min_week_valid_days": 8}),
    ("lifecycle", {"growth_threshold_pct": {"lt2": 5, "from2to5": 40,
        "from5to10": 30, "from10to20": 25, "gte20": 20}}),
    ("inventory_repair", {"stockout_consecutive_days": 30, "long_stockout_days": 25}),
    ("inventory_repair", {"low_stock_max_units": -1}),
    ("follow_up", {"overdue_notice": True}),
    ("follow_up", {"reminder_time": "18:00", "deadline_time": "17:00"}),
    ("follow_up", {"reminder_time": "25:01"}),
])
def test_invalid_section_params_rejected(section: str, patch: dict[str, object]) -> None:
    x = ListingGradeRuleConfig()
    values = x.model_dump()
    values[section] = {**values[section], **patch}
    with pytest.raises(ValidationError):
        ListingGradeRuleConfig.model_validate(values)


def test_sections_round_trip_version_json() -> None:
    first = ListingGradeRuleConfig(
        lifecycle=LifecycleRuleConfig(growth_min_valid_days_30=16),
        inventory_repair=InventoryRepairRuleConfig(low_stock_max_units=7),
        follow_up=FollowUpRuleConfig(reminder_time="09:00", deadline_time="18:00", overdue_notice=True),
    )
    next_rule = ListingGradeRuleConfig.model_validate(first.model_dump(mode="json"))
    assert next_rule == first
    assert next_rule.inventory_repair.low_stock_max_units == 7


def test_extra_fields_cannot_override_protected_rules() -> None:
    with pytest.raises(ValidationError):
        ListingGradeRuleConfig.model_validate({
            **ListingGradeRuleConfig().model_dump(), "closing_lag_days": 1,
        })
