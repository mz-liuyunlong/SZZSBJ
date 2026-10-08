from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, String, and_, cast, column, func, select, table, tuple_
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.modules.data_pages.repository import DailySalesRepository, OrderProfitRepository
from app.modules.data_pages.schemas import (
    DailySalesListData,
    DailySalesQuery,
    OrderProfitListData,
    OrderProfitQuery,
    OrderProfitTrendData,
)

AFTER_SALES_REFUND_ITEMS = table(
    "after_sales_refund_items",
    column("source_account_ref", String()),
    column("platform_code", String()),
    column("store_id", String()),
    column("item_id", String()),
    column("msku", String()),
    column("local_sku", String()),
    column("purchase_time_at"),
    column("refund_loss_amount"),
    column("refund_currency_code", String()),
    column("refund_loss_effective"),
)


def _decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _purchase_date() -> object:
    return cast(AFTER_SALES_REFUND_ITEMS.c.purchase_time_at, Date)


def _trimmed_text(value: object) -> object:
    return func.trim(cast(value, String))


def _normalized_msku(value: object) -> object:
    return func.coalesce(func.nullif(_trimmed_text(value), ""), "")


def _normalized_profit_sku(local_sku: object, fallback_item_id: object) -> object:
    return func.coalesce(
        func.nullif(_trimmed_text(local_sku), ""),
        func.nullif(_trimmed_text(fallback_item_id), ""),
        "",
    )


def _safe_all(session: Session, statement: object) -> list[object]:
    try:
        return list(session.execute(statement).all())
    except ProgrammingError as exc:
        message = str(exc).lower()
        if "after_sales_refund_items" in message and (
            "undefinedtable" in message or "does not exist" in message
        ):
            session.rollback()
            return []
        raise


def _safe_one_or_none(session: Session, statement: object) -> object | None:
    rows = _safe_all(session, statement)
    return rows[0] if rows else None


def _account_values(account_refs: frozenset[str]) -> list[str]:
    return sorted(str(value) for value in account_refs if str(value).strip())


def _daily_sales_statement(
    session: Session,
    *,
    query: DailySalesQuery,
    account_refs: frozenset[str],
):
    return DailySalesRepository(session)._filtered_statement(
        account_refs=account_refs,
        start_date=query.start_date,
        end_date=query.end_date,
        platform=query.platform,
        store_id=query.store_id,
        owner_ref=query.owner_ref,
        search_field=query.search_field,
        keyword=query.keyword,
        batch_values=query.batch_values,
    )


def _order_profit_statement(
    session: Session,
    *,
    query: OrderProfitQuery,
    account_refs: frozenset[str],
):
    return OrderProfitRepository(session)._filtered_statement(
        account_refs=account_refs,
        start_date=query.start_date,
        end_date=query.end_date,
        store_id=query.store_id,
        search_field=query.search_field,
        keyword=query.keyword,
    )


def _daily_sales_base(statement: object) -> object:
    from app.modules.data_pages.models import DailySalesItemDayMart

    return (
        statement.with_only_columns(
            DailySalesItemDayMart.business_date_la.label("business_date_la"),
            DailySalesItemDayMart.source_account_ref.label("source_account_ref"),
            DailySalesItemDayMart.store_id.label("store_id"),
            DailySalesItemDayMart.item_id.label("item_id"),
            DailySalesItemDayMart.msku.label("msku"),
        )
        .order_by(None)
        .distinct()
        .subquery()
    )


def _order_profit_base(statement: object) -> object:
    from app.modules.data_pages.models import OrderProfitSkuDayMart

    return (
        statement.with_only_columns(
            OrderProfitSkuDayMart.business_date_la.label("business_date_la"),
            OrderProfitSkuDayMart.source_account_ref.label("source_account_ref"),
            OrderProfitSkuDayMart.local_sku.label("local_sku"),
        )
        .order_by(None)
        .distinct()
        .subquery()
    )


