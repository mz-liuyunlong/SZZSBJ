"""Strict input contracts for clearance V1; all mutation data is server-validated."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ListingQuery(Strict):
    store_id: str = ""
    keyword: Annotated[str, StringConstraints(max_length=128)] = ""
    risk_level: Literal["high", "medium", "low", "unknown"] | None = None
    candidate_status: Literal["auto", "observe", "none", "review_required"] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class ApplicationWrite(Strict):
    listing_id: str
    target_qty: int = Field(ge=1)
    methods: list[Literal["降价", "促销", "广告清货", "WFS 移除", "弃置"]] = Field(
        min_length=1, max_length=5
    )
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    remark: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    due_date: date | None = None
    proposed_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    source: Literal["manual", "auto"] = "manual"


class DecisionWrite(Strict):
    decision: Literal["approved", "rejected"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    expected_version: int = Field(ge=1)


class ProgressWrite(Strict):
    sold_qty: int = Field(ge=0)
    removed_qty: int = Field(ge=0)
    disposed_qty: int = Field(ge=0)
    expected_version: int = Field(ge=1)


class RuleWrite(Strict):
    source_account_ref: str
    expected_version: int = Field(ge=0)
    rules: dict[str, bool | int | float]
