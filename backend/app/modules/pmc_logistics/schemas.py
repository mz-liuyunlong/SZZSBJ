"""Response models of the 物流看板 API. Row and detail bodies keep the 8088 field names
(``app-a.jsx`` ``enrich``) so the page and the 8088 demo read the same keys."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Option(BaseModel):
    value: str
    label: str


class LogisticsRuleSummary(BaseModel):
    remind_before: int
    delivered_not_signed: int
    penalty_per_kg_day: float
    wm_receive_buffer: int
    receive_diff_buffer: int
    region_total: dict[str, int]


class LogisticsBoard(BaseModel):
    today: date
    rows: list[dict[str, Any]] = Field(
        description="One SP per row: Lingxing shipping-list fields + 8088 derived fields."
    )
    stages: list[str]
    stage_counts: dict[str, int]
    providers: list[Option]
    channels: list[dict[str, str]]
    stores: list[Option]
    regions: list[str]
    rules: LogisticsRuleSummary
    sources: dict[str, Any]


class LogisticsDetail(BaseModel):
    today: date
    row: dict[str, Any]
    track: dict[str, Any] | None = None
    walmart: list[dict[str, Any]] = Field(default_factory=list)