def _daily_loss_summary(session: Session, base: object) -> tuple[Decimal, str | None]:
    refund_msku = _normalized_msku(AFTER_SALES_REFUND_ITEMS.c.msku)
    base_msku = _normalized_msku(base.c.msku)
    statement = (
        select(
            func.coalesce(
                func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                0,
            ).label("refund_loss_amount"),
            func.max(AFTER_SALES_REFUND_ITEMS.c.refund_currency_code).label("refund_currency_code"),
        )
        .select_from(base)
        .join(
            AFTER_SALES_REFUND_ITEMS,
            and_(
                base.c.business_date_la == _purchase_date(),
                base.c.source_account_ref == AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                base.c.store_id == AFTER_SALES_REFUND_ITEMS.c.store_id,
                base.c.item_id == AFTER_SALES_REFUND_ITEMS.c.item_id,
                base_msku == refund_msku,
            ),
        )
        .where(
            AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
            AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
            AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
        )
    )
    row = _safe_one_or_none(session, statement)
    if row is None:
        return Decimal("0"), None
    return _decimal(row.refund_loss_amount), row.refund_currency_code


def _daily_loss_map(
    session: Session,
    *,
    items: Iterable[object],
    account_refs: frozenset[str],
) -> dict[tuple[date, str, str, str], Decimal]:
    keys = {
        (
            item.business_date_la,
            str(item.store_id),
            str(item.item_id),
            str(item.msku or "").strip(),
        )
        for item in items
    }
    accounts = _account_values(account_refs)
    if not keys or not accounts:
        return {}

    refund_msku = _normalized_msku(AFTER_SALES_REFUND_ITEMS.c.msku)
    statement = (
        select(
            _purchase_date().label("business_date_la"),
            AFTER_SALES_REFUND_ITEMS.c.store_id,
            AFTER_SALES_REFUND_ITEMS.c.item_id,
            refund_msku.label("msku"),
            func.coalesce(
                func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                0,
            ).label("refund_loss_amount"),
        )
        .where(
            AFTER_SALES_REFUND_ITEMS.c.source_account_ref.in_(accounts),
            AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
            AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
            AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
            tuple_(
                _purchase_date(),
                AFTER_SALES_REFUND_ITEMS.c.store_id,
                AFTER_SALES_REFUND_ITEMS.c.item_id,
                refund_msku,
            ).in_(list(keys)),
        )
        .group_by(
            _purchase_date(),
            AFTER_SALES_REFUND_ITEMS.c.store_id,
            AFTER_SALES_REFUND_ITEMS.c.item_id,
            refund_msku,
        )
    )
    return {
        (
            row.business_date_la,
            str(row.store_id),
            str(row.item_id),
            str(row.msku or "").strip(),
        ): _decimal(row.refund_loss_amount)
        for row in _safe_all(session, statement)
    }


def _order_profit_loss_summary(session: Session, base: object) -> tuple[Decimal, str | None]:
    refund_sku = _normalized_profit_sku(
        AFTER_SALES_REFUND_ITEMS.c.local_sku,
        AFTER_SALES_REFUND_ITEMS.c.item_id,
    )
    statement = (
        select(
            func.coalesce(
                func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                0,
            ).label("refund_loss_amount"),
            func.max(AFTER_SALES_REFUND_ITEMS.c.refund_currency_code).label("refund_currency_code"),
        )
        .select_from(base)
        .join(
            AFTER_SALES_REFUND_ITEMS,
            and_(
                base.c.business_date_la == _purchase_date(),
                base.c.source_account_ref == AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                base.c.local_sku == refund_sku,
            ),
        )
        .where(
            AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
            AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
            AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
        )
    )
    row = _safe_one_or_none(session, statement)
    if row is None:
        return Decimal("0"), None
    return _decimal(row.refund_loss_amount), row.refund_currency_code


