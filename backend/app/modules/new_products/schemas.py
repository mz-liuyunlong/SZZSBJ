"""Strict IO models; avoid implicit zero defaults for business metrics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


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
    # New-product evaluation filters, distinct from Listing-management status.
    np_statuses: str = Field(default="", max_length=256)
    np_owners: str = Field(default="", max_length=1024)
    np_ratings: str = Field(default="", max_length=128)
    np_owner_keyword: str = Field(default="", max_length=128)
    first_wfs_start_date: date | None = Field(
        default=None, description="LA WFS first available date, inclusive"
    )
    first_wfs_end_date: date | None = Field(
        default=None, description="LA WFS first available date, inclusive"
    )


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

    # Manual Walmart competitor Item IDs, persisted alongside the market score.
    competitor_ids: list[str]
    no_competitors: bool

    @field_validator("competitor_ids")
    @classmethod
    def validate_competitor_ids(cls, values: list[str]) -> list[str]:
        if any(not (value.isascii() and value.isalnum()) for value in values):
            raise ValueError("竞品 ID 只允许英文字母和数字")
        return values

    @model_validator(mode="after")
    def validate_competitor_selection(self):
        if self.no_competitors and self.competitor_ids:
            raise ValueError("勾选无竞品时不得填写竞品 ID")
        if not self.no_competitors and not self.competitor_ids:
            raise ValueError("请填写竞品 ID，或勾选无")
        return self

    # PR337_MANUAL_RISK_V1: enforced even if UI validation is bypassed.
    risk_conditions: list[str] = Field(min_length=1, max_length=14)

    @field_validator("risk_conditions")
    @classmethod
    def check_risk_conditions(cls, values: list[str]) -> list[str]:
        allowed = {
            "无",
            "资金占用率高",
            "季节性（一般）",
            "低价依赖",
            "ROI低（Pass）",
            "ROI低（评级上限）",
            "季节性（强）",
            "侵权风险",
            "合规风险",
            "供应链风险",
            "质量风险",
            "价格风险",
            "退货风险",
            "平台风险",
        }
        if len(values) != len(set(values)) or any(v not in allowed for v in values):
            raise ValueError("风险条件含无效或重复选项")
        if "无" in values and len(values) != 1:
            raise ValueError("选择「无」时不能同时勾选其他风险")
        return values


# NP_OPERATOR_SCORE_CORRECTION_V1_20261119: operator writes, no approval step.
class ScoreCorrectionWrite(Identity):
    dimension: Literal["speed", "ad", "profit", "trust"]
    new_score: Decimal = Field(ge=0, le=10, decimal_places=2)
    reason: str = Field(min_length=5, max_length=500)
    expected_revision: int = Field(ge=0)


class GradeConfirmationWrite(Identity):
    expected_revision: int = Field(ge=0)


class TrackingWrite(Identity):
    decision: Literal["打品成功", "继续观察", "需要优化", "打品失败"]
    reason: str = Field(min_length=10, max_length=4000, description="复盘说明，至少10个非空白字符")
    expected_version: int = Field(ge=0)

    @field_validator("reason")
    @classmethod
    def validate_tracking_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if len("".join(trimmed.split())) < 10:
            raise ValueError("复盘说明 / 判定依据至少填写10个字")
        return trimmed


class AssessmentWrite(Identity):
    decision: Literal["passed", "failed"]
    reason: str = Field(min_length=20, max_length=4000)

    @field_validator("reason")
    @classmethod
    def validate_assessment_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if len("".join(trimmed.split())) < 20:
            raise ValueError("人工测评通过与不通过均须填写至少20个非空白字符")
        return trimmed


class AssessmentPurchaseWrite(AssessmentWrite):
    # One write request, one business transaction. Purchase approval still follows.
    decision: Literal["passed"]
    requested_qty: int = Field(ge=1, le=100000)
    purchase_reason: str = Field(default="", max_length=4000)
    expected_rule_version: int = Field(ge=0)


class PurchaseWrite(Identity):
    requested_qty: int = Field(ge=1, le=100000)
    reason: str = Field(default="", max_length=4000)
    expected_rule_version: int = Field(ge=0)


class PurchaseDecision(Strict):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=4000)
    expected_version: int = Field(ge=1)
    purchase_store_id: str | None = Field(default=None, min_length=1, max_length=128)
    approved_qty: int | None = Field(default=None, ge=1, le=100000)


class RulePreview(Identity):
    config: dict[str, Any]


# SZZSBJ_PURCHASE_APPROVE_STORE_QTY_V1
