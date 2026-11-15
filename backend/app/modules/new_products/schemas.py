"""Strict IO models; avoid implicit zero defaults for business metrics."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


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

    # PR337_MANUAL_RISK_V1: enforced even if UI validation is bypassed.
    risk_conditions: list[str] = Field(min_length=1, max_length=14)

    @field_validator("risk_conditions")
    @classmethod
    def check_risk_conditions(cls, values: list[str]) -> list[str]:
        allowed = {
            "无",
            "资金占用率高",
            "广告数据骤变",
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
