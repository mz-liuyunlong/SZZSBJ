"""Request/response contracts for the Listing grade rules configuration."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ListingStage = Literal[
    "测品期", "打品期", "启动期", "上升期", "稳定期",
    "下滑期", "断货期", "修复期",
]

DEFAULT_INCLUDED_STAGES: tuple[ListingStage, ...] = (
    "打品期", "启动期", "上升期", "稳定期", "下滑期", "修复期",
)


class ListingGradeRuleConfig(BaseModel):
    """Only adjustable grade rules belong here; financial safeguards are immutable."""

    model_config = ConfigDict(extra="forbid")

    short_days: int = Field(default=7, ge=1, le=90)
    medium_days: int = Field(default=14, ge=2, le=180)
    short_weight_percent: int = Field(default=60, ge=1, le=99)
    medium_weight_percent: int = Field(default=40, ge=1, le=99)
    short_min_valid_days: int = Field(default=4, ge=1)
    medium_min_valid_days: int = Field(default=8, ge=1)
    c_min_percent: Decimal = Field(default=Decimal("5"), ge=-100, le=1000)
    b_min_percent: Decimal = Field(default=Decimal("10"), ge=-100, le=1000)
    a_above_percent: Decimal = Field(default=Decimal("15"), ge=-100, le=1000)
    included_stages: list[ListingStage] = Field(default_factory=lambda: list(DEFAULT_INCLUDED_STAGES))

    @model_validator(mode="after")
    def validate_business_rules(self) -> "ListingGradeRuleConfig":
        if self.short_days >= self.medium_days:
            raise ValueError("短期统计窗口必须小于中期统计窗口")
        if self.short_weight_percent + self.medium_weight_percent != 100:
            raise ValueError("两个评级窗口权重之和必须为100%")
        if self.short_min_valid_days > self.short_days:
            raise ValueError("短期最低有效天数不能超过短期窗口")
        if self.medium_min_valid_days > self.medium_days:
            raise ValueError("中期最低有效天数不能超过中期窗口")
        if not self.c_min_percent < self.b_min_percent < self.a_above_percent:
            raise ValueError("C、B、A级边界必须严格递增")
        if not self.included_stages or len(self.included_stages) != len(set(self.included_stages)):
            raise ValueError("参与评级的生命周期不能为空或重复")
        return self


class ListingGradeRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    change_reason: str = Field(min_length=3, max_length=500)
    config: ListingGradeRuleConfig


class ProtectedListingRuleSettings(BaseModel):
    execution_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    execution_time: Literal["22:30"] = "22:30"
    business_timezone: Literal["America/Los_Angeles"] = "America/Los_Angeles"
    closing_lag_days: Literal[2] = 2
    requires_complete_financial_inputs: Literal[True] = True
    permanently_excluded_stages: tuple[str, str] = ("清货期", "已归档")


class ListingGradeRuleRead(BaseModel):
    version: int
    config: ListingGradeRuleConfig
    protected: ProtectedListingRuleSettings = Field(default_factory=ProtectedListingRuleSettings)
    effective_from: datetime | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    change_reason: str | None = None
    is_pending: bool = False
    source: Literal["default", "database"]
    can_edit: bool = False


class ListingGradeRuleHistoryItem(BaseModel):
    version: int
    config: ListingGradeRuleConfig
    effective_from: datetime
    created_at: datetime
    created_by: str
    change_reason: str


class ListingGradeRuleHistoryData(BaseModel):
    items: list[ListingGradeRuleHistoryItem]
    total: int
