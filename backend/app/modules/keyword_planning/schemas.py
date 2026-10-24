"""Read-only projections of immutable keyword analysis runs.

Never return raw source cells, full rule configs, platform payloads or authorization data.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    product_id: UUID
    source_account_ref: str
    item_id: str
    status: str
    rule_version_id: UUID
    created_at: datetime
    finished_at: datetime | None
    keyword_count: int


class RunListRead(BaseModel):
    items: list[RunRead]
    total: int
    limit: int
    offset: int


class KeywordRead(BaseModel):
    term_id: UUID
    keyword: str
    primary_type: str | None
    page_coverage: str | None
    core_root: str | None
    score: int | None
    match_points: int | None = None
    intent_points: int | None = None
    page_points: int | None = None
    root_points: int | None = None
    data_points: int | None = None
    risk_points: int | None = None
    base_grade: str | None
    allocation_grade: str | None
    exact_selected: bool
    broad_selected: bool
    broad_role: str | None
    suggested_optimization_bid: Decimal | None
    decision_status: str
    risk_reasons: list[str] = Field(default_factory=list)
    exact_reason: str | None
    broad_reason: str | None
    quality_note: str | None
    rank_index: int | None
    evidence: dict[str, object] = Field(default_factory=dict)


class KeywordListRead(BaseModel):
    run_id: UUID
    items: list[KeywordRead]
    total: int
    limit: int
    offset: int
    official_export_authorized: bool = False
