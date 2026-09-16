from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.data_pages.models import DailySalesItemDayMart

SEARCH_COLUMNS: dict[str, ColumnElement[str | None]] = {
    "sku": DailySalesItemDayMart.local_sku,
    "msku": DailySalesItemDayMart.msku,
    "item_id": DailySalesItemDayMart.item_id,
    "product_name": DailySalesItemDayMart.local_name,
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
            statement.with_only_columns(func.max(DailySalesItemDayMart.calculated_at)).order_by(None)
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
            column = SEARCH_COLUMNS.get(search_field, DailySalesItemDayMart.local_sku)
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
