from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart
from app.modules.data_pages.repository import DailySalesRepository
from app.modules.data_pages.schemas import (
    DailySalesItemRead,
    DailySalesListData,
    DailySalesQuery,
    DailySalesTrendPointRead,
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
