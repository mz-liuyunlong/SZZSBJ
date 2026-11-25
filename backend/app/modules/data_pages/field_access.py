from __future__ import annotations

from decimal import Decimal

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.sales_report_totals import redact_report_totals
from app.modules.data_pages.schemas import (
    DailySalesListData,
    DailySalesSummaryRead,
    OrderProfitListData,
    OrderProfitSummaryRead,
    OrderProfitTrendData,
    SalesReportTableTotalsRead,
)

ORDER_PROFIT_GROSS_PROFIT_PERMISSION = "field:sales:order-profit:gross-profit"
ORDER_PROFIT_MARGIN_PERMISSION = "field:sales:order-profit:profit-margin"

_GROSS_PROFIT_EXPORT_COLUMNS = {
    "refund_amount",
    "total_ad_spend",
    "ad_ratio",
    "ad_spend",
    "sem_ad_spend",
    "wfs_fee_total",
    "wfs_low_price_surcharge",
    "wfs_fee_unit",
    "commission",
    "purchase_cost_total",
    "purchase_unit_cny",
    "first_leg_cost_total",
    "first_leg_unit_cny",
    "storage_fee_total",
    "storage_unit",
    "total_cost",
    "order_profit",
    "avg_profit_per_order",
}
_MARGIN_EXPORT_COLUMNS = {"gross_margin", "roi"}

_PROFIT_FORMULA_ITEM_FIELDS = {
    "refund_amount": None,
    "refund_loss_amount": None,
    "ad_spend_amount": None,
    "sem_ad_spend_amount": None,
    "total_ad_spend_amount": None,
    "ad_ratio": None,
    "wfs_fee_unit_amount": None,
    "wfs_fee_total_amount": None,
    "wfs_low_price_surcharge_amount": None,
    "purchase_cost_unit_cny": None,
    "purchase_cost_total_usd": None,
    "first_leg_cost_unit_cny": None,
    "first_leg_cost_total_usd": None,
    "storage_fee_unit_amount": None,
    "storage_fee_total_amount": None,
    "commission_fee_amount": None,
    "total_cost_amount": None,
}

_DAILY_SALES_PROFIT_FORMULA_FIELDS = {
    **_PROFIT_FORMULA_ITEM_FIELDS,
    "wfs_fee_expected_unit_amount": None,
    "wfs_fee_expected_total_amount": None,
    "wfs_fee_actual_total_amount": None,
    "wfs_fee_variance_amount": None,
    "wfs_fee_variance_rate": None,
    "purchase_cost_estimated_total_usd": None,
    "purchase_cost_actual_total_usd": None,
    "first_leg_cost_estimated_total_usd": None,
    "first_leg_cost_actual_total_usd": None,
    "storage_fee_estimated_total_amount": None,
    "storage_fee_actual_total_amount": None,
    "exchange_rate": None,
    "commission_rate": None,
}


def filter_order_profit_export_columns(
    columns: str | None,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
    available_columns: tuple[str, ...],
) -> str:
    available = set(available_columns)
    if columns is None:
        selected = list(available_columns)
    else:
        selected = [item.strip() for item in columns.split(",") if item.strip()]
        if not selected or any(key not in available for key in selected):
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    if not can_view_gross_profit:
        selected = [key for key in selected if key not in _GROSS_PROFIT_EXPORT_COLUMNS]
    if not (can_view_gross_profit and can_view_profit_margin):
        selected = [key for key in selected if key not in _MARGIN_EXPORT_COLUMNS]
    return ",".join(selected)


def _existing_summary_table_totals(
    summary: DailySalesSummaryRead | OrderProfitSummaryRead,
) -> SalesReportTableTotalsRead:
    """Use only already-returned server aggregates; never read page rows."""
    fx = Decimal("6.6")  # Same convention as the existing statistics cards.

    def usd(value: Decimal | None, currency: str | None) -> Decimal | None:
        if value is None:
            return None
        return value / fx if currency == "CNY" else value

    def ratio(
        numerator: Decimal | None,
        denominator: Decimal | None,
        scale: int = 1,
    ) -> Decimal | None:
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return numerator / denominator * scale

    amounts = {
        "sales_amount": usd(summary.sales_amount, summary.sales_currency_code),
        "order_profit": usd(summary.order_profit_amount, summary.order_profit_currency_code),
        "ad_spend": usd(summary.ad_spend_amount, summary.ad_spend_currency_code),
        "sem_ad_spend": usd(summary.sem_ad_spend_amount, summary.ad_spend_currency_code),
        "total_ad_spend": usd(summary.total_ad_spend_amount, summary.ad_spend_currency_code),
    }
    counts: dict[str, Decimal | None] = {
        "sales_qty": summary.sales_qty,
        "order_count": summary.order_count,
    }
    if isinstance(summary, DailySalesSummaryRead):
        counts["wfs_inventory"] = summary.wfs_available_quantity
        # Daily card refund events and item-day refund attribution differ.
        # Do not silently replace one with the other.
    else:
        counts["return_qty"] = summary.return_qty
        amounts["refund_amount"] = usd(summary.refund_amount, summary.refund_currency_code)

    usd_values = {**counts, **amounts}
    cny_values = {
        **counts,
        **{key: value * fx if value is not None else None for key, value in amounts.items()},
    }
    for values in (usd_values, cny_values):
        values["avg_price"] = ratio(values["sales_amount"], values["sales_qty"])
        values["ad_ratio"] = ratio(values["total_ad_spend"], values["sales_amount"], 100)
        values["gross_margin"] = ratio(values["order_profit"], values["sales_amount"], 100)
    return SalesReportTableTotalsRead(usd=usd_values, cny=cny_values)


