from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, String, and_, cast, column, func, select, table, tuple_
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.modules.data_pages.models import DailySalesItemDayMart, OrderProfitSkuDayMart


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


def _trimmed_text(value: object) -> object:
    return func.trim(cast(value, String))


def _normalized_msku(value: object) -> object:
    return func.coalesce(func.nullif(_trimmed_text(value), ""), "")


def _normalized_profit_sku(value: object, fallback_item_id: object) -> object:
    return func.coalesce(
        func.nullif(_trimmed_text(value), ""),
        func.nullif(_trimmed_text(fallback_item_id), ""),
        "",
    )


def _purchase_date() -> object:
    return cast(AFTER_SALES_REFUND_ITEMS.c.purchase_time_at, Date)


def _safe_execute_all(session: Session, statement: object) -> Sequence[object]:
    try:
        return session.execute(statement).all()
    except ProgrammingError as exc:
        message = str(exc).lower()
        if "after_sales_refund_items" in message and (
            "undefinedtable" in message or "does not exist" in message
        ):
            session.rollback()
            return []
        raise


class RefundLossRepository:
    """Read actual refund loss from after-sales refund facts.

    The refund-management page already owns the correct business amount in
    after_sales_refund_items.refund_loss_amount. Data Pages should display that
    value directly instead of recalculating refund_amount * (1 - commission_rate).
    These reads are display-only and must not participate in gross profit math.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def daily_sales_loss_map(
        self,
        rows: Sequence[DailySalesItemDayMart],
    ) -> dict[tuple[date, str, str, str, str], Decimal]:
        keys = {
            (
                row.business_date_la,
                row.source_account_ref,
                row.store_id,
                row.item_id,
                str(row.msku or "").strip(),
            )
            for row in rows
        }
        if not keys:
            return {}

        refund_msku = _normalized_msku(AFTER_SALES_REFUND_ITEMS.c.msku)
        statement = (
            select(
                _purchase_date().label("business_date_la"),
                AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                AFTER_SALES_REFUND_ITEMS.c.store_id,
                AFTER_SALES_REFUND_ITEMS.c.item_id,
                refund_msku.label("msku"),
                func.coalesce(
                    func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                    0,
                ).label("refund_loss_amount"),
            )
            .where(
                AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
                AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
                AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
                tuple_(
                    _purchase_date(),
                    AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                    AFTER_SALES_REFUND_ITEMS.c.store_id,
                    AFTER_SALES_REFUND_ITEMS.c.item_id,
                    refund_msku,
                ).in_(list(keys)),
            )
            .group_by(
                _purchase_date(),
                AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                AFTER_SALES_REFUND_ITEMS.c.store_id,
                AFTER_SALES_REFUND_ITEMS.c.item_id,
                refund_msku,
            )
        )

        return {
            (
                row.business_date_la,
                str(row.source_account_ref),
                str(row.store_id),
                str(row.item_id),
                str(row.msku or "").strip(),
            ): Decimal(str(row.refund_loss_amount or 0))
            for row in _safe_execute_all(self.session, statement)
        }

    def daily_sales_summary(
        self,
        statement: Select[tuple[DailySalesItemDayMart]],
    ) -> tuple[Decimal, str | None]:
        base = (
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
        rows = _safe_execute_all(self.session, self._daily_sales_summary_statement(base))
        if not rows:
            return Decimal("0"), None
        row = rows[0]
        return Decimal(str(row.refund_loss_amount or 0)), row.refund_currency_code

    def daily_sales_trend_summary(
        self,
        statement: Select[tuple[DailySalesItemDayMart]],
    ) -> dict[date, Decimal]:
        base = (
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
            row.business_date_la: Decimal(str(row.refund_loss_amount or 0))
            for row in _safe_execute_all(self.session, statement)
        }

    def order_profit_loss_map(
        self,
        rows: Sequence[OrderProfitSkuDayMart],
    ) -> dict[tuple[date, str, str], Decimal]:
        keys = {
            (row.business_date_la, row.source_account_ref, row.local_sku)
            for row in rows
        }
        if not keys:
            return {}

        refund_profit_sku = _normalized_profit_sku(
            AFTER_SALES_REFUND_ITEMS.c.local_sku,
            AFTER_SALES_REFUND_ITEMS.c.item_id,
        )
        statement = (
            select(
                _purchase_date().label("business_date_la"),
                AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                refund_profit_sku.label("local_sku"),
                func.coalesce(
                    func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                    0,
                ).label("refund_loss_amount"),
            )
            .where(
                AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
                AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
                AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
                tuple_(
                    _purchase_date(),
                    AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                    refund_profit_sku,
                ).in_(list(keys)),
            )
            .group_by(
                _purchase_date(),
                AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                refund_profit_sku,
            )
        )

        return {
            (
                row.business_date_la,
                str(row.source_account_ref),
                str(row.local_sku),
            ): Decimal(str(row.refund_loss_amount or 0))
            for row in _safe_execute_all(self.session, statement)
        }

    def order_profit_summary(
        self,
        statement: Select[tuple[OrderProfitSkuDayMart]],
    ) -> tuple[Decimal, str | None]:
        base = (
            statement.with_only_columns(
                OrderProfitSkuDayMart.business_date_la.label("business_date_la"),
                OrderProfitSkuDayMart.source_account_ref.label("source_account_ref"),
                OrderProfitSkuDayMart.local_sku.label("local_sku"),
            )
            .order_by(None)
            .distinct()
            .subquery()
        )
        refund_profit_sku = _normalized_profit_sku(
            AFTER_SALES_REFUND_ITEMS.c.local_sku,
            AFTER_SALES_REFUND_ITEMS.c.item_id,
        )
        statement = (
            select(
                func.coalesce(
                    func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                    0,
                ).label("refund_loss_amount"),
                func.max(AFTER_SALES_REFUND_ITEMS.c.refund_currency_code).label(
                    "refund_currency_code"
                ),
            )
            .select_from(base)
            .join(
                AFTER_SALES_REFUND_ITEMS,
                and_(
                    base.c.business_date_la == _purchase_date(),
                    base.c.source_account_ref == AFTER_SALES_REFUND_ITEMS.c.source_account_ref,
                    base.c.local_sku == refund_profit_sku,
                ),
            )
            .where(
                AFTER_SALES_REFUND_ITEMS.c.platform_code == "walmart",
                AFTER_SALES_REFUND_ITEMS.c.refund_loss_effective.is_(True),
                AFTER_SALES_REFUND_ITEMS.c.purchase_time_at.is_not(None),
            )
        )
        rows = _safe_execute_all(self.session, statement)
        if not rows:
            return Decimal("0"), None
        row = rows[0]
        return Decimal(str(row.refund_loss_amount or 0)), row.refund_currency_code

    @staticmethod
    def _daily_sales_summary_statement(base: object) -> object:
        refund_msku = _normalized_msku(AFTER_SALES_REFUND_ITEMS.c.msku)
        base_msku = _normalized_msku(base.c.msku)
        return (
            select(
                func.coalesce(
                    func.sum(func.coalesce(AFTER_SALES_REFUND_ITEMS.c.refund_loss_amount, 0)),
                    0,
                ).label("refund_loss_amount"),
                func.max(AFTER_SALES_REFUND_ITEMS.c.refund_currency_code).label(
                    "refund_currency_code"
                ),
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
