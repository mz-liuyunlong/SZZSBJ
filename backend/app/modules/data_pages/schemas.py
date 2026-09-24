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


class DataPageFilterOptionRead(StrictSchema):
    value: str
    label: str
    count: int = 0


class DataPageFilterOptionsData(StrictSchema):
    platforms: list[DataPageFilterOptionRead] = Field(default_factory=list)
    owners: list[DataPageFilterOptionRead] = Field(default_factory=list)
    stores: list[DataPageFilterOptionRead] = Field(default_factory=list)


class DailySalesQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    platform: Nonblank128 | None = None
    store_id: Nonblank128 | None = None
    owner_ref: Nonblank128 | None = None
    search_field: Literal["sku", "msku", "item_id", "product_name"] = "sku"
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    batch_values: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=32768),
    ] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)


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
    gross_sales_qty: Money = Decimal("0")
    gross_order_count: Money = Decimal("0")
    gross_sales_amount: Money = Decimal("0")
    sample_order_count: Money = Decimal("0")
    sample_qty: Money = Decimal("0")
    cost_quantity: Money = Decimal("0")
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
    wfs_fee_expected_unit_amount: Money | None = None
    wfs_fee_expected_total_amount: Money | None = None
    wfs_fee_actual_total_amount: Money | None = None
    wfs_fee_variance_amount: Money | None = None
    wfs_fee_variance_rate: Ratio | None = None
    wfs_fee_source: str | None = None
    purchase_cost_unit_cny: Money | None
    purchase_cost_total_usd: Money | None
    purchase_cost_estimated_total_usd: Money | None = None
    purchase_cost_actual_total_usd: Money | None = None
    purchase_cost_source: str | None = None
    first_leg_cost_unit_cny: Money | None
    first_leg_cost_total_usd: Money | None
    first_leg_cost_estimated_total_usd: Money | None = None
    first_leg_cost_actual_total_usd: Money | None = None
    first_leg_cost_source: str | None = None
    storage_fee_unit_amount: Money | None
    storage_fee_total_amount: Money | None
    storage_fee_currency_code: str | None
    storage_fee_estimated_total_amount: Money | None = None
    storage_fee_actual_total_amount: Money | None = None
    storage_fee_source: str | None = None
    exchange_rate: Ratio | None = None
    fx_date: date | None = None
    fx_source: str | None = None
    commission_rate: Ratio | None
    commission_fee_amount: Money | None
    commission_fee_currency_code: str | None
    commission_source: str | None = None
    gross_profit_amount: Money | None
    gross_profit_currency_code: str | None
    gross_margin: Ratio | None
    roi: Ratio | None
    cost_status: Literal["complete", "partial", "missing"]
    missing_cost_codes: list[str]
    calculation_warnings: list[str] = Field(default_factory=list)
    sales_7d_trend: list[DailySalesTrendPointRead]
    calc_version: str
    calculated_at: datetime


class DailySalesSummaryRead(StrictSchema):
    sales_qty: Money = Decimal("0")
    order_count: Money = Decimal("0")
    sales_amount: Money = Decimal("0")
    sales_currency_code: str | None = "USD"
    order_profit_amount: Money = Decimal("0")
    order_profit_currency_code: str | None = "USD"
    ad_spend_amount: Money = Decimal("0")
    ad_spend_currency_code: str | None = "USD"
    wfs_available_quantity: Money | None = None
    refund_event_qty: Money = Decimal("0")
    refund_event_amount: Money = Decimal("0")
    refund_event_currency_code: str | None = "USD"


class DailySalesListData(StrictSchema):
    items: list[DailySalesItemRead]
    summary: DailySalesSummaryRead = Field(default_factory=DailySalesSummaryRead)


class DailySalesReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    latest_calculated_at: datetime | None = None
    page: int
    page_size: int
    total: int
    partial: bool = False
    input_missing: bool = False


class OrderProfitQuery(StrictSchema):
    start_date: date | None = None
    end_date: date | None = None
    platform: Nonblank128 | None = None
    store_id: Nonblank128 | None = None
    owner_ref: Nonblank128 | None = None
    search_field: Literal["sku", "item_id", "product_name"] = "sku"
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)


class OrderProfitItemRead(StrictSchema):
    id: str
    business_date_la: date
    business_timezone: str
    local_sku: str
    item_ids: list[str]
    store_ids: list[str]
    store_count: int
    item_count: int
    sales_qty: Money
    order_count: Money
    sales_amount: Money
    sales_currency_code: str | None
    refund_amount: Money | None
    ad_spend_amount: Money | None
    commission_fee_amount: Money | None
    wfs_fee_total_amount: Money | None
    purchase_cost_total_usd: Money | None
    first_leg_cost_total_usd: Money | None
    storage_fee_total_amount: Money | None
    gross_profit_amount: Money | None
    gross_profit_currency_code: str | None
    gross_margin: Ratio | None
    roi: Ratio | None
    cost_status: Literal["complete", "partial", "missing"]
    missing_cost_codes: list[str]
    calc_version: str
    calculated_at: datetime


