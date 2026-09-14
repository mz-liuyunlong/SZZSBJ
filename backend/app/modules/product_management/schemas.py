from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    SerializationInfo,
    StringConstraints,
    field_validator,
    model_validator,
)

Nonblank64 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Nonblank128 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
SkuSearchValue = Annotated[str, StringConstraints(min_length=1, max_length=128)]


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
    Field(max_digits=9, decimal_places=6),
    PlainSerializer(_api_decimal, return_type=str, when_used="json"),
]
DecimalSix = Annotated[
    Decimal,
    Field(max_digits=18, decimal_places=6),
    PlainSerializer(_api_decimal, return_type=str, when_used="json"),
]
RootMissingCode = Literal[
    "missing_purchase_cost",
    "missing_gross_weight",
    "missing_package_dimensions",
    "missing_dimension_image",
    "invalid_pricing_rule",
]

PRODUCT_MANAGEMENT_COLUMNS = frozenset(
    {
        "image",
        "sku",
        "productName",
        "tags",
        "sourceTags",
        "productGrade",
        "wfsFee",
        "suggestedPrice",
        "minimumPrice",
        "clearancePrice",
        "category",
        "purchasePrice",
        "firstLegFreight",
        "wfsDeliveryFee",
        "purchaseLeadTime",
        "storageFee",
        "linkedPlatformSkuCount",
        "dataCompleteness",
        "updatedAt",
    }
)
DEFAULT_PRODUCT_MANAGEMENT_COLUMNS = (
    "image",
    "sku",
    "productName",
    "category",
    "purchasePrice",
    "firstLegFreight",
    "purchaseLeadTime",
    "dataCompleteness",
    "updatedAt",
)


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)

    @field_validator(
        "amount",
        "min_weight_kg",
        "max_weight_kg",
        "max_longest_side_cm",
        "monthly_rate_usd_per_cuft",
        "other_fixed_cost_cny",
        "usd_cny_rate",
        "platform_commission_rate",
        "first_leg_cost_per_kg_cny",
        "suggested_gross_margin_rate",
        "minimum_gross_margin_rate",
        "clearance_gross_margin_rate",
        "grade_a_min_margin_rate",
        "grade_a_min_roi",
        "grade_b_min_margin_rate",
        "grade_b_min_roi",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_binary_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("decimal values must use decimal strings")
        return value

    @field_validator(
        "effective_from",
        "effective_to",
        "wfs_confirmed_at",
        "effective_at",
        check_fields=False,
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("datetime values must include a timezone")
        return value


class ProductManagementReadMeta(StrictSchema):
    source: Literal["new_system_postgresql"] = "new_system_postgresql"
    source_objects: list[str]
    list_freshness_at: datetime | None = None
    latest_observed_at: datetime | None = None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
    stale: bool | None = None
    partial: bool = False
    input_missing: bool = False


class ProductManagementFilterQuery(StrictSchema):
    sku: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
        | None
    ) = None
    sku_batch: list[SkuSearchValue] = Field(default_factory=list, max_length=1000)
    product_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
        | None
    ) = None
    category: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
        | None
    ) = None
    internal_tag: Nonblank128 | None = None
    product_grade: Literal["A", "B", "C", "exception"] | None = None
    calculation_status: Nonblank64 | None = None

    @field_validator("sku_batch", mode="before")
    @classmethod
    def normalize_sku_batch(cls, value: object) -> object:
        if value is None:
            return []
        raw_values = [value] if isinstance(value, str) else value
        if not isinstance(raw_values, (list, tuple)):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            if not isinstance(raw, str):
                return value
            for line in raw.splitlines():
                sku = line.strip()
                if not sku:
                    continue
                if len(sku) > 128:
                    raise ValueError("each batch SKU must be at most 128 characters")
                if sku not in seen:
                    seen.add(sku)
                    normalized.append(sku)
                if len(normalized) > 1000:
                    raise ValueError("batch SKU search accepts at most 1000 values")
        if raw_values and not normalized:
            raise ValueError("batch SKU search must contain a nonblank value")
        return normalized

    @model_validator(mode="after")
    def validate_sku_filters(self) -> Self:
        if self.sku is not None and self.sku_batch:
            raise ValueError("sku and sku_batch are mutually exclusive")
        return self


