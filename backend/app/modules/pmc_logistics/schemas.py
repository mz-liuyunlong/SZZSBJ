"""Request and response models of the 物流 API. Row and detail bodies keep the 8088 field
names (``app-a.jsx`` ``enrich``, ``app-b.jsx`` tabs) so the pages and the 8088 demo read the
same keys."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Option(BaseModel):
    value: str
    label: str


class _Query(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    keyword: str = Field(default="", max_length=128)


class SpFilters(_Query):
    store: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=64)
    channel: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=16)
    field: Literal["sp", "cargo", "track", "sku"] = "sp"


class OverviewQuery(SpFilters):
    stage: str | None = Field(default=None, max_length=32)
    card: Literal["all", "transit", "soon", "over", "signed", "miss", "month"] = "all"


class AlertQuery(SpFilters):
    type: str | None = Field(default=None, max_length=64)
    sev: Literal["high", "mid", "low"] | None = None


class ForecastQuery(_Query):
    store: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=16)
    owner: str | None = Field(default=None, max_length=64)
    bucket: Literal["total", "bOver", "b15", "b30", "b60", "b60p", "bNone", "arrived"] | None = None


class CarrierQuery(_Query):
    status: str | None = Field(default=None, max_length=32)
    store: str | None = Field(default=None, max_length=64)
    stale: bool = False


RULE_SORTS = {
    "cycles": ("channel", "provider", "toSail", "voyage", "days", "sps"),
    "contracts": ("provider", "channel", "region", "days", "remind", "sps"),
    "fcs": ("fc", "state", "region", "n"),
}


class RuleListQuery(_Query):
    """Server-side paging for the 时效与阈值设置 tables; ``sort`` is checked per table."""

    sort: str | None = Field(default=None, max_length=16)
    order: Literal["asc", "desc"] = "asc"
    region: str | None = Field(default=None, max_length=16)


class LogisticsRuleSummary(BaseModel):
    remind_before: int
    delivered_not_signed: int
    penalty_per_kg_day: float
    wm_receive_buffer: int
    receive_diff_buffer: int
    region_total: dict[str, int]


class LogisticsOptions(BaseModel):
    """Filter options, rule summary and source counts shared by the 物流 pages."""

    today: date
    total: int
    stages: list[str]
    stage_counts: dict[str, int]
    providers: list[Option]
    channels: list[dict[str, str]]
    stores: list[Option]
    regions: list[str]
    owners: list[str]
    carrier_statuses: list[Option]
    alert_types: list[str]
    rules: LogisticsRuleSummary
    sources: dict[str, Any]


class LogisticsList(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    summary: dict[str, Any] = Field(default_factory=dict)


class LogisticsDetail(BaseModel):
    today: date
    row: dict[str, Any]
    track: dict[str, Any] | None = None
    walmart: list[dict[str, Any]] = Field(default_factory=list)


class CarrierOrderDetail(BaseModel):
    today: date
    order: dict[str, Any]


class LogisticsRulesView(BaseModel):
    """时效与阈值设置 (read-only): the rule values the pages are computed with."""

    today: date
    thresholds: list[dict[str, Any]]
    region_total: dict[str, int]
    counts: dict[str, int]
    editable: bool = False
    edit_hint: str