def filter_daily_sales_list_data(
    data: DailySalesListData,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
) -> DailySalesListData:
    """Redact profit-derived values exposed through the Daily Sales page."""

    items = []
    for item in data.items:
        updates: dict[str, object] = {}
        if not can_view_gross_profit:
            updates.update(
                {
                    **_DAILY_SALES_PROFIT_FORMULA_FIELDS,
                    "gross_profit_amount": None,
                    "gross_profit_currency_code": None,
                    "average_profit_per_order": None,
                }
            )
        if not (can_view_gross_profit and can_view_profit_margin):
            updates.update({"gross_margin": None, "roi": None})
        items.append(item.model_copy(update=updates) if updates else item)

    summary_updates: dict[str, object] = {
        "table_totals": redact_report_totals(
            data.summary.table_totals or _existing_summary_table_totals(data.summary),
            gross_keys=_GROSS_PROFIT_EXPORT_COLUMNS,
            margin_keys=_MARGIN_EXPORT_COLUMNS,
            can_view_gross_profit=can_view_gross_profit,
            can_view_profit_margin=can_view_profit_margin,
        ),
    }
    if not can_view_gross_profit:
        summary_updates.update(
            {
                "order_profit_amount": None,
                "order_profit_currency_code": None,
            }
        )
    summary = data.summary.model_copy(update=summary_updates) if summary_updates else data.summary
    return data.model_copy(update={"items": items, "summary": summary})


def filter_order_profit_list_data(
    data: OrderProfitListData,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
) -> OrderProfitListData:
    items = []
    for item in data.items:
        updates: dict[str, object] = {}
        if not can_view_gross_profit:
            updates.update(
                {
                    **_PROFIT_FORMULA_ITEM_FIELDS,
                    "gross_profit_amount": None,
                    "gross_profit_currency_code": None,
                    "average_profit_per_order": None,
                }
            )
        if not (can_view_gross_profit and can_view_profit_margin):
            updates.update({"gross_margin": None, "roi": None})
        items.append(item.model_copy(update=updates) if updates else item)

    summary_updates: dict[str, object] = {
        "table_totals": redact_report_totals(
            data.summary.table_totals or _existing_summary_table_totals(data.summary),
            gross_keys=_GROSS_PROFIT_EXPORT_COLUMNS,
            margin_keys=_MARGIN_EXPORT_COLUMNS,
            can_view_gross_profit=can_view_gross_profit,
            can_view_profit_margin=can_view_profit_margin,
        ),
    }
    if not can_view_gross_profit:
        summary_updates.update(
            {
                "order_profit_amount": None,
                "order_profit_currency_code": None,
            }
        )
    summary = data.summary.model_copy(update=summary_updates) if summary_updates else data.summary
    return data.model_copy(update={"items": items, "summary": summary})


def filter_order_profit_trend_data(
    data: OrderProfitTrendData,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
) -> OrderProfitTrendData:
    items = []
    for item in data.items:
        updates: dict[str, object] = {}
        if not can_view_gross_profit:
            updates.update(
                {
                    "order_profit_amount": None,
                    "order_profit_currency_code": None,
                }
            )
        if not (can_view_gross_profit and can_view_profit_margin):
            updates["profit_margin"] = None
        items.append(item.model_copy(update=updates) if updates else item)
    return data.model_copy(update={"items": items})


def empty_order_profit_summary() -> OrderProfitSummaryRead:
    """Build a schema-compatible empty summary for tests and safe fallbacks."""

    return OrderProfitSummaryRead(
        sales_qty=Decimal("0"),
        order_count=Decimal("0"),
        sales_amount=Decimal("0"),
        return_qty=Decimal("0"),
        refund_amount=Decimal("0"),
        refund_loss_amount=Decimal("0"),
        order_profit_amount=None,
        ad_spend_amount=Decimal("0"),
        sem_ad_spend_amount=Decimal("0"),
        total_ad_spend_amount=Decimal("0"),
    )


def require_sales_sort_access(
    field: str | None,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
) -> None:
    """Prevent hidden financial fields leaking through relative row order."""
    if field in _GROSS_PROFIT_EXPORT_COLUMNS and not can_view_gross_profit:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    if field in _MARGIN_EXPORT_COLUMNS and not (can_view_gross_profit and can_view_profit_margin):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