class ProductManagementListQuery(ProductManagementFilterQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["sku", "product_name", "product_grade", "calculated_at"] = "sku"
    sort_order: Literal["asc", "desc"] = "asc"


class ProductManagementSummaryQuery(ProductManagementFilterQuery):
    pass


class InternalTagRead(StrictSchema):
    key: str
    label: str
    color: str | None


class SourceTagRead(StrictSchema):
    source_tag_id: str | None
    label: str | None
    color: str | None


class ProductManagementListItem(StrictSchema):
    sku_id: UUID
    sku: str | None
    product_name: str | None
    primary_image: str | None
    internal_tags: list[InternalTagRead]
    source_tags: list[SourceTagRead]
    category: str | None
    purchase_cost_cny: Money | None
    unit_first_leg_cost: Money | None
    unit_first_leg_currency_code: str | None
    purchase_delivery_days: int | None
    data_quality_score: DecimalSix | None
    linked_platform_sku_count: int
    source_observed_at: datetime | None
    product_grade: Literal["A", "B", "C", "exception"] | None
    grade_reason: str | None
    wfs_fulfillment_fee: Money | None
    wfs_fulfillment_fee_currency_code: Literal["USD", "CNY"] | None
    wfs_daily_storage_fee: Money | None
    wfs_daily_storage_fee_currency_code: Literal["USD"] | None
    suggested_price_usd: Money | None
    minimum_price_usd: Money | None
    clearance_price_usd: Money | None
    price_currency_code: Literal["USD"] | None
    calculation_status: str | None
    calculated_at: datetime | None
    rule_version: str | None
    costs_visible: bool
    image_count: int = 0
    product_gross_weight_g: Money | None = None
    gross_weight_kg: DecimalSix | None = None
    package_length_cm: Money | None = None
    package_width_cm: Money | None = None
    package_height_cm: Money | None = None
    first_leg_volume_weight_kg: DecimalSix | None = None
    first_leg_chargeable_weight_kg: DecimalSix | None = None
    first_leg_fee_cny: Money | None = None
    wfs_actual_weight_lb: DecimalSix | None = None
    wfs_dimensional_weight_lb: DecimalSix | None = None
    wfs_chargeable_weight_lb: DecimalSix | None = None
    wfs_base_fee_usd: Money | None = None
    fixed_cost_usd: Money | None = None
    storage_fee_usd: Money | None = None
    root_missing_codes: list[RootMissingCode] = Field(default_factory=list)
    pricing_available: bool = False
    billing_root_complete: bool = False
    wfs_calc_status: str | None = None
    wfs_calc_reason: str | None = None
    storage_calc_status: str | None = None
    first_leg_calc_status: str | None = None
    formula_version: str | None = None
    wfs_formula_version: str | None = None


class ProductManagementListData(StrictSchema):
    items: list[ProductManagementListItem]


class ProductManagementSummaryData(StrictSchema):
    total: int
    synced_detail_count: int
    data_completeness_rate: DecimalSix
    with_image_count: int
    with_source_tag_count: int
    incomplete_count: int
    missing_purchase_cost_count: int = 0
    missing_gross_weight_count: int = 0
    missing_package_dimensions_count: int = 0
    missing_dimension_image_count: int = 0
    invalid_pricing_rule_count: int = 0
    pricing_ok_count: int = 0


class ProductCoreRead(StrictSchema):
    product_id: UUID
    sku: str
    product_name: str
    category: str | None
    product_type: str | None
    status: str | None
    manual_grade: str | None


class SyncedProductDetailRead(StrictSchema):
    product_name: str | None
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


class ProductImageRead(StrictSchema):
    ordinal: int
    url: str
    is_primary: bool | None
    source: Literal["picture_list"] = "picture_list"


class CostComponentRead(StrictSchema):
    name: Literal[
        "purchase_cost",
        "first_leg",
        "wfs_fulfillment",
        "estimated_storage",
        "other_fixed_cost",
        "commission",
    ]
    amount: Money | None
    currency: Literal["USD", "CNY"] | None
    source: Literal[
        "lingxing_detail",
        "pricing_rule_config",
        "wfs_rate_config",
        "storage_rate_config",
        "manual_override",
        "calculated",
        "default_zero",
        "missing",
    ]
    included: bool
    status: Literal["ok", "not_included", "missing", "needs_confirm", "not_calculated"]
    reason: Nonblank128 | None = None


class PricingBreakdownRead(StrictSchema):
    sku_id: UUID
    calculation_status: str
    wfs_calc_status: str
    wfs_calc_reason: str | None
    wfs_fee_source: str
    storage_calc_status: str
    first_leg_calc_status: str
    product_grade: Literal["A", "B", "C", "exception"]
    grade_reason: str
    commission_source: str
    rule_version: str
    calc_version: str
    pricing_effective_at: datetime
    calculated_at: datetime
    wfs_fulfillment_fee_usd: Money | None
    wfs_fulfillment_fee_cny: Money | None
    package_volume_cuft: DecimalSix | None
    daily_storage_fee_per_unit_usd: Money | None
    daily_storage_fee_per_unit_cny: Money | None
    estimated_storage_fee_usd: Money | None
    estimated_storage_fee_cny: Money | None
    suggested_price_usd: Money | None
    minimum_price_usd: Money | None
    clearance_price_usd: Money | None
    price_currency_code: Literal["USD"] | None
    suggested_gross_margin_rate: Ratio | None
    suggested_roi: DecimalSix | None
    components: Annotated[list[CostComponentRead], Field(min_length=6, max_length=6)] | None
    purchase_cost_cny: Money | None = None
    purchase_cost_currency_code: Literal["CNY"] | None = None
    product_gross_weight_g: Money | None = None
    gross_weight_kg: DecimalSix | None = None
    package_length_cm: Money | None = None
    package_width_cm: Money | None = None
    package_height_cm: Money | None = None
    first_leg_volume_weight_kg: DecimalSix | None = None
    first_leg_chargeable_weight_kg: DecimalSix | None = None
    first_leg_cost_per_kg_cny: Money | None = None
    first_leg_fee_cny: Money | None = None
    wfs_actual_weight_lb: DecimalSix | None = None
    wfs_dimensional_weight_lb: DecimalSix | None = None
    wfs_chargeable_weight_lb: DecimalSix | None = None
    wfs_weight_padding_lb: DecimalSix | None = None
    wfs_base_fee_usd: Money | None = None
    storage_fee_usd: Money | None = None
    fixed_cost_usd: Money | None = None
    usd_cny_rate: DecimalSix | None = None
    commission_rate: Ratio | None = None
    after_sales_rate: Ratio | None = None
    ad_cost_rate: Ratio | None = None
    suggested_margin_rate: Ratio | None = None
    minimum_margin_rate: Ratio | None = None
    root_missing_codes: list[RootMissingCode] = Field(default_factory=list)
    pricing_available: bool = False
    billing_root_complete: bool = False
    detail_messages: list[str] = Field(default_factory=list)
    formula_version: str | None = None
    wfs_formula_version: str | None = None


class ProductManagementDetailData(StrictSchema):
    sku_id: UUID
    core: ProductCoreRead | None
    synced_detail: SyncedProductDetailRead | None
    images: list[ProductImageRead]
    source_tags: list[SourceTagRead]
    internal_tags: list[InternalTagRead]
    pricing: PricingBreakdownRead | None


class ProductManagementOptionsData(StrictSchema):
    product_grades: list[str]
    calculation_statuses: list[str]
    internal_tags: list[InternalTagRead]


class ExportRequest(StrictSchema):
    query: ProductManagementListQuery = Field(default_factory=ProductManagementListQuery)
    max_rows: int = Field(default=5000, ge=1, le=5000)


class ExportResult(StrictSchema):
    status: Literal["not_implemented_safe"] = "not_implemented_safe"
    row_limit: int
    file_created: Literal[False] = False


class WfsFulfillmentRateConfig(StrictSchema):
    rate_key: Nonblank64
    market: Literal["US"] = "US"
    amount: Money = Field(ge=0)
    currency_code: Literal["USD", "CNY"]
    unit: Literal["per_unit"] = "per_unit"
    min_weight_kg: Money | None = Field(default=None, ge=0)
    max_weight_kg: Money | None = Field(default=None, gt=0)
    max_longest_side_cm: Money | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if (
            self.min_weight_kg is not None
            and self.max_weight_kg is not None
            and self.min_weight_kg > self.max_weight_kg
        ):
            raise ValueError("min_weight_kg must not exceed max_weight_kg")
        return self


class WfsStorageRateConfig(StrictSchema):
    rate_key: Nonblank64
    market: Literal["US"] = "US"
    monthly_rate_usd_per_cuft: Money = Field(ge=0)
    currency_code: Literal["USD"] = "USD"
    unit: Literal["cuft_month"] = "cuft_month"
    month_start: int = Field(default=1, ge=1, le=12)
    month_end: int = Field(default=12, ge=1, le=12)

    @model_validator(mode="after")
    def validate_months(self) -> Self:
        if self.month_start > self.month_end:
            raise ValueError("month_start must not exceed month_end")
        return self


class IdentityWfsOverrideConfig(StrictSchema):
    identity_id: UUID
    amount: Money = Field(ge=0)
    currency_code: Literal["USD", "CNY"]
    is_active: bool = True


class PricingRuleWrite(StrictSchema):
    source_account_ref: Nonblank128
    version: Nonblank64
    effective_from: datetime
    effective_to: datetime | None = None
    wfs_source_url: Literal["https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"]
    wfs_confirmed_at: datetime
    wfs_confirmed_by: Nonblank128
    wfs_fulfillment_rates: list[WfsFulfillmentRateConfig] = Field(
        default_factory=list, max_length=500
    )
    wfs_storage_rates: list[WfsStorageRateConfig] = Field(default_factory=list, max_length=50)
    identity_wfs_overrides: list[IdentityWfsOverrideConfig] = Field(
        default_factory=list, max_length=500
    )
    storage_month_basis_days: int = Field(default=30, ge=1, le=366)
    pricing_storage_days: int = Field(default=30, ge=0, le=366)
    include_first_leg_fee: bool = True
    include_wfs_fulfillment_fee: bool = True
    include_storage_fee: bool = True
    other_fixed_cost_cny: Money = Field(default=Decimal("0"), ge=0)
    usd_cny_rate: Money | None = Field(default=None, gt=0)
    fx_date: date | None = None
    fx_source: Nonblank128 | None = None
    platform_commission_rate: Ratio | None = Field(default=None, ge=0, lt=1)
    first_leg_cost_per_kg_cny: Money = Field(default=Decimal("12.00"), ge=0)
    suggested_gross_margin_rate: Ratio = Field(default=Decimal("0.20"), ge=0, lt=1)
    minimum_gross_margin_rate: Ratio = Field(default=Decimal("0.10"), ge=0, lt=1)
    clearance_gross_margin_rate: Ratio = Field(default=Decimal("0.00"), ge=0, lt=1)
    roi_base: Literal["purchase_cost", "total_cost"] = "purchase_cost"
    grade_a_min_margin_rate: Ratio = Field(default=Decimal("0.20"))
    grade_a_min_roi: Ratio = Field(default=Decimal("1.00"))
    grade_b_min_margin_rate: Ratio = Field(default=Decimal("0.10"))
    grade_b_min_roi: Ratio = Field(default=Decimal("0.50"))
    rounding_mode: Literal["none"] = "none"
    change_reason: Reason
    approval_ref: Nonblank128

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        if self.effective_to is not None:
            raise ValueError("new active rule versions must be open-ended")
        if not (
            self.suggested_gross_margin_rate
            >= self.minimum_gross_margin_rate
            >= self.clearance_gross_margin_rate
        ):
            raise ValueError("target margins must be ordered")
        if (self.fx_date is None) != (self.fx_source is None):
            raise ValueError("fx_date and fx_source must be provided together")
        if (
            self.grade_a_min_margin_rate < self.grade_b_min_margin_rate
            or self.grade_a_min_roi < self.grade_b_min_roi
        ):
            raise ValueError("grade A thresholds must not be lower than grade B thresholds")
        identities = [item.identity_id for item in self.identity_wfs_overrides if item.is_active]
        if len(identities) != len(set(identities)):
            raise ValueError("active identity WFS overrides must be unique")
        rate_keys = [item.rate_key for item in self.wfs_fulfillment_rates]
        storage_keys = [item.rate_key for item in self.wfs_storage_rates]
        if len(rate_keys) != len(set(rate_keys)) or len(storage_keys) != len(set(storage_keys)):
            raise ValueError("rate keys must be unique")
        return self


class PricingRuleRead(PricingRuleWrite):
    id: UUID
    rule_key: str
    is_active: bool
    approved_by: str
    approved_at: datetime
    actor_ref: str
    request_id: str
    action: Literal["publish_pricing_rule"]
    status: Literal["succeeded"]
    created_at: datetime
    updated_at: datetime


class PricingRulesData(StrictSchema):
    items: list[PricingRuleRead]
    active_rule_id: UUID | None


class RecalculatePricingRequest(StrictSchema):
    source_account_ref: Nonblank128
    scope: Literal["all", "selected", "missing_price", "pricing_failed"]
    sku_ids: list[UUID] = Field(default_factory=list, max_length=100)
    rule_version_id: UUID | None = None
    effective_at: datetime | None = None
    reason: Reason
    idempotency_key: Nonblank128
    preview_only: bool = True
    max_items: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.scope == "selected" and not self.sku_ids:
            raise ValueError("selected scope requires sku_ids")
        if self.scope != "selected" and self.sku_ids:
            raise ValueError("sku_ids are only allowed for selected scope")
        if len(self.sku_ids) != len(set(self.sku_ids)):
            raise ValueError("sku_ids must be unique")
        return self


class RecalculatePricingResult(StrictSchema):
    run_id: UUID
    mode: Literal["preview", "execute"]
    status: Literal["running", "previewed", "succeeded", "partial", "no_items", "failed"]
    matched_count: int
    eligible_count: int
    skipped_count: int
    estimated_affected_count: int
    affected_count: int
    failed_count: int
    idempotent_replay: bool


class UserTableViewWrite(StrictSchema):
    applied_column_keys: list[str] = Field(max_length=len(PRODUCT_MANAGEMENT_COLUMNS))
    column_widths: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        if len(self.applied_column_keys) != len(set(self.applied_column_keys)):
            raise ValueError("applied_column_keys must be unique")
        if not set(self.applied_column_keys) <= PRODUCT_MANAGEMENT_COLUMNS:
            raise ValueError("unknown product management column")
        if not set(self.column_widths) <= PRODUCT_MANAGEMENT_COLUMNS:
            raise ValueError("unknown product management column width")
        if any(width < 48 or width > 800 for width in self.column_widths.values()):
            raise ValueError("column width is outside the allowed range")
        return self


class UserTableViewRead(UserTableViewWrite):
    schema_version: int
    view_key: str
    updated_at: datetime | None