def _order_profit_loss_map(
    session: Session,
    *,
    items: Iterable[object],
    account_refs: frozenset[str],
) -> dict[tuple[date, str], Decimal]:
    keys = {(item.business_date_la, str(item.local_sku)) for item in items}
    accounts = _account_values(account_refs)
    if not keys or not accounts:
        return {}

    refund_sku = _normalized_profit_sku(
        AFTER_SALES_REFUND_ITEMS.c.local_sku,
        AFTER_SALES_REFUND_ITEMS.c.item_id,
    )
    statement = (
        select(
            _purchase_date().label("business_date_la"),
            refund_sku.label("local_sku"),
            func.coalesce(
                func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                0,
            ).label("refund_loss_amount"),
        )
        .where(
            AFTER_SALES_REFUND_ITEMS.c.source_account_ref.in_(accounts),
            AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
            AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
            AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
            tuple_(_purchase_date(), refund_sku).in_(list(keys)),
        )
        .group_by(_purchase_date(), refund_sku)
    )
    return {
        (row.business_date_la, str(row.local_sku)): _decimal(row.refund_loss_amount)
        for row in _safe_all(session, statement)
    }


def _daily_trend_loss_map(session: Session, base: object) -> dict[date, Decimal]:
    refund_msku = _normalized_msku(AFTER_SALES_REFUND_ITEMS.c.msku)
    base_msku = _normalized_msku(base.c.msku)
    statement = (
        select(
            base.c.business_date_la.label("business_date_la"),
            func.coalesce(
                func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                0,
            ).label("refund_loss_amount"),
        )
        .select_from(base)
        .join(
            AFTER_SALES_REFUND_ITEMS,
            and_(
                base.c.business_date_la == _purchase_date(),
                base.c.source_account_ref == AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                base.c.store_id == AFTER_SALES_REFUND_ITEMS.c.store_id,
                base.c.item_id == AFTER_SALES_REFUND_ITEMS.c.item_id,
                base_msku == refund_msku,
            ),
        )
        .where(
            AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
            AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
            AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
        )
        .group_by(base.c.business_date_la)
    )
    return {
        row.business_date_la: _decimal(row.refund_loss_amount)
        for row in _safe_all(session, statement)
    }


def apply_daily_sales_refund_loss(
    session: Session,
    *,
    data: DailySalesListData,
    query: DailySalesQuery,
    account_refs: frozenset[str],
) -> None:
    """Overlay display-only refund actual loss on a Daily Sales response."""
    row_loss = _daily_loss_map(session, items=data.items, account_refs=account_refs)
    for item in data.items:
        item.refund_loss_amount = row_loss.get(
            (
                item.business_date_la,
                str(item.store_id),
                str(item.item_id),
                str(item.msku or "").strip(),
            ),
            Decimal("0"),
        )

    base = _daily_sales_base(
        _daily_sales_statement(session, query=query, account_refs=account_refs)
    )
    loss_amount, currency = _daily_loss_summary(session, base)
    data.summary.refund_loss_amount = loss_amount
    if currency:
        data.summary.refund_event_currency_code = currency


def apply_order_profit_refund_loss(
    session: Session,
    *,
    data: OrderProfitListData,
    query: OrderProfitQuery,
    account_refs: frozenset[str],
) -> None:
    """Overlay display-only refund actual loss on an Order Profit response."""
    row_loss = _order_profit_loss_map(session, items=data.items, account_refs=account_refs)
    for item in data.items:
        item.refund_loss_amount = row_loss.get(
            (item.business_date_la, str(item.local_sku)),
            Decimal("0"),
        )

    base = _order_profit_base(
        _order_profit_statement(session, query=query, account_refs=account_refs)
    )
    loss_amount, currency = _order_profit_loss_summary(session, base)
    data.summary.refund_loss_amount = loss_amount
    if currency:
        data.summary.refund_currency_code = currency


def apply_order_profit_trend_refund_loss(
    session: Session,
    *,
    data: OrderProfitTrendData,
    query: OrderProfitQuery,
    account_refs: frozenset[str],
) -> None:
    """Overlay display-only refund actual loss on Order Profit trend points."""
    daily_query = DailySalesQuery(
        start_date=query.start_date,
        end_date=query.end_date,
        platform=query.platform,
        store_id=query.store_id,
        owner_ref=query.owner_ref,
        search_field=query.search_field if query.search_field != "product_name" else "sku",
        keyword=query.keyword,
    )
    base = _daily_sales_base(
        _daily_sales_statement(session, query=daily_query, account_refs=account_refs)
    )
    by_date = _daily_trend_loss_map(session, base)
    for item in data.items:
        item.refund_loss_amount = by_date.get(item.date, Decimal("0"))
