"""Strict IO models; avoid implicit zero defaults for business metrics."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ListingQuery(Strict):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    store_id: str = Field(default="", max_length=128)
    owner: str = Field(default="", max_length=128)
    keyword: str = Field(default="", max_length=128)
    search_field: Literal["sku", "msku", "item_id", "title"] = "item_id"
    status: str = Field(default="", max_length=128)


class RuleApply(Strict):
    kind: Literal["performance", "tracking"] = "performance"
    expected_version: int = Field(ge=0)
    config: dict[str, Any]
    change_reason: str = Field(default="", max_length=1000)


class Identity(Strict):
    source_account_ref: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    store_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    item_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class MarketWrite(Identity):
    score: int = Field(ge=0, le=10)
    reason: str = Field(min_length=5, max_length=4000)
    expected_version: int = Field(ge=0)


class TrackingWrite(Identity):
    decision: Literal["打品成功", "继续观察", "需要优化", "打品失败"]
    reason: str = Field(default="", max_length=4000)
    expected_version: int = Field(ge=0)


class PurchaseWrite(Identity):
    requested_qty: int = Field(ge=1, le=100000)
    reason: str = Field(default="", max_length=4000)
    expected_rule_version: int = Field(ge=0)


class PurchaseDecision(Strict):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=4000)
    expected_version: int = Field(ge=1)


class RulePreview(Identity):
    config: dict[str, Any]
