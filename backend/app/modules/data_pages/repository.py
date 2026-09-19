from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Select, String, and_, cast, column, func, or_, select, table
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    OrderProfitSkuDayMart,
    WalmartRefundItemFact,
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


PRODUCT_INFO_CURRENT = table(
    "dwd_lingxing_sku_product_info_current",
    column("source_account_ref", String()),
    column("lingxing_sku_code", String()),
    column("owner_uid", String()),
    column("owner_name", String()),
    column("product_developer_uid", String()),
    column("product_developer_name", String()),
)


@dataclass(frozen=True)
class ListingManagementRowProjection:
    """Listing row plus SKU owner/developer fields resolved from ProductInfo current."""

    listing: ListingManagementCurrentMart
    owner_uid: str | None
    owner_name: str | None
    product_developer_uid: str | None
    product_developer_name: str | None

    def __getattr__(self, name: str) -> object:
        return getattr(self.listing, name)


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

    def daily_sales_summary(
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
    ) -> tuple[object, object, object, str | None, object, str | None, object, str | None]:
        """Aggregate daily-sales metrics for the full filtered range, independent of pagination."""
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

        row = self.session.execute(
            statement.with_only_columns(
                func.coalesce(func.sum(DailySalesItemDayMart.sales_qty), 0),
                func.coalesce(func.sum(DailySalesItemDayMart.order_count), 0),
                func.coalesce(func.sum(DailySalesItemDayMart.sales_amount), 0),
                func.max(DailySalesItemDayMart.sales_currency_code),
                func.coalesce(func.sum(DailySalesItemDayMart.gross_profit_amount), 0),
                func.max(DailySalesItemDayMart.gross_profit_currency_code),
                func.coalesce(func.sum(DailySalesItemDayMart.ad_spend_amount), 0),
                func.max(DailySalesItemDayMart.ad_spend_currency_code),
            ).order_by(None)
        ).one()

        return row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]

    def refund_event_summary(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        store_id: str | None,
    ) -> tuple[object, object, str | None]:
        """Aggregate completed refunds by refund event day, not original sales day."""

        statement = select(
            func.coalesce(func.sum(WalmartRefundItemFact.quantity), 0),
            func.coalesce(func.sum(WalmartRefundItemFact.refund_amount), 0),
            func.max(WalmartRefundItemFact.refund_currency_code),
        ).where(
            WalmartRefundItemFact.source_account_ref.in_(account_refs),
            WalmartRefundItemFact.refund_status_raw == "REFUND_COMPLETED",
        )
        if start_date is not None:
            statement = statement.where(WalmartRefundItemFact.business_date_la >= start_date)
        if end_date is not None:
            statement = statement.where(WalmartRefundItemFact.business_date_la <= end_date)
        if store_id is not None:
            statement = statement.where(WalmartRefundItemFact.store_id == store_id)

        row = self.session.execute(statement).one()
        return row[0], row[1], row[2]

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

    def order_profit_summary(
        self,
        *,
        account_refs: frozenset[str],
        start_date: date | None,
        end_date: date | None,
        store_id: str | None,
        search_field: str,
        keyword: str,
    ) -> tuple[
        object,
        object,
        object,
        str | None,
        object,
        str | None,
        object,
        str | None,
        object,
        str | None,
    ]:
        """Aggregate order-profit metrics for the full filtered range, independent of pagination."""
        statement = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            search_field=search_field,
            keyword=keyword,
        )

        row = self.session.execute(
            statement.with_only_columns(
                func.coalesce(func.sum(OrderProfitSkuDayMart.sales_qty), 0),
                func.coalesce(func.sum(OrderProfitSkuDayMart.order_count), 0),
                func.coalesce(func.sum(OrderProfitSkuDayMart.sales_amount), 0),
                func.max(OrderProfitSkuDayMart.sales_currency_code),
                func.coalesce(func.sum(OrderProfitSkuDayMart.refund_amount), 0),
                func.max(OrderProfitSkuDayMart.sales_currency_code),
                func.coalesce(func.sum(OrderProfitSkuDayMart.gross_profit_amount), 0),
                func.max(OrderProfitSkuDayMart.gross_profit_currency_code),
                func.coalesce(func.sum(OrderProfitSkuDayMart.ad_spend_amount), 0),
                func.max(OrderProfitSkuDayMart.sales_currency_code),
            ).order_by(None)
        ).one()

        return row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9]

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
    ) -> tuple[Sequence[ListingManagementRowProjection], int, datetime | None]:
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

        # ProductInfo current has SKU-level owner/developer fields. Listing MART
        # itself may not persist owner_ref yet, so resolve owner at query time
        # without updating production data.
        owner_lookup = (
            select(
                PRODUCT_INFO_CURRENT.c.source_account_ref.label("source_account_ref"),
                PRODUCT_INFO_CURRENT.c.lingxing_sku_code.label("lingxing_sku_code"),
                func.max(PRODUCT_INFO_CURRENT.c.owner_uid).label("owner_uid"),
                func.max(PRODUCT_INFO_CURRENT.c.owner_name).label("owner_name"),
                func.max(PRODUCT_INFO_CURRENT.c.product_developer_uid).label(
                    "product_developer_uid"
                ),
                func.max(PRODUCT_INFO_CURRENT.c.product_developer_name).label(
                    "product_developer_name"
                ),
            )
            .where(PRODUCT_INFO_CURRENT.c.lingxing_sku_code.is_not(None))
            .group_by(
                PRODUCT_INFO_CURRENT.c.source_account_ref,
                PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
            )
            .subquery()
        )

        rows = self.session.execute(
            statement.outerjoin(
                owner_lookup,
                and_(
                    owner_lookup.c.source_account_ref
                    == ListingManagementCurrentMart.source_account_ref,
                    owner_lookup.c.lingxing_sku_code == ListingManagementCurrentMart.local_sku,
                ),
            )
            .add_columns(
                owner_lookup.c.owner_uid,
                owner_lookup.c.owner_name,
                owner_lookup.c.product_developer_uid,
                owner_lookup.c.product_developer_name,
            )
            .order_by(
                ListingManagementCurrentMart.store_name.asc(),
                ListingManagementCurrentMart.local_sku.asc(),
                ListingManagementCurrentMart.item_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return (
            [
                ListingManagementRowProjection(
                    listing=listing,
                    owner_uid=owner_uid,
                    owner_name=owner_name,
                    product_developer_uid=product_developer_uid,
                    product_developer_name=product_developer_name,
                )
                for (
                    listing,
                    owner_uid,
                    owner_name,
                    product_developer_uid,
                    product_developer_name,
                ) in rows
            ],
            int(total or 0),
            latest_calculated_at,
        )

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
            column = LISTING_SEARCH_COLUMNS.get(
                search_field, ListingManagementCurrentMart.local_sku
            )
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
