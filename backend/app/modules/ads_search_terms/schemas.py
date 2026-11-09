from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        hide_input_in_errors=True,
    )


class SearchTermQuery(StrictSchema):
    start_date: date
    end_date: date
    store_ids: list[str] = Field(default_factory=list, max_length=100)
    advertiser_ids: list[str] = Field(default_factory=list, max_length=100)
    campaign_ids: list[str] = Field(default_factory=list, max_length=500)
    targeting_type: Literal["all", "auto", "manual"] = "all"
    query: str = Field(default="", max_length=256)
    conversion_state: Literal["all", "orders", "no_orders"] = "all"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class SearchTermRead(StrictSchema):
    id: UUID
    business_date_la: date
    source_account_ref: str
    advertiser_id: str
    store_id: str | None
    item_id: str | None
    listing_mapping_status: str
    mp_seller_name: str | None
    mp_advertiser_name: str | None
    campaign_id: str
    campaign_name: str | None
    targeting_type: str
    searched_keyword: str
    num_ads_shown: int | None
    num_ads_clicks: int | None
    ad_spend_amount: Decimal | None
    attributed_orders: Decimal | None
    advertised_sku_sales_amount: Decimal | None
    other_sku_sales_amount: Decimal | None
    cpc: Decimal | None
    ctr: Decimal | None
    cvr: Decimal | None
    attribution_days: int
    synced_at: datetime


class SearchTermListData(StrictSchema):
    items: list[SearchTermRead]
    total: int
    page: int
    page_size: int
    view: Literal["summary", "detail"] = "detail"


class SearchTermSummaryData(StrictSchema):
    total_terms: int
    converting_terms: int
    auto_converting_not_manually_covered: int
    no_order_terms_with_spend: int
    ad_spend_total: Decimal
    attributed_orders_total: Decimal
    direct_sales_total: Decimal
    other_sales_total: Decimal
    freshness_at: datetime | None
    mapping_unresolved_count: int
    manual_keyword_data_available: bool


class SearchTermTrendPoint(StrictSchema):
    business_date_la: date
    impressions: int
    clicks: int
    spend: Decimal
    orders: Decimal
    direct_sales: Decimal
    other_sales: Decimal


class SearchTermTrendData(StrictSchema):
    items: list[SearchTermTrendPoint]
    date_grain: Literal["daily_snapshot"] = "daily_snapshot"


class ActionCreate(StrictSchema):
    source_fact_id: UUID | None = None
    source_account_ref: str = Field(min_length=1, max_length=128)
    action_type: Literal["add_keyword", "add_negative_keyword"]
    search_term: str = Field(min_length=1, max_length=256)
    target_scope: dict[str, object]
    reason: str = Field(default="", max_length=1000)


class ActionComplete(StrictSchema):
    completion_note: str = Field(min_length=1, max_length=1000)


class ActionRead(StrictSchema):
    id: UUID
    source_account_ref: str
    source_fact_id: UUID | None
    action_type: str
    search_term: str
    target_scope_json: dict[str, object]
    status: str
    effect_status: str
    reason: str
    created_by: str
    completed_by: str | None
    completion_note: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionListData(StrictSchema):
    items: list[ActionRead]
    total: int


class SearchTermAggregateRead(StrictSchema):
    normalized_search_term: str
    searched_keyword: str
    has_auto: bool
    has_manual: bool
    store_count: int
    listing_count: int
    campaign_count: int
    impressions: int
    clicks: int
    spend: Decimal
    orders: Decimal
    direct_sales: Decimal
    other_sales: Decimal
    auto_orders: Decimal
    manual_orders: Decimal
    manual_covered_same_store: bool
    manual_covered_other_store: bool
    manual_keyword_data_available: bool
    freshness_at: datetime | None


class SearchTermAggregateListData(StrictSchema):
    items: list[SearchTermAggregateRead]
    total: int
    page: int
    page_size: int
