from __future__ import annotations

from app.modules.product_management.schemas import (
    ExportRequest,
    PricingBreakdownRead,
    ProductManagementDetailData,
    ProductManagementListData,
    ProductManagementListItem,
)

PURCHASE_COST_PERMISSION = "field:products:product-management:purchase-cost"
LOGISTICS_COST_PERMISSION = "field:products:product-management:logistics-cost"

_BASE_EXPORT_COLUMNS = (
    "sku",
    "product_name",
    "category",
    "product_grade",
    "owner",
    "developer",
    "tags",
    "source_tags",
    "image_count",
    "listing_count",
    "completeness_status",
    "missing_codes",
    "calculation_status",
    "wfs_status",
    "storage_status",
    "first_leg_status",
    "observed_at",
    "calculated_at",
)
_PURCHASE_EXPORT_COLUMNS = ("purchase_cost_cny",)
_LOGISTICS_EXPORT_COLUMNS = (
    "first_leg_fee_cny",
    "wfs_fulfillment_fee",
    "storage_fee_usd",
)
_DERIVED_EXPORT_COLUMNS = (
    "suggested_price_usd",
    "minimum_price_usd",
    "clearance_price_usd",
)


def filter_export_request(
    payload: ExportRequest,
    *,
    can_view_purchase_cost: bool,
    can_view_logistics_cost: bool,
) -> ExportRequest:
    allowed = list(_BASE_EXPORT_COLUMNS)
    if can_view_purchase_cost:
        allowed.extend(_PURCHASE_EXPORT_COLUMNS)
    if can_view_logistics_cost:
        allowed.extend(_LOGISTICS_EXPORT_COLUMNS)
    if can_view_purchase_cost and can_view_logistics_cost:
        allowed.extend(_DERIVED_EXPORT_COLUMNS)

    requested = payload.columns or allowed
    allowed_set = set(allowed)
    return payload.model_copy(
        update={"columns": [key for key in requested if key in allowed_set]},
    )


def filter_list_item(
    item: ProductManagementListItem,
    *,
    can_view_purchase_cost: bool,
    can_view_logistics_cost: bool,
) -> ProductManagementListItem:
    updates: dict[str, object] = {
        "costs_visible": can_view_purchase_cost or can_view_logistics_cost,
    }
    if not can_view_purchase_cost:
        updates["purchase_cost_cny"] = None
    if not can_view_logistics_cost:
        updates.update(
            {
                "unit_first_leg_cost": None,
                "unit_first_leg_currency_code": None,
                "wfs_fulfillment_fee": None,
                "wfs_fulfillment_fee_currency_code": None,
                "wfs_daily_storage_fee": None,
                "wfs_daily_storage_fee_currency_code": None,
                "first_leg_fee_cny": None,
                "wfs_base_fee_usd": None,
                "storage_fee_usd": None,
            }
        )
    if not (can_view_purchase_cost and can_view_logistics_cost):
        updates.update(
            {
                "suggested_price_usd": None,
                "minimum_price_usd": None,
                "clearance_price_usd": None,
                "price_currency_code": None,
                "fixed_cost_usd": None,
            }
        )
    return item.model_copy(update=updates)


def filter_list_data(
    data: ProductManagementListData,
    *,
    can_view_purchase_cost: bool,
    can_view_logistics_cost: bool,
) -> ProductManagementListData:
    return data.model_copy(
        update={
            "items": [
                filter_list_item(
                    item,
                    can_view_purchase_cost=can_view_purchase_cost,
                    can_view_logistics_cost=can_view_logistics_cost,
                )
                for item in data.items
            ]
        }
    )


def filter_pricing_breakdown(
    pricing: PricingBreakdownRead,
    *,
    can_view_purchase_cost: bool,
    can_view_logistics_cost: bool,
) -> PricingBreakdownRead:
    updates: dict[str, object] = {}
    if not can_view_purchase_cost:
        updates.update(
            {
                "purchase_cost_cny": None,
                "purchase_cost_currency_code": None,
            }
        )
    if not can_view_logistics_cost:
        updates.update(
            {
                "wfs_fulfillment_fee_usd": None,
                "wfs_fulfillment_fee_cny": None,
                "daily_storage_fee_per_unit_usd": None,
                "daily_storage_fee_per_unit_cny": None,
                "estimated_storage_fee_usd": None,
                "estimated_storage_fee_cny": None,
                "first_leg_cost_per_kg_cny": None,
                "first_leg_fee_cny": None,
                "wfs_base_fee_usd": None,
                "storage_fee_usd": None,
            }
        )
    if not (can_view_purchase_cost and can_view_logistics_cost):
        updates.update(
            {
                "suggested_price_usd": None,
                "minimum_price_usd": None,
                "clearance_price_usd": None,
                "price_currency_code": None,
                "suggested_gross_margin_rate": None,
                "suggested_roi": None,
                "fixed_cost_usd": None,
                "usd_cny_rate": None,
                "components": None,
            }
        )
    return pricing.model_copy(update=updates)


def filter_detail_data(
    data: ProductManagementDetailData,
    *,
    can_view_purchase_cost: bool,
    can_view_logistics_cost: bool,
) -> ProductManagementDetailData:
    if data.pricing is None:
        return data
    return data.model_copy(
        update={
            "pricing": filter_pricing_breakdown(
                data.pricing,
                can_view_purchase_cost=can_view_purchase_cost,
                can_view_logistics_cost=can_view_logistics_cost,
            )
        }
    )
