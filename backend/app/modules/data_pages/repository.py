from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    OrderProfitSkuDayMart,
)

DAILY_SALES_SEARCH_COLUMNS: dict[str, ColumnElement[str | None]] = {
    "sku": DailySalesItemDayMart.local_sku,
    "msku": DailySalesItemDayMart.msku,
    "item_id": DailySalesItemDayMart.item_id,
    "product_name": DailySalesItemDayMart.local_name,
}

ORDER_PROFIT_SEARCH_COLUMNS: dict[str, ColumnElement[str | None]] = {
    "sku": OrderProfitSkuDayMart.local_sku,
    "item_id": cast(OrderProfitSkuDayMart.item_ids_json, String),
    "product_name": OrderProfitSkuDayMart.local_sku,
}

LISTING_SEARCH_COLUMNS: dict[str, ColumnElement[str | None]] = {
    "sku": ListingManagementCurrentMart.local_sku,
    "msku": ListingManagementCurrentMart.msku,
    "item_id": ListingManagementCurrentMart.item_id,
    "title": ListingManagementCurrentMart.title,
}


class DailySalesRepository:
    """Read-only persistence boundary for DATA-PAGES daily sales MART queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_daily_sales(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        platform: str | None,
        store_id: str | None,
        owner_ref: str | None,
        search_field: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[DailySalesItemDayMart], int, datetime | None]:
        statement = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            store_id=store_id,
            owner_ref=owner_ref,
            search_field=search_field,
            keyword=keyword,
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        latest_calculated_at = self.session.scalar(
            statement.with_only_columns(func.max(DailySalesItemDayMart.calculated_at)).order_by(
                None
            )
        )
        rows = self.session.scalars(
            statement.order_by(
                DailySalesItemDayMart.business_date_la.desc(),
                DailySalesItemDayMart.store_name.asc(),
                DailySalesItemDayMart.local_sku.asc(),
                DailySalesItemDayMart.item_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0), latest_calculated_at

    def _filtered_statement(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        platform: str | None,
        store_id: str | None,
        owner_ref: str | None,
        search_field: str,
        keyword: str,
    ) -> Select[tuple[DailySalesItemDayMart]]:
        statement = select(DailySalesItemDayMart).where(
            DailySalesItemDayMart.source_account_ref.in_(account_refs)
        )
        if start_date is not None:
            statement = statement.where(DailySalesItemDayMart.business_date_la >= start_date)
        if end_date is not None:
            statement = statement.where(DailySalesItemDayMart.business_date_la <= end_date)
        if platform is not None:
            statement = statement.where(DailySalesItemDayMart.platform_code == platform)
        if store_id is not None:
            statement = statement.where(DailySalesItemDayMart.store_id == store_id)
        if owner_ref is not None:
            statement = statement.where(DailySalesItemDayMart.owner_ref == owner_ref)
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            column = DAILY_SALES_SEARCH_COLUMNS.get(search_field, DailySalesItemDayMart.local_sku)
            like_value = f"%{normalized_keyword}%"
            if search_field == "product_name":
                statement = statement.where(
                    or_(
                        DailySalesItemDayMart.local_name.ilike(like_value),
                        DailySalesItemDayMart.title.ilike(like_value),
                    )
                )
            else:
                statement = statement.where(column.ilike(like_value))
        return statement


class OrderProfitRepository:
    """Read-only persistence boundary for DATA-PAGES order-profit MART queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_order_profit(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        store_id: str | None,
        search_field: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[OrderProfitSkuDayMart], int, datetime | None]:
        statement = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            search_field=search_field,
            keyword=keyword,
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        latest_calculated_at = self.session.scalar(
            statement.with_only_columns(func.max(OrderProfitSkuDayMart.calculated_at)).order_by(
                None
            )
        )
        rows = self.session.scalars(
            statement.order_by(
                OrderProfitSkuDayMart.business_date_la.desc(),
                OrderProfitSkuDayMart.local_sku.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0), latest_calculated_at

    def _filtered_statement(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        store_id: str | None,
        search_field: str,
        keyword: str,
    ) -> Select[tuple[OrderProfitSkuDayMart]]:
        statement = select(OrderProfitSkuDayMart).where(
            OrderProfitSkuDayMart.source_account_ref.in_(account_refs)
        )
        if start_date is not None:
            statement = statement.where(OrderProfitSkuDayMart.business_date_la >= start_date)
        if end_date is not None:
            statement = statement.where(OrderProfitSkuDayMart.business_date_la <= end_date)
        if store_id is not None:
            statement = statement.where(OrderProfitSkuDayMart.store_ids_json.contains([store_id]))
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            column = ORDER_PROFIT_SEARCH_COLUMNS.get(search_field, OrderProfitSkuDayMart.local_sku)
            statement = statement.where(column.ilike(f"%{normalized_keyword}%"))
        return statement


class ListingManagementRepository:
    """Read-only persistence boundary for DATA-PAGES listing-management MART queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_listings(
        self,
        *,
        account_refs: frozenset[str],
        store_id: str | None,
        search_field: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ListingManagementCurrentMart], int, datetime | None]:
        statement = self._filtered_statement(
            account_refs=account_refs,
            store_id=store_id,
            search_field=search_field,
            keyword=keyword,
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        latest_calculated_at = self.session.scalar(
            statement.with_only_columns(
                func.max(ListingManagementCurrentMart.calculated_at)
            ).order_by(None)
        )
        rows = self.session.scalars(
            statement.order_by(
                ListingManagementCurrentMart.store_name.asc(),
                ListingManagementCurrentMart.local_sku.asc(),
                ListingManagementCurrentMart.item_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0), latest_calculated_at

    def _filtered_statement(
        self,
        *,
        account_refs: frozenset[str],
        store_id: str | None,
        search_field: str,
        keyword: str,
    ) -> Select[tuple[ListingManagementCurrentMart]]:
        statement = select(ListingManagementCurrentMart).where(
            ListingManagementCurrentMart.source_account_ref.in_(account_refs)
        )
        if store_id is not None:
            statement = statement.where(ListingManagementCurrentMart.store_id == store_id)
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            column = LISTING_SEARCH_COLUMNS.get(search_field, ListingManagementCurrentMart.local_sku)
            like_value = f"%{normalized_keyword}%"
            if search_field == "title":
                statement = statement.where(
                    or_(
                        ListingManagementCurrentMart.local_name.ilike(like_value),
                        ListingManagementCurrentMart.title.ilike(like_value),
                    )
                )
            else:
                statement = statement.where(column.ilike(like_value))
        return statement
