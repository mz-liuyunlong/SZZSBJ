from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

Money = Annotated[
    Decimal,
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


class SkuPageQuery(StrictSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SkuListQuery(SkuPageQuery):
    provider: Literal["lingxing"] = "lingxing"
    active: bool | None = None
    mapping_status: Literal["unmapped", "confirmed"] | None = None


class SkuReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    freshness_at: datetime | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class SkuListItem(StrictSchema):
    sku_id: UUID
    lingxing_sku_code: str | None
    product_name: str | None
    is_active: bool
    mapping_status: Literal["unmapped", "confirmed"]
    last_seen_at: datetime
    snapshot_at: datetime | None
    calculated_at: datetime | None


class SkuListData(StrictSchema):
    items: list[SkuListItem]


class SkuIdentityRead(StrictSchema):
    sku_id: UUID
    provider: str
    source_account_ref: str
    lingxing_sku_code: str | None
    mapping_status: Literal["unmapped", "confirmed"]
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime


class SkuImageRead(StrictSchema):
    ordinal: int
    pic_url: str
    is_primary: bool | None


class SkuTagRead(StrictSchema):
    ordinal: int
    global_tag_id: str | None
    tag_name: str | None
    color: str | None


class SkuNonCostDetail(StrictSchema):
    product_name: str | None
    lingxing_sku_code: str | None
    main_image_url: str | None
    purchase_delivery_days: int | None
    purchase_material: str | None
    customs_export_name_cn: str | None
    customs_import_name_en: str | None
    china_hs_code: str | None
    clearance_material_cn: str | None
    clearance_usage_cn: str | None
    clearance_material_en: str | None
    product_length_cm: Money | None
    product_width_cm: Money | None
    product_height_cm: Money | None
    product_net_weight_g: Money | None
    product_gross_weight_g: Money | None
    package_length_cm: Money | None
    package_width_cm: Money | None
    package_height_cm: Money | None
    box_length_cm: Money | None
    box_width_cm: Money | None
    box_height_cm: Money | None
    box_pcs: int | None
    box_weight_kg: Money | None
    source_observed_at: datetime


class SkuCostBlock(StrictSchema):
    purchase_cost_cny: Money | None
    purchase_cost_currency_code: str | None
    customs_declared_unit_price: Money | None
    customs_declared_currency: str | None
    us_first_leg_cost: Money | None
    us_first_leg_currency: str | None


class SkuProfileRead(StrictSchema):
    product_volume_cm3: Money | None
    package_volume_cm3: Money | None
    box_volume_cm3: Money | None
    box_volume_cbm: Money | None
    product_net_weight_kg: Money | None
    product_gross_weight_kg: Money | None
    unit_box_weight_kg: Money | None
    unit_first_leg_cost: Money | None
    unit_first_leg_currency: str | None
    has_customs_info: bool
    has_package_info: bool
    has_logistics_info: bool
    missing_fields: list[str]
    data_quality_score: Money
    calculated_at: datetime


class SkuDetailData(StrictSchema):
    identity: SkuIdentityRead
    detail: SkuNonCostDetail | None
    images: list[SkuImageRead]
    tags: list[SkuTagRead]
    profile: SkuProfileRead | None
    costs: SkuCostBlock | None


class SkuSyncHistoryItem(StrictSchema):
    run_id: UUID
    run_status: str
    trigger_type: str
    work_item_id: UUID
    work_item_status: str
    snapshot_id: UUID
    snapshot_at: datetime
    parser_version: str


class SkuSyncHistoryData(StrictSchema):
    items: list[SkuSyncHistoryItem]


class SkuLineageItem(StrictSchema):
    lineage_id: UUID
    raw_request_ref_id: UUID
    raw_blob_id: UUID
    source_path: str
    target_table: str
    target_field: str
    transform_key: str
    transform_version: str
    response_hash: str
    storage_mode: str
    received_at: datetime


class SkuLineageData(StrictSchema):
    items: list[SkuLineageItem]


class SkuPlatformListingItem(StrictSchema):
    id: UUID
    product_id: UUID
    platform: str
    store_name: str
    msku: str
    external_listing_id: str | None
    listing_status: str | None
    fulfillment_type: str | None


class SkuPlatformListingsData(StrictSchema):
    mapping_status: Literal["unmapped", "confirmed"]
    items: list[SkuPlatformListingItem]


class SkuCostHistoryItem(SkuCostBlock):
    snapshot_id: UUID
    source_run_id: UUID
    source_observed_at: datetime


class SkuCostHistoryData(StrictSchema):
    items: list[SkuCostHistoryItem]


class OperationLogQuery(SkuPageQuery):
    event_type: Annotated[str, StringConstraints(max_length=64)] | None = None


class SkuOperationLogItem(StrictSchema):
    event_id: int
    run_id: UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    message_code: str
    actor_ref: str | None
    request_id: str | None
    occurred_at: datetime


class SkuOperationLogsData(StrictSchema):
    items: list[SkuOperationLogItem]
