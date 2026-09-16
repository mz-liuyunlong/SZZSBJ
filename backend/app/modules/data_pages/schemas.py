from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    SerializationInfo,
    StringConstraints,
    field_validator,
)

Nonblank128 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


def _api_decimal(value: Decimal, info: SerializationInfo) -> str:
    if info.context and info.context.get("preserve_decimal_places"):
        return format(value, "f")
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


Money = Annotated[
    Decimal,
    Field(max_digits=18, decimal_places=4),
    PlainSerializer(_api_decimal, return_type=str, when_used="json"),
]
Ratio = Annotated[
    Decimal,
    Field(max_digits=18, decimal_places=6),
    PlainSerializer(_api_decimal, return_type=str, when_used="json"),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)

    @field_validator("start_date", "end_date", check_fields=False)
    @classmethod
    def normalize_date(cls, value: date | None) -> date | None:
        return value


class DailySalesQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    platform: Nonblank128 | None = None
    store_id: Nonblank128 | None = None
    owner_ref: Nonblank128 | None = None
    search_field: Literal["sku", "msku", "item_id", "product_name"] = "sku"
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class DailySalesTrendPointRead(StrictSchema):
    date: date
    sales_qty: Money


class DailySalesItemRead(StrictSchema):
    id: str
    business_date_la: date
    business_timezone: str
    store_id: str
    store_name: str | None
    owner_ref: str | None
    item_id: str
    msku: str | None
    local_sku: str | None
    local_name: str | None
    title: str | None
    picture_url: str | None
    platform_code: str | None
    sales_qty: Money
    order_count: Money
    sales_amount: Money
    sales_currency_code: str | None
    sample_amount: Money | None
    sales_amount_excluding_sample: Money | None
    return_qty: Money | None
    refund_amount: Money | None
    refund_currency_code: str | None
    return_rate_30d: Ratio | None
    ad_spend_amount: Money | None
    ad_spend_currency_code: str | None
    ad_ratio: Ratio | None
    wfs_available_quantity: Money | None
    wfs_fee_unit_amount: Money | None
    wfs_fee_total_amount: Money | None
    wfs_fee_currency_code: str | None
    purchase_cost_unit_cny: Money | None
    purchase_cost_total_usd: Money | None
    first_leg_cost_unit_cny: Money | None
    first_leg_cost_total_usd: Money | None
    storage_fee_unit_amount: Money | None
    storage_fee_total_amount: Money | None
    storage_fee_currency_code: str | None
    commission_rate: Ratio | None
    commission_fee_amount: Money | None
    commission_fee_currency_code: str | None
    gross_profit_amount: Money | None
    gross_profit_currency_code: str | None
    gross_margin: Ratio | None
    roi: Ratio | None
    cost_status: Literal["complete", "partial", "missing"]
    missing_cost_codes: list[str]
    sales_7d_trend: list[DailySalesTrendPointRead]
    calc_version: str
    calculated_at: datetime


class DailySalesListData(StrictSchema):
    items: list[DailySalesItemRead]


class DailySalesReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    latest_calculated_at: datetime | None = None
    page: int
    page_size: int
    total: int
    partial: bool = False
    input_missing: bool = False
