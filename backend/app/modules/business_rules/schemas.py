from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CommissionRuleScope = Literal["store", "item", "price_range"]
StoreCommissionSource = Literal["store_rule", "default_15_percent"]
StoreCommissionApplyScope = Literal["all_dates", "from_date"]
BusinessRuleOperationStatus = Literal["queued", "running", "succeeded", "failed"]


def _split_text_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.replace(",", "\n").replace("，", "\n").replace(" ", "\n").splitlines()
    elif isinstance(value, list):
        raw_values = [str(item) for item in value]
    else:
        raw_values = [str(value)]

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


class BusinessRuleOperationRead(BaseModel):
    id: str
    source_account_ref: str
    platform_code: str
    operation_type: str
    status: BusinessRuleOperationStatus
    store_id: str | None = None
    rule_scope: CommissionRuleScope | None = None
    item_ids: list[str] = Field(default_factory=list)
    price_min_amount: Decimal | None = None
    price_max_amount: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    days_recalculated: int = 0
    daily_sales_rows: int = 0
    order_profit_rows: int = 0
    actor_ref: str
    request_id: str
    message: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class StoreCommissionRead(BaseModel):
    id: str | None = None
    source_account_ref: str
    platform_code: str
    store_id: str
    store_name: str | None = None
    rule_scope: CommissionRuleScope
    item_id: str | None = None
    price_min_amount: Decimal | None = None
    price_max_amount: Decimal | None = None
    priority: int = 100
    commission_rate: Decimal
    commission_percent: Decimal
    source: StoreCommissionSource
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool
    rule_version: str | None = None
    change_reason: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    needs_recalculate: bool = False
    active_operation_id: str | None = None
    active_operation_status: BusinessRuleOperationStatus | None = None
    active_operation_actor: str | None = None
    active_operation_created_at: datetime | None = None


class StoreCommissionListData(BaseModel):
    store_rules: list[StoreCommissionRead]
    special_rules: list[StoreCommissionRead]
    active_operations: list[BusinessRuleOperationRead] = Field(default_factory=list)
    operation_logs: list[BusinessRuleOperationRead] = Field(default_factory=list)


class StoreCommissionMutationData(BaseModel):
    items: list[StoreCommissionRead]


class StoreCommissionUpsertRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    platform_code: Literal["walmart"] = "walmart"
    store_id: str = Field(min_length=1, max_length=128)
    rule_scope: CommissionRuleScope = "store"
    item_id: str | None = None
    item_ids: list[str] = Field(default_factory=list)
    price_min_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    price_max_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    priority: int = Field(default=100, ge=1, le=9999)
    commission_rate: Decimal = Field(ge=Decimal("0"), lt=Decimal("1"))
    apply_scope: StoreCommissionApplyScope = "all_dates"
    effective_from: date | None = None
    effective_to: date | None = None
    change_reason: str = Field(min_length=2, max_length=500)
    replace_rule_id: str | None = None

    @field_validator("source_account_ref", "store_id", "change_reason")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("item_ids", mode="before")
    @classmethod
    def normalize_item_ids(cls, value: object) -> list[str]:
        return _split_text_values(value)

    @field_validator("item_id")
    @classmethod
    def strip_item_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def normalized_item_ids(self) -> list[str]:
        values = list(self.item_ids)
        if self.item_id:
            values.insert(0, self.item_id)
        return _split_text_values(values)

    @model_validator(mode="after")
    def validate_rule(self) -> StoreCommissionUpsertRequest:
        if self.apply_scope == "from_date" and self.effective_from is None:
            raise ValueError("effective_from is required when apply_scope is from_date")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("effective_to must be greater than effective_from")

        if self.rule_scope == "item" and not self.normalized_item_ids():
            raise ValueError("item_ids is required when rule_scope is item")

        if self.rule_scope == "price_range":
            if self.price_min_amount is None and self.price_max_amount is None:
                raise ValueError("price_min_amount or price_max_amount is required")
            if (
                self.price_min_amount is not None
                and self.price_max_amount is not None
                and self.price_min_amount >= self.price_max_amount
            ):
                raise ValueError("price_min_amount must be less than price_max_amount")

        return self


class StoreCommissionRecalculateRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    rule_scope: CommissionRuleScope = "store"
    item_ids: list[str] = Field(default_factory=list)
    price_min_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    price_max_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    start_date: date | None = None
    end_date: date | None = None
    confirm_all_dates: bool = False

    @field_validator("source_account_ref", "store_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("item_ids", mode="before")
    @classmethod
    def normalize_item_ids(cls, value: object) -> list[str]:
        return _split_text_values(value)

    @model_validator(mode="after")
    def validate_range(self) -> StoreCommissionRecalculateRequest:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be greater than or equal to start_date")
        if (self.start_date is None or self.end_date is None) and not self.confirm_all_dates:
            raise ValueError("confirm_all_dates is required when date range is omitted")
        if self.rule_scope == "item" and not self.item_ids:
            raise ValueError("item_ids is required when recalculating item rules")
        return self


class StoreCommissionDeactivateRequest(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    rule_id: str = Field(min_length=1)

    @field_validator("source_account_ref", "rule_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class StoreCommissionRecalculateData(BaseModel):
    operation_id: str
    source_account_ref: str
    store_id: str
    rule_scope: CommissionRuleScope
    item_ids: list[str]
    status: BusinessRuleOperationStatus
    message: str


class StoreCommissionOperationLogData(BaseModel):
    items: list[BusinessRuleOperationRead]
