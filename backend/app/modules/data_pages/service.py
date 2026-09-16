from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    OrderProfitSkuDayMart,
)
from app.modules.data_pages.repository import (
    DailySalesRepository,
    ListingManagementRepository,
    OrderProfitRepository,
)
from app.modules.data_pages.schemas import (
    DailySalesItemRead,
    DailySalesListData,
    DailySalesQuery,
    DailySalesTrendPointRead,
    ListingManagementItemRead,
    ListingManagementListData,
    ListingManagementQuery,
    OrderProfitItemRead,
    OrderProfitListData,
    OrderProfitQuery,
)


def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _trend_points(value: object) -> list[DailySalesTrendPointRead]:
    if not isinstance(value, list):
        return []
    result: list[DailySalesTrendPointRead] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("date") or item.get("business_date")
        if raw_date is None:
            continue
        try:
            point_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        result.append(
            DailySalesTrendPointRead(
                date=point_date,
                sales_qty=_decimal(
                    item.get("sales_qty") or item.get("value") or item.get("quantity")
                ),
            )
        )
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("title")
            if label is not None and str(label).strip():
                tags.append(str(label).strip())
    return tags


class DailySalesService:
    """Read and shape the daily-sales MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = DailySalesRepository(session)

    def list_daily_sales(
        self,
        query: DailySalesQuery,
        account_refs: frozenset[str],
    ) -> tuple[DailySalesListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_daily_sales(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            DailySalesListData(items=[self._to_read(row) for row in rows]),
            total,
            latest_calculated_at,
        )

    def _to_read(self, row: DailySalesItemDayMart) -> DailySalesItemRead:
        return DailySalesItemRead(
            id=str(row.id),
            business_date_la=row.business_date_la,
            business_timezone=row.business_timezone,
            store_id=row.store_id,
            store_name=row.store_name,
            owner_ref=row.owner_ref,
            item_id=row.item_id,
            msku=row.msku,
            local_sku=row.local_sku,
            local_name=row.local_name,
            title=row.title,
            picture_url=row.picture_url,
            platform_code=row.platform_code,
            sales_qty=_decimal(row.sales_qty),
            order_count=_decimal(row.order_count),
            sales_amount=_decimal(row.sales_amount),
            sales_currency_code=row.sales_currency_code,
            sample_amount=row.sample_amount,
            sales_amount_excluding_sample=row.sales_amount_excluding_sample,
            return_qty=row.return_qty,
            refund_amount=row.refund_amount,
            refund_currency_code=row.refund_currency_code,
            return_rate_30d=row.return_rate_30d,
            ad_spend_amount=row.ad_spend_amount,
            ad_spend_currency_code=row.ad_spend_currency_code,
            ad_ratio=row.ad_ratio,
            wfs_available_quantity=row.wfs_available_quantity,
            wfs_fee_unit_amount=row.wfs_fee_unit_amount,
            wfs_fee_total_amount=row.wfs_fee_total_amount,
            wfs_fee_currency_code=row.wfs_fee_currency_code,
            purchase_cost_unit_cny=row.purchase_cost_unit_cny,
            purchase_cost_total_usd=row.purchase_cost_total_usd,
            first_leg_cost_unit_cny=row.first_leg_cost_unit_cny,
            first_leg_cost_total_usd=row.first_leg_cost_total_usd,
            storage_fee_unit_amount=row.storage_fee_unit_amount,
            storage_fee_total_amount=row.storage_fee_total_amount,
            storage_fee_currency_code=row.storage_fee_currency_code,
            commission_rate=row.commission_rate,
            commission_fee_amount=row.commission_fee_amount,
            commission_fee_currency_code=row.commission_fee_currency_code,
            gross_profit_amount=row.gross_profit_amount,
            gross_profit_currency_code=row.gross_profit_currency_code,
            gross_margin=row.gross_margin,
            roi=row.roi,
            cost_status=row.cost_status,
            missing_cost_codes=list(row.missing_cost_codes_json or []),
            sales_7d_trend=_trend_points(row.sales_7d_trend_json),
            calc_version=row.calc_version,
            calculated_at=row.calculated_at,
        )


class OrderProfitService:
    """Read and shape the order-profit MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = OrderProfitRepository(session)

    def list_order_profit(
        self,
        query: OrderProfitQuery,
        account_refs: frozenset[str],
    ) -> tuple[OrderProfitListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_order_profit(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            store_id=query.store_id,
            search_field=query.search_field,
            keyword=query.keyword,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            OrderProfitListData(items=[self._to_read(row) for row in rows]),
            total,
            latest_calculated_at,
        )

    def _to_read(self, row: OrderProfitSkuDayMart) -> OrderProfitItemRead:
        return OrderProfitItemRead(
            id=str(row.id),
            business_date_la=row.business_date_la,
            business_timezone=row.business_timezone,
            local_sku=row.local_sku,
            item_ids=_string_list(row.item_ids_json),
            store_ids=_string_list(row.store_ids_json),
            store_count=row.store_count,
            item_count=row.item_count,
            sales_qty=_decimal(row.sales_qty),
            order_count=_decimal(row.order_count),
            sales_amount=_decimal(row.sales_amount),
            sales_currency_code=row.sales_currency_code,
            refund_amount=row.refund_amount,
            ad_spend_amount=row.ad_spend_amount,
            commission_fee_amount=row.commission_fee_amount,
            wfs_fee_total_amount=row.wfs_fee_total_amount,
            purchase_cost_total_usd=row.purchase_cost_total_usd,
            first_leg_cost_total_usd=row.first_leg_cost_total_usd,
            storage_fee_total_amount=row.storage_fee_total_amount,
            gross_profit_amount=row.gross_profit_amount,
            gross_profit_currency_code=row.gross_profit_currency_code,
            gross_margin=row.gross_margin,
            roi=row.roi,
            cost_status=row.cost_status,
            missing_cost_codes=list(row.missing_cost_codes_json or []),
            calc_version=row.calc_version,
            calculated_at=row.calculated_at,
        )


class ListingManagementService:
    """Read and shape the listing-management MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = ListingManagementRepository(session)

    def list_listings(
        self,
        query: ListingManagementQuery,
        account_refs: frozenset[str],
    ) -> tuple[ListingManagementListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_listings(
            account_refs=account_refs,
            store_id=query.store_id,
            search_field=query.search_field,
            keyword=query.keyword,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            ListingManagementListData(items=[self._to_read(row) for row in rows]),
            total,
            latest_calculated_at,
        )

    def _to_read(self, row: ListingManagementCurrentMart) -> ListingManagementItemRead:
        return ListingManagementItemRead(
            id=str(row.id),
            source_account_ref=row.source_account_ref,
            platform_code=row.platform_code,
            store_id=row.store_id,
            store_name=row.store_name,
            item_id=row.item_id,
            msku=row.msku,
            local_sku=row.local_sku,
            local_name=row.local_name,
            title=row.title,
            picture_url=row.picture_url,
            item_url=row.item_url,
            owner_ref=row.owner_ref,
            product_grade=row.product_grade,
            tags=_tag_list(row.tags_json),
            strike_price_amount=row.strike_price_amount,
            strike_price_currency_code=row.strike_price_currency_code,
            sale_price_amount=row.sale_price_amount,
            sale_price_currency_code=row.sale_price_currency_code,
            listing_status=row.listing_status,
            lifecycle_status=row.lifecycle_status,
            listing_start_at_utc=row.listing_start_at_utc,
            category=row.category,
            wfs_available_quantity=row.wfs_available_quantity,
            available_quantity=row.available_quantity,
            inbound_quantity=row.inbound_quantity,
            sales_7d=_decimal(row.sales_7d),
            sales_14d=_decimal(row.sales_14d),
            sales_30d=_decimal(row.sales_30d),
            ad_spend_30d_amount=row.ad_spend_30d_amount,
            ad_spend_currency_code=row.ad_spend_currency_code,
            buybox_status=row.buybox_status,
            walmart_seller=row.walmart_seller,
            is_hijacked=row.is_hijacked,
            average_rating=row.average_rating,
            review_count=row.review_count,
            brand=row.brand,
            disabled_reason=row.disabled_reason,
            wfs_fee_amount=row.wfs_fee_amount,
            wfs_fee_currency_code=row.wfs_fee_currency_code,
            gtin=row.gtin,
            upc=row.upc,
            calculated_at=row.calculated_at,
        )