class OrderProfitSummaryRead(StrictSchema):
    sales_qty: Money = Decimal("0")
    order_count: Money = Decimal("0")
    sales_amount: Money = Decimal("0")
    sales_currency_code: str | None = "USD"
    refund_amount: Money = Decimal("0")
    refund_currency_code: str | None = "USD"
    order_profit_amount: Money = Decimal("0")
    order_profit_currency_code: str | None = "USD"
    ad_spend_amount: Money = Decimal("0")
    ad_spend_currency_code: str | None = "USD"


class OrderProfitTrendPointRead(StrictSchema):
    date: date
    sales_qty: Money = Decimal("0")
    order_count: Money = Decimal("0")
    sales_amount: Money = Decimal("0")
    sales_currency_code: str | None = "USD"
    refund_amount: Money = Decimal("0")
    refund_currency_code: str | None = "USD"
    order_profit_amount: Money = Decimal("0")
    order_profit_currency_code: str | None = "USD"
    profit_margin: Ratio | None = None
    ad_spend_amount: Money = Decimal("0")
    ad_spend_currency_code: str | None = "USD"
    ad_ratio: Ratio | None = None


class OrderProfitTrendData(StrictSchema):
    items: list[OrderProfitTrendPointRead]


class OrderProfitListData(StrictSchema):
    items: list[OrderProfitItemRead]
    summary: OrderProfitSummaryRead = Field(default_factory=OrderProfitSummaryRead)


class OrderProfitReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    latest_calculated_at: datetime | None = None
    page: int
    page_size: int
    total: int
    partial: bool = False
    input_missing: bool = False


class ListingManagementQuery(StrictSchema):
    store_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32768)] = ""
    owner_ref: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32768)] = ""
    product_type: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32768)] = ""
    status: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32768)] = ""
    tag: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32768)] = ""
    summary_filter: Literal[
        "total",
        "online",
        "offline",
        "buybox",
        "rating",
        "resold",
        "strike",
        "disabled",
    ] = "total"
    search_field: Literal["sku", "msku", "item_id", "title"] = "sku"
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)] = ""
    batch_values: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=32768),
    ] = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)


class ListingManagementItemRead(StrictSchema):
    id: str
    source_account_ref: str
    platform_code: str | None
    store_id: str
    store_name: str | None
    item_id: str
    msku: str | None
    local_sku: str | None
    local_name: str | None
    title: str | None
    picture_url: str | None
    item_url: str | None
    owner_ref: str | None
    owner_uid: str | None = None
    owner_name: str | None = None
    product_developer_uid: str | None = None
    product_developer_name: str | None = None
    product_grade: str | None
    tags: list[str]
    strike_price_amount: Money | None
    strike_price_currency_code: str | None
    sale_price_amount: Money | None
    sale_price_currency_code: str | None
    listing_status: str | None
    lifecycle_status: str | None
    listing_start_at_utc: datetime | None
    category: str | None
    wfs_available_quantity: Money | None
    available_quantity: Money | None
    inbound_quantity: Money | None
    sales_7d: Money
    sales_14d: Money
    sales_30d: Money
    ad_spend_30d_amount: Money | None
    ad_spend_currency_code: str | None
    buybox_status: str | None
    walmart_seller: str | None
    is_hijacked: bool | None
    average_rating: Ratio | None
    review_count: int | None
    brand: str | None
    disabled_reason: str | None
    wfs_fee_amount: Money | None
    wfs_fee_currency_code: str | None
    gtin: str | None
    upc: str | None
    calculated_at: datetime


class ListingManagementSummaryData(StrictSchema):
    total: int = 0
    online: int = 0
    buybox_exception: int = 0
    rating_warning: int = 0
    resold_warning: int = 0
    strike_price_exception: int = 0


class ListingManagementFilterOptionsData(StrictSchema):
    stores: list[DataPageFilterOptionRead] = Field(default_factory=list)
    owners: list[DataPageFilterOptionRead] = Field(default_factory=list)
    product_types: list[DataPageFilterOptionRead] = Field(default_factory=list)
    tags: list[DataPageFilterOptionRead] = Field(default_factory=list)


class ListingManagementListData(StrictSchema):
    items: list[ListingManagementItemRead]


class ListingManagementReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    latest_calculated_at: datetime | None = None
    page: int
    page_size: int
    total: int
    partial: bool = False
    input_missing: bool = False


class ListingTagRead(StrictSchema):
    id: str
    name: str
    color: str
    usage: int = 0
    sort_order: int = 0
    is_active: bool = True


class ListingTagListData(StrictSchema):
    items: list[ListingTagRead] = Field(default_factory=list)


class ListingTagCreateRequest(StrictSchema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]
    color: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    sort_order: int = 0


class ListingTagUpdateRequest(StrictSchema):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)] | None
    ) = None
    color: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)] | None
    ) = None
    sort_order: int | None = None
    is_active: bool | None = None


class ListingTagBatchSetRequest(StrictSchema):
    listing_ids: list[Nonblank128] = Field(min_length=1, max_length=1000)
    tag_ids: list[Nonblank128] = Field(default_factory=list, max_length=1000)
    tag_values: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]
    ] = Field(default_factory=list, max_length=1000)
    mode: Literal["replace", "append", "remove"] = "append"


class ListingTagBatchSetData(StrictSchema):
    updated_listings: int = 0
    tag_count: int = 0
    mode: Literal["replace", "append", "remove"]
