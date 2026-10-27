"""Request/response contracts for the Listing grade rules configuration."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ListingStage = Literal[
    "测品期",
    "打品期",
    "启动期",
    "上升期",
    "稳定期",
    "下滑期",
    "断货期",
    "修复期",
]

DEFAULT_INCLUDED_STAGES: tuple[ListingStage, ...] = (
    "打品期",
    "启动期",
    "上升期",
    "稳定期",
    "下滑期",
    "修复期",
)


class SalesTierPercents(BaseModel):
    """Thresholds for baseline effective daily sales bands (units): <2, 2-5, 5-10, 10-20, >=20."""

    model_config = ConfigDict(extra="forbid")

    lt2: int = Field(ge=1, le=200)
    from2to5: int = Field(ge=1, le=200)
    from5to10: int = Field(ge=1, le=200)
    from10to20: int = Field(ge=1, le=200)
    gte20: int = Field(ge=1, le=200)

    @model_validator(mode="after")
    def validate_tiers(self) -> SalesTierPercents:
        tiers = (self.lt2, self.from2to5, self.from5to10, self.from10to20, self.gte20)
        if any(a < b for a, b in pairwise(tiers)):
            raise ValueError("销量阶梯百分比应随基准销量增长而不递增")
        return self


class LifecycleRuleConfig(BaseModel):
    """Tunable samples and tier thresholds; 4x7 day windows and 2 weekly changes stay fixed."""

    model_config = ConfigDict(extra="forbid")

    min_week_valid_days: int = Field(default=4, ge=1, le=7)
    growth_min_valid_days_30: int = Field(default=14, ge=1, le=30)
    stable_min_valid_days_30: int = Field(default=21, ge=1, le=30)
    decline_min_valid_days_30: int = Field(default=21, ge=1, le=30)
    growth_threshold_pct: SalesTierPercents = Field(
        default_factory=lambda: SalesTierPercents(
            lt2=50,
            from2to5=40,
            from5to10=30,
            from10to20=25,
            gte20=20,
        )
    )
    decline_threshold_pct: SalesTierPercents = Field(
        default_factory=lambda: SalesTierPercents(
            lt2=50,
            from2to5=40,
            from5to10=30,
            from10to20=25,
            gte20=20,
        )
    )
    stable_tolerance_pct: SalesTierPercents = Field(
        default_factory=lambda: SalesTierPercents(
            lt2=60,
            from2to5=45,
            from5to10=35,
            from10to20=30,
            gte20=25,
        )
    )


class InventoryRepairRuleConfig(BaseModel):
    """Low-stock day, long-stock recovery and abnormality acceptance thresholds."""

    model_config = ConfigDict(extra="forbid")

    low_stock_max_units: int = Field(default=5, ge=0, le=10000)
    stockout_consecutive_days: int = Field(default=7, ge=1, le=90)
    long_stockout_days: int = Field(default=25, ge=2, le=365)
    stockout_repair_valid_days: int = Field(default=15, ge=1, le=180)
    strike_price_abnormal_days: int = Field(default=25, ge=1, le=365)
    buybox_abnormal_days: int = Field(default=25, ge=1, le=365)
    abnormal_recovery_days: int = Field(default=7, ge=1, le=90)

    @model_validator(mode="after")
    def validate_recovery(self) -> InventoryRepairRuleConfig:
        if self.stockout_consecutive_days >= self.long_stockout_days:
            raise ValueError("长期断货天数必须大于进入断货期的天数")
        return self


class FollowUpRuleConfig(BaseModel):
    """Optional reminder planning only; the existing C/D daily-check obligation is immutable."""

    model_config = ConfigDict(extra="forbid")

    reminder_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    deadline_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    overdue_notice: bool = False

    @model_validator(mode="after")
    def validate_reminder(self) -> FollowUpRuleConfig:
        if self.overdue_notice and self.deadline_time is None:
            raise ValueError("开启逾期提醒前必须设置每日截止时间")
        if self.reminder_time and self.deadline_time and self.reminder_time >= self.deadline_time:
            raise ValueError("提醒时间应早于同日完成截止时间")
        return self


class ListingGradeRuleConfig(BaseModel):
    """Adjustable Listing rules including the daily rating execution time."""

    model_config = ConfigDict(extra="forbid")

    execution_time: str = Field(default="22:30", pattern=r"^([01]\\d|2[0-3]):[0-5]\\d$")

    short_days: int = Field(default=7, ge=1, le=90)
    medium_days: int = Field(default=14, ge=2, le=180)
    short_weight_percent: int = Field(default=60, ge=1, le=99)
    medium_weight_percent: int = Field(default=40, ge=1, le=99)
    short_min_valid_days: int = Field(default=4, ge=1)
    medium_min_valid_days: int = Field(default=8, ge=1)
    c_min_percent: Decimal = Field(default=Decimal("5"), ge=-100, le=1000)
    b_min_percent: Decimal = Field(default=Decimal("10"), ge=-100, le=1000)
    a_above_percent: Decimal = Field(default=Decimal("15"), ge=-100, le=1000)
    included_stages: list[ListingStage] = Field(
        default_factory=lambda: list(DEFAULT_INCLUDED_STAGES)
    )
    lifecycle: LifecycleRuleConfig = Field(default_factory=LifecycleRuleConfig)
    inventory_repair: InventoryRepairRuleConfig = Field(default_factory=InventoryRepairRuleConfig)
    follow_up: FollowUpRuleConfig = Field(default_factory=FollowUpRuleConfig)

    @model_validator(mode="after")
    def validate_business_rules(self) -> ListingGradeRuleConfig:
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
    storage_ready: bool = True


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
    storage_ready: bool = True
