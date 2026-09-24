from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Select,
    String,
    and_,
    case,
    cast,
    column,
    delete,
    exists,
    func,
    or_,
    select,
    table,
    text,
    tuple_,
)
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    OrderProfitSkuDayMart,
    ProductCustomTag,
    ProductCustomTagAssignment,
    WalmartListingInventoryDailyFact,
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


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _platform_filter_values(value: str | None) -> list[str]:
    values: list[str] = []
    for item in _csv_values(value):
        normalized = item.strip().lower()
        if normalized == "walmart":
            values.extend(["10008", "Walmart", "walmart"])
        elif normalized == "amazon":
            values.extend(["amazon", "Amazon"])
        elif normalized == "temu":
            values.extend(["temu", "TEMU"])
        else:
            values.append(item)
    return list(dict.fromkeys(values))


class DailySalesRepository:
    """Read-only persistence boundary for DATA-PAGES daily sales MART queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _inventory_snapshot_table_ready(self) -> bool:
        """Return whether the inventory snapshot migration is already applied.

        The application code may be deployed before the database migration.
        In that state Daily Sales must remain readable and inventory is reported
        as unavailable instead of raising a 500 or falling back to fake history.
        """
        return bool(
            self.session.scalar(
                text("select to_regclass('public.fact_walmart_listing_inventory_daily')")
            )
        )

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
        batch_values: str,
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
            batch_values=batch_values,
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        latest_calculated_at = self.session.scalar(
            statement.with_only_columns(func.max(DailySalesItemDayMart.calculated_at)).order_by(
                None
            )
        )
        is_single_day = start_date is not None and end_date is not None and start_date == end_date
        order_columns = (
            (
                func.coalesce(DailySalesItemDayMart.sales_qty, 0).desc(),
                func.coalesce(DailySalesItemDayMart.sales_amount, 0).desc(),
                DailySalesItemDayMart.business_date_la.desc(),
                DailySalesItemDayMart.store_name.asc(),
                DailySalesItemDayMart.local_sku.asc(),
                DailySalesItemDayMart.item_id.asc(),
            )
            if is_single_day
            else (
                DailySalesItemDayMart.business_date_la.desc(),
                func.coalesce(DailySalesItemDayMart.sales_qty, 0).desc(),
                func.coalesce(DailySalesItemDayMart.sales_amount, 0).desc(),
                DailySalesItemDayMart.store_name.asc(),
                DailySalesItemDayMart.local_sku.asc(),
                DailySalesItemDayMart.item_id.asc(),
            )
        )

        rows = self.session.scalars(
            statement.order_by(*order_columns).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return rows, int(total or 0), latest_calculated_at

    def daily_sales_inventory_snapshot_map(
        self,
        rows: Sequence[DailySalesItemDayMart],
    ) -> dict[tuple[date, str, str, str], object | None]:
        """Read inventory from the actual listing capture day.

        Daily-sales MART rows may be recalculated later. Therefore their persisted
        WFS inventory must never be trusted as a substitute for the historical
        point-in-time inventory snapshot.
        """
        if not self._inventory_snapshot_table_ready():
            return {}

        keys = {
            (
                row.business_date_la,
                row.source_account_ref,
                row.store_id,
                row.item_id,
            )
            for row in rows
        }

        if not keys:
            return {}

        snapshot_rows = self.session.execute(
            select(
                WalmartListingInventoryDailyFact.snapshot_date_la,
                WalmartListingInventoryDailyFact.source_account_ref,
                WalmartListingInventoryDailyFact.store_id,
                WalmartListingInventoryDailyFact.item_id,
                WalmartListingInventoryDailyFact.wfs_available_quantity,
            ).where(
                tuple_(
                    WalmartListingInventoryDailyFact.snapshot_date_la,
                    WalmartListingInventoryDailyFact.source_account_ref,
                    WalmartListingInventoryDailyFact.store_id,
                    WalmartListingInventoryDailyFact.item_id,
                ).in_(list(keys))
            )
        ).all()

        return {
            (
                snapshot_date,
                source_account_ref,
                store_id,
                item_id,
            ): wfs_available_quantity
            for (
                snapshot_date,
                source_account_ref,
                store_id,
                item_id,
                wfs_available_quantity,
            ) in snapshot_rows
        }

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
        batch_values: str,
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
            batch_values=batch_values,
        )

        # Inventory is a point-in-time metric.
        # Find the latest business date in the full filtered Daily Sales result,
        # then aggregate only genuine snapshots captured for that same LA date.
        summary_base = (
            statement.with_only_columns(
                DailySalesItemDayMart.business_date_la,
                DailySalesItemDayMart.source_account_ref,
                DailySalesItemDayMart.store_id,
                DailySalesItemDayMart.item_id,
            )
            .order_by(None)
            .distinct()
            .subquery()
        )

        latest_inventory_date = self.session.scalar(
            select(func.max(summary_base.c.business_date_la))
        )

        latest_wfs_available_quantity = None

        if latest_inventory_date is not None and self._inventory_snapshot_table_ready():
            expected_inventory_rows = self.session.scalar(
                select(func.count())
                .select_from(summary_base)
                .where(summary_base.c.business_date_la == latest_inventory_date)
            )

            inventory_row = self.session.execute(
                select(
                    func.count(WalmartListingInventoryDailyFact.wfs_available_quantity),
                    func.sum(WalmartListingInventoryDailyFact.wfs_available_quantity),
                )
                .select_from(WalmartListingInventoryDailyFact)
                .join(
                    summary_base,
                    and_(
                        summary_base.c.business_date_la
                        == WalmartListingInventoryDailyFact.snapshot_date_la,
                        summary_base.c.source_account_ref
                        == WalmartListingInventoryDailyFact.source_account_ref,
                        summary_base.c.store_id == WalmartListingInventoryDailyFact.store_id,
                        summary_base.c.item_id == WalmartListingInventoryDailyFact.item_id,
                    ),
                )
                .where(WalmartListingInventoryDailyFact.snapshot_date_la == latest_inventory_date)
            ).one()

            expected_count = int(expected_inventory_rows or 0)
            captured_count = int(inventory_row[0] or 0)

            # Do not present a partial inventory total as complete.
            if expected_count > 0 and captured_count == expected_count:
                latest_wfs_available_quantity = inventory_row[1]

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

        return (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            latest_wfs_available_quantity,
        )

    def refund_event_summary(
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
        batch_values: str,
    ) -> tuple[object, object, str | None]:
        """Aggregate refund quantity and refund loss from recalculated Daily Sales MART."""

        statement = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            store_id=store_id,
            owner_ref=owner_ref,
            search_field=search_field,
            keyword=keyword,
            batch_values=batch_values,
        )

        row = self.session.execute(
            statement.with_only_columns(
                func.coalesce(func.sum(DailySalesItemDayMart.return_qty), 0),
                func.coalesce(func.sum(DailySalesItemDayMart.refund_amount), 0),
                func.max(DailySalesItemDayMart.refund_currency_code),
            ).order_by(None)
        ).one()

        return row[0], row[1], row[2]

    def order_profit_trend(
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
    ) -> Sequence[object]:
        """Aggregate lightweight order-profit chart points by date.

        Chart rendering only needs one row per day, not product/SKU detail rows.
        """
        base = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            store_id=store_id,
            owner_ref=owner_ref,
            search_field=search_field,
            keyword=keyword,
            batch_values="",
        ).subquery()

        return self.session.execute(
            select(
                base.c.business_date_la.label("date"),
                func.coalesce(func.sum(base.c.sales_qty), 0).label("sales_qty"),
                func.coalesce(func.sum(base.c.order_count), 0).label("order_count"),
                func.coalesce(func.sum(base.c.sales_amount), 0).label("sales_amount"),
                func.max(base.c.sales_currency_code).label("sales_currency_code"),
                func.coalesce(func.sum(base.c.refund_amount), 0).label("refund_amount"),
                func.max(base.c.refund_currency_code).label("refund_currency_code"),
                func.coalesce(func.sum(base.c.gross_profit_amount), 0).label("order_profit_amount"),
                func.max(base.c.gross_profit_currency_code).label("order_profit_currency_code"),
                func.coalesce(func.sum(base.c.ad_spend_amount), 0).label("ad_spend_amount"),
                func.max(base.c.ad_spend_currency_code).label("ad_spend_currency_code"),
            )
            .group_by(base.c.business_date_la)
            .order_by(base.c.business_date_la.asc())
        ).all()

    def filter_options(
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
    ) -> dict[str, list[tuple[str, str, int]]]:
        """Return filter options from the full filtered daily-sales range, not the current page."""

        # Faceted filter logic:
        # - platform options are filtered by selected owner/store,
        #   but not by selected platform itself.
        # - owner options are filtered by selected platform/store,
        #   but not by selected owner itself.
        # - store options are filtered by selected platform/owner,
        #   but not by selected store itself.
        platform_base = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=None,
            store_id=store_id,
            owner_ref=owner_ref,
            search_field=search_field,
            keyword=keyword,
        ).subquery()

        owner_base = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            store_id=store_id,
            owner_ref=None,
            search_field=search_field,
            keyword=keyword,
        ).subquery()

        store_base = self._filtered_statement(
            account_refs=account_refs,
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            store_id=None,
            owner_ref=owner_ref,
            search_field=search_field,
            keyword=keyword,
        ).subquery()

        platform_rows = self.session.execute(
            select(
                platform_base.c.platform_code,
                func.count().label("count"),
            )
            .where(platform_base.c.platform_code.is_not(None))
            .group_by(platform_base.c.platform_code)
            .order_by(platform_base.c.platform_code)
        ).all()

        owner_rows = self.session.execute(
            select(
                owner_base.c.owner_ref,
                func.count().label("count"),
            )
            .where(
                owner_base.c.owner_ref.is_not(None),
                func.trim(cast(owner_base.c.owner_ref, String)) != "",
            )
            .group_by(owner_base.c.owner_ref)
            .order_by(owner_base.c.owner_ref)
        ).all()

        store_value = func.coalesce(store_base.c.store_name, store_base.c.store_id)
        store_rows = self.session.execute(
            select(
                store_value.label("store_value"),
                func.count().label("count"),
            )
            .where(
                store_value.is_not(None),
                func.trim(cast(store_value, String)) != "",
            )
            .group_by(store_value)
            .order_by(store_value)
        ).all()

        return {
            "platforms": [
                (str(value), str(value), int(count or 0))
                for value, count in platform_rows
                if value is not None and str(value).strip()
            ],
            "owners": [
                (str(value), str(value), int(count or 0))
                for value, count in owner_rows
                if value is not None and str(value).strip()
            ],
            "stores": [
                (str(value), str(value), int(count or 0))
                for value, count in store_rows
                if value is not None and str(value).strip()
            ],
        }

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
        batch_values: str = "",
    ) -> Select[tuple[DailySalesItemDayMart]]:
        statement = select(DailySalesItemDayMart).where(
            DailySalesItemDayMart.source_account_ref.in_(account_refs)
        )
        if start_date is not None:
            statement = statement.where(DailySalesItemDayMart.business_date_la >= start_date)
        if end_date is not None:
            statement = statement.where(DailySalesItemDayMart.business_date_la <= end_date)
        platform_values = _platform_filter_values(platform)
        if platform_values:
            statement = statement.where(DailySalesItemDayMart.platform_code.in_(platform_values))
        store_values = _csv_values(store_id)
        if store_values:
            statement = statement.where(
                or_(
                    DailySalesItemDayMart.store_id.in_(store_values),
                    DailySalesItemDayMart.store_name.in_(store_values),
                )
            )
        owner_values = _csv_values(owner_ref)
        if owner_values:
            statement = statement.where(DailySalesItemDayMart.owner_ref.in_(owner_values))
        search_column = DAILY_SALES_SEARCH_COLUMNS.get(
            search_field,
            DailySalesItemDayMart.local_sku,
        )
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            like_value = f"%{normalized_keyword}%"
            if search_field == "product_name":
                statement = statement.where(
                    or_(
                        DailySalesItemDayMart.local_name.ilike(like_value),
                        DailySalesItemDayMart.title.ilike(like_value),
                    )
                )
            else:
                statement = statement.where(search_column.ilike(like_value))

        batch_filter_values = _csv_values(batch_values)
        if batch_filter_values:
            if search_field == "product_name":
                statement = statement.where(
                    or_(
                        DailySalesItemDayMart.local_name.in_(batch_filter_values),
                        DailySalesItemDayMart.title.in_(batch_filter_values),
                    )
                )
            else:
                statement = statement.where(search_column.in_(batch_filter_values))
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
                func.coalesce(OrderProfitSkuDayMart.sales_qty, 0).desc(),
                func.coalesce(OrderProfitSkuDayMart.sales_amount, 0).desc(),
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
        owner_ref: str | None = "",
        product_type: str | None = "",
        status: str | None = "",
        tag: str | None = "",
        summary_filter: str = "total",
        search_field: str,
        keyword: str,
        batch_values: str = "",
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ListingManagementRowProjection], int, datetime | None]:
        statement = self._filtered_listing_statement(
            account_refs=account_refs,
            store_id=store_id,
            owner_ref=owner_ref,
            product_type=product_type,
            status=status,
            tag=tag,
            summary_filter=summary_filter,
            search_field=search_field,
            keyword=keyword,
            batch_values=batch_values,
        )

        base = statement.order_by(None).subquery()
        total = self.session.scalar(select(func.count()).select_from(base))
        latest_calculated_at = self.session.scalar(select(func.max(base.c.calculated_at)))

        rows = self.session.execute(
            statement.order_by(
                func.coalesce(ListingManagementCurrentMart.wfs_available_quantity, 0).desc(),
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

    def listing_summary(
        self,
        *,
        account_refs: frozenset[str],
        store_id: str | None,
        owner_ref: str | None,
        product_type: str | None,
        status: str | None,
        tag: str | None,
        search_field: str,
        keyword: str,
        batch_values: str,
    ) -> tuple[int, int, int, int, int, int]:
        statement = self._filtered_listing_statement(
            account_refs=account_refs,
            store_id=store_id,
            owner_ref=owner_ref,
            product_type=product_type,
            status=status,
            tag=tag,
            summary_filter="total",
            search_field=search_field,
            keyword=keyword,
            batch_values=batch_values,
        )
        base = statement.order_by(None).subquery()

        online_condition = func.coalesce(base.c.wfs_available_quantity, 0) > 0
        buybox_exception_condition = base.c.buybox_status.in_(
            ["未拥有", "LOST", "NOT_OWNED", "secondary", "other"]
        )
        rating_warning_condition = and_(
            base.c.average_rating.is_not(None),
            base.c.average_rating > 0,
            base.c.average_rating < 4,
        )
        resold_warning_condition = base.c.is_hijacked.is_(True)
        strike_price_exception_condition = and_(
            base.c.sale_price_amount.is_not(None),
            base.c.sale_price_amount > 0,
            base.c.strike_price_amount.is_not(None),
            base.c.strike_price_amount <= base.c.sale_price_amount,
        )

        row = self.session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((online_condition, 1), else_=0)), 0),
                func.coalesce(func.sum(case((buybox_exception_condition, 1), else_=0)), 0),
                func.coalesce(func.sum(case((rating_warning_condition, 1), else_=0)), 0),
                func.coalesce(func.sum(case((resold_warning_condition, 1), else_=0)), 0),
                func.coalesce(func.sum(case((strike_price_exception_condition, 1), else_=0)), 0),
            ).select_from(base)
        ).one()

        return (
            int(row[0] or 0),
            int(row[1] or 0),
            int(row[2] or 0),
            int(row[3] or 0),
            int(row[4] or 0),
            int(row[5] or 0),
        )

    def listing_filter_options(
        self,
        *,
        account_refs: frozenset[str],
    ) -> dict[str, list[tuple[str, str, int]]]:
        statement = self._filtered_listing_statement(
            account_refs=account_refs,
            store_id="",
            owner_ref="",
            product_type="",
            status="",
            tag="",
            summary_filter="total",
            search_field="sku",
            keyword="",
            batch_values="",
        )
        base = statement.order_by(None).subquery()

        store_value = func.coalesce(base.c.store_name, base.c.store_id)
        owner_value = func.coalesce(base.c.owner_name, base.c.owner_ref, base.c.owner_uid)
        product_type_value = base.c.category

        store_rows = self.session.execute(
            select(store_value.label("value"), func.count().label("count"))
            .where(store_value.is_not(None), func.trim(cast(store_value, String)) != "")
            .group_by(store_value)
            .order_by(store_value)
        ).all()

        owner_rows = self.session.execute(
            select(owner_value.label("value"), func.count().label("count"))
            .where(owner_value.is_not(None), func.trim(cast(owner_value, String)) != "")
            .group_by(owner_value)
            .order_by(owner_value)
        ).all()

        product_type_rows = self.session.execute(
            select(product_type_value.label("value"), func.count().label("count"))
            .where(
                product_type_value.is_not(None),
                func.trim(cast(product_type_value, String)) != "",
            )
            .group_by(product_type_value)
            .order_by(product_type_value)
        ).all()

        tag_counter: dict[str, int] = {}
        tag_source_rows = self.session.scalars(
            select(base.c.tags_json).where(base.c.tags_json.is_not(None))
        ).all()
        for tags in tag_source_rows:
            if not isinstance(tags, list):
                continue
            for item in tags:
                if isinstance(item, str):
                    name = item.strip()
                elif isinstance(item, dict):
                    raw = item.get("name") or item.get("label") or item.get("title")
                    name = str(raw).strip() if raw is not None else ""
                else:
                    name = ""
                if name:
                    tag_counter[name] = tag_counter.get(name, 0) + 1

        return {
            "stores": [
                (str(value), str(value), int(count or 0))
                for value, count in store_rows
                if value is not None and str(value).strip()
            ],
            "owners": [
                (str(value), str(value), int(count or 0))
                for value, count in owner_rows
                if value is not None and str(value).strip()
            ],
            "product_types": [
                (str(value), str(value), int(count or 0))
                for value, count in product_type_rows
                if value is not None and str(value).strip()
            ],
            "tags": [
                (name, name, count)
                for name, count in sorted(tag_counter.items(), key=lambda item: item[0])
            ],
        }

    def _owner_lookup(self):
        return (
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

    def _filtered_listing_statement(
        self,
        *,
        account_refs: frozenset[str],
        store_id: str | None,
        owner_ref: str | None,
        product_type: str | None,
        status: str | None,
        tag: str | None,
        summary_filter: str,
        search_field: str,
        keyword: str,
        batch_values: str,
    ):
        owner_lookup = self._owner_lookup()
        statement = (
            select(
                ListingManagementCurrentMart,
                owner_lookup.c.owner_uid,
                owner_lookup.c.owner_name,
                owner_lookup.c.product_developer_uid,
                owner_lookup.c.product_developer_name,
            )
            .outerjoin(
                owner_lookup,
                and_(
                    owner_lookup.c.source_account_ref
                    == ListingManagementCurrentMart.source_account_ref,
                    owner_lookup.c.lingxing_sku_code == ListingManagementCurrentMart.local_sku,
                ),
            )
            .where(ListingManagementCurrentMart.source_account_ref.in_(account_refs))
        )

        store_values = _csv_values(store_id)
        if store_values:
            statement = statement.where(
                or_(
                    ListingManagementCurrentMart.store_id.in_(store_values),
                    ListingManagementCurrentMart.store_name.in_(store_values),
                )
            )

        owner_values = _csv_values(owner_ref)
        if owner_values:
            owner_display_value = func.coalesce(
                owner_lookup.c.owner_name,
                ListingManagementCurrentMart.owner_ref,
                owner_lookup.c.owner_uid,
            )
            statement = statement.where(
                or_(
                    owner_lookup.c.owner_uid.in_(owner_values),
                    owner_lookup.c.owner_name.in_(owner_values),
                    ListingManagementCurrentMart.owner_ref.in_(owner_values),
                    owner_display_value.in_(owner_values),
                )
            )

        product_type_values = _csv_values(product_type)
        if product_type_values:
            statement = statement.where(
                ListingManagementCurrentMart.category.in_(product_type_values)
            )

        status_values = _csv_values(status)
        if status_values:
            status_conditions = []
            for item in status_values:
                if item == "启用":
                    status_conditions.append(ListingManagementCurrentMart.disabled_reason.is_(None))
                elif item == "停用":
                    status_conditions.append(
                        ListingManagementCurrentMart.disabled_reason.is_not(None)
                    )
                elif item == "在线":
                    status_conditions.append(
                        ListingManagementCurrentMart.listing_status.in_(
                            ["在线", "在售", "ONLINE", "PUBLISHED", "PUBLISH", "published"]
                        )
                    )
                elif item == "离线":
                    status_conditions.append(
                        ListingManagementCurrentMart.listing_status.in_(
                            ["离线", "UNPUBLISHED", "OFFLINE", "unpublished", "offline"]
                        )
                    )
                elif item == "拥有":
                    status_conditions.append(
                        ListingManagementCurrentMart.buybox_status.in_(
                            ["拥有", "PRIMARY", "primary", "WON", "WINNING"]
                        )
                    )
                elif item == "未拥有":
                    status_conditions.append(
                        ListingManagementCurrentMart.buybox_status.in_(
                            ["未拥有", "LOST", "NOT_OWNED", "secondary", "other"]
                        )
                    )
            if status_conditions:
                statement = statement.where(or_(*status_conditions))

        tag_values = _csv_values(tag)
        if tag_values:
            tag_text = cast(ListingManagementCurrentMart.tags_json, String)
            legacy_tag_conditions = [tag_text.ilike(f'%"{value}"%') for value in tag_values]

            db_tag_exists = exists(
                select(1)
                .select_from(ProductCustomTagAssignment)
                .join(ProductCustomTag, ProductCustomTag.id == ProductCustomTagAssignment.tag_id)
                .where(
                    ProductCustomTagAssignment.source_account_ref
                    == ListingManagementCurrentMart.source_account_ref,
                    ProductCustomTagAssignment.item_id == ListingManagementCurrentMart.item_id,
                    ProductCustomTag.deleted_at.is_(None),
                    ProductCustomTag.is_active.is_(True),
                    ProductCustomTag.name.in_(tag_values),
                )
            )

            statement = statement.where(or_(*legacy_tag_conditions, db_tag_exists))

        if summary_filter == "online":
            statement = statement.where(
                func.coalesce(ListingManagementCurrentMart.wfs_available_quantity, 0) > 0
            )
        elif summary_filter == "offline":
            statement = statement.where(
                ListingManagementCurrentMart.listing_status.in_(
                    ["离线", "UNPUBLISHED", "OFFLINE", "unpublished", "offline"]
                )
            )
        elif summary_filter == "buybox":
            statement = statement.where(
                ListingManagementCurrentMart.buybox_status.in_(
                    ["未拥有", "LOST", "NOT_OWNED", "secondary", "other"]
                )
            )
        elif summary_filter == "rating":
            statement = statement.where(
                ListingManagementCurrentMart.average_rating.is_not(None),
                ListingManagementCurrentMart.average_rating > 0,
                ListingManagementCurrentMart.average_rating < 4,
            )
        elif summary_filter == "resold":
            statement = statement.where(ListingManagementCurrentMart.is_hijacked.is_(True))
        elif summary_filter == "strike":
            statement = statement.where(
                ListingManagementCurrentMart.sale_price_amount.is_not(None),
                ListingManagementCurrentMart.sale_price_amount > 0,
                ListingManagementCurrentMart.strike_price_amount.is_not(None),
                ListingManagementCurrentMart.strike_price_amount
                <= ListingManagementCurrentMart.sale_price_amount,
            )
        elif summary_filter == "disabled":
            statement = statement.where(ListingManagementCurrentMart.disabled_reason.is_not(None))

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

        batch_filter_values = _csv_values(batch_values)
        if batch_filter_values:
            statement = statement.where(
                or_(
                    ListingManagementCurrentMart.local_sku.in_(batch_filter_values),
                    ListingManagementCurrentMart.msku.in_(batch_filter_values),
                    ListingManagementCurrentMart.item_id.in_(batch_filter_values),
                )
            )

        return statement


class ListingTagRepository:
    """Write boundary for Listing custom tags and item assignments."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _is_tag_table_missing(exc: ProgrammingError) -> bool:
        message = str(exc).lower()
        mentions_tag_table = (
            "product_custom_tags" in message or "product_custom_tag_assignments" in message
        )
        return mentions_tag_table and (
            "undefinedtable" in message or "does not exist" in message or "no such table" in message
        )

    def _rollback_if_tag_table_missing(self, exc: ProgrammingError) -> bool:
        if self._is_tag_table_missing(exc):
            self.session.rollback()
            return True
        return False

    def list_tags(self, *, account_refs: frozenset[str]) -> list[tuple[ProductCustomTag, int]]:
        if not account_refs:
            return []

        usage = (
            select(
                ProductCustomTagAssignment.tag_id.label("tag_id"),
                func.count().label("usage"),
            )
            .where(ProductCustomTagAssignment.source_account_ref.in_(account_refs))
            .group_by(ProductCustomTagAssignment.tag_id)
            .subquery()
        )

        try:
            rows = self.session.execute(
                select(ProductCustomTag, func.coalesce(usage.c.usage, 0))
                .outerjoin(usage, usage.c.tag_id == ProductCustomTag.id)
                .where(
                    ProductCustomTag.deleted_at.is_(None),
                    ProductCustomTag.is_active.is_(True),
                )
                .order_by(ProductCustomTag.sort_order.asc(), ProductCustomTag.created_at.asc())
            ).all()
        except ProgrammingError as exc:
            if self._rollback_if_tag_table_missing(exc):
                return []
            raise

        return [(tag, int(count or 0)) for tag, count in rows]

    def create_tag(self, *, name: str, color: str, sort_order: int = 0) -> ProductCustomTag:
        normalized_name = name.strip()
        self._raise_if_duplicate_name(normalized_name)

        tag = ProductCustomTag(
            name=normalized_name,
            color=color.strip(),
            sort_order=sort_order,
            is_active=True,
        )
        self.session.add(tag)
        self.session.commit()
        self.session.refresh(tag)
        return tag

    def update_tag(
        self,
        *,
        tag_id: str,
        name: str | None,
        color: str | None,
        sort_order: int | None,
        is_active: bool | None,
    ) -> ProductCustomTag:
        tag = self._get_tag_or_raise(tag_id)

        if name is not None:
            normalized_name = name.strip()
            self._raise_if_duplicate_name(normalized_name, except_id=tag.id)
            tag.name = normalized_name
        if color is not None:
            tag.color = color.strip()
        if sort_order is not None:
            tag.sort_order = sort_order
        if is_active is not None:
            tag.is_active = is_active

        tag.updated_at = datetime.now()
        self.session.commit()
        self.session.refresh(tag)
        return tag

    def delete_tag(self, *, tag_id: str) -> None:
        tag = self._get_tag_or_raise(tag_id)
        self.session.execute(
            delete(ProductCustomTagAssignment).where(ProductCustomTagAssignment.tag_id == tag.id)
        )
        self.session.delete(tag)
        self.session.commit()

    def batch_set_tags(
        self,
        *,
        account_refs: frozenset[str],
        listing_ids: list[str],
        tag_ids: list[str],
        tag_values: list[str],
        mode: str,
    ) -> tuple[int, int]:
        listings = self.session.execute(
            select(
                ListingManagementCurrentMart.id,
                ListingManagementCurrentMart.source_account_ref,
                ListingManagementCurrentMart.item_id,
            ).where(
                ListingManagementCurrentMart.id.in_([self._uuid(value) for value in listing_ids]),
                ListingManagementCurrentMart.source_account_ref.in_(account_refs),
            )
        ).all()

        if not listings:
            return 0, 0

        tags = self._resolve_tags(tag_ids=tag_ids, tag_values=tag_values)
        if not tags:
            return len(listings), 0

        resolved_tag_ids = [tag.id for tag in tags]

        if mode == "replace":
            for _, source_account_ref, item_id in listings:
                self.session.execute(
                    delete(ProductCustomTagAssignment).where(
                        ProductCustomTagAssignment.source_account_ref == source_account_ref,
                        ProductCustomTagAssignment.item_id == item_id,
                    )
                )
                for tag_id in resolved_tag_ids:
                    self.session.add(
                        ProductCustomTagAssignment(
                            tag_id=tag_id,
                            source_account_ref=source_account_ref,
                            item_id=item_id,
                        )
                    )

        elif mode == "remove":
            for _, source_account_ref, item_id in listings:
                self.session.execute(
                    delete(ProductCustomTagAssignment).where(
                        ProductCustomTagAssignment.source_account_ref == source_account_ref,
                        ProductCustomTagAssignment.item_id == item_id,
                        ProductCustomTagAssignment.tag_id.in_(resolved_tag_ids),
                    )
                )

        else:
            for _, source_account_ref, item_id in listings:
                existing_tag_ids = set(
                    self.session.scalars(
                        select(ProductCustomTagAssignment.tag_id).where(
                            ProductCustomTagAssignment.source_account_ref == source_account_ref,
                            ProductCustomTagAssignment.item_id == item_id,
                            ProductCustomTagAssignment.tag_id.in_(resolved_tag_ids),
                        )
                    ).all()
                )
                for tag_id in resolved_tag_ids:
                    if tag_id in existing_tag_ids:
                        continue
                    self.session.add(
                        ProductCustomTagAssignment(
                            tag_id=tag_id,
                            source_account_ref=source_account_ref,
                            item_id=item_id,
                        )
                    )

        self.session.commit()
        return len(listings), len(tags)

    def tags_for_listing_rows(self, rows: Sequence[object]) -> dict[tuple[str, str], list[str]]:
        identities = {
            (str(row.source_account_ref), str(row.item_id))
            for row in rows
            if getattr(row, "source_account_ref", None) and getattr(row, "item_id", None)
        }
        if not identities:
            return {}

        account_refs = sorted({account_ref for account_ref, _ in identities})
        item_ids = sorted({item_id for _, item_id in identities})

        result: dict[tuple[str, str], list[str]] = {identity: [] for identity in identities}

        try:
            tag_rows = self.session.execute(
                select(
                    ProductCustomTagAssignment.source_account_ref,
                    ProductCustomTagAssignment.item_id,
                    ProductCustomTag.name,
                )
                .join(ProductCustomTag, ProductCustomTag.id == ProductCustomTagAssignment.tag_id)
                .where(
                    ProductCustomTagAssignment.source_account_ref.in_(account_refs),
                    ProductCustomTagAssignment.item_id.in_(item_ids),
                    ProductCustomTag.deleted_at.is_(None),
                    ProductCustomTag.is_active.is_(True),
                )
                .order_by(ProductCustomTag.sort_order.asc(), ProductCustomTag.created_at.asc())
            ).all()
        except ProgrammingError as exc:
            if self._rollback_if_tag_table_missing(exc):
                return result
            raise

        for source_account_ref, item_id, name in tag_rows:
            key = (str(source_account_ref), str(item_id))
            if key in result:
                result[key].append(str(name))

        return result

    def _resolve_tags(self, *, tag_ids: list[str], tag_values: list[str]) -> list[ProductCustomTag]:
        tags: list[ProductCustomTag] = []
        seen: set[UUID] = set()

        uuid_values = [self._uuid(value) for value in tag_ids if value.strip()]
        if uuid_values:
            for tag in self.session.scalars(
                select(ProductCustomTag).where(
                    ProductCustomTag.id.in_(uuid_values),
                    ProductCustomTag.deleted_at.is_(None),
                    ProductCustomTag.is_active.is_(True),
                )
            ):
                if tag.id not in seen:
                    seen.add(tag.id)
                    tags.append(tag)

        for value in tag_values:
            name = value.strip()
            if not name:
                continue
            tag = self._find_tag_by_name(name)
            if tag is None:
                tag = ProductCustomTag(
                    name=name[:16],
                    color="#1677FF",
                    sort_order=0,
                    is_active=True,
                )
                self.session.add(tag)
                self.session.flush()
            if tag.id not in seen:
                seen.add(tag.id)
                tags.append(tag)

        return tags

    def _find_tag_by_name(self, name: str) -> ProductCustomTag | None:
        return self.session.scalar(
            select(ProductCustomTag).where(
                func.lower(ProductCustomTag.name) == name.strip().lower(),
                ProductCustomTag.deleted_at.is_(None),
            )
        )

    def _raise_if_duplicate_name(self, name: str, except_id: UUID | None = None) -> None:
        statement = select(ProductCustomTag).where(
            func.lower(ProductCustomTag.name) == name.strip().lower(),
            ProductCustomTag.deleted_at.is_(None),
        )
        if except_id is not None:
            statement = statement.where(ProductCustomTag.id != except_id)

        if self.session.scalar(statement) is not None:
            raise ValueError("LISTING_TAG_NAME_DUPLICATED")

    def _get_tag_or_raise(self, tag_id: str) -> ProductCustomTag:
        tag = self.session.get(ProductCustomTag, self._uuid(tag_id))
        if tag is None or tag.deleted_at is not None:
            raise ValueError("LISTING_TAG_NOT_FOUND")
        return tag

    @staticmethod
    def _uuid(value: str) -> UUID:
        try:
            return UUID(str(value))
        except ValueError as exc:
            raise ValueError("INVALID_UUID") from exc
