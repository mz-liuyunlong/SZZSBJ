from __future__ import annotations

from decimal import Decimal

from app.modules.data_pages.schemas import (
    OrderProfitListData,
    OrderProfitSummaryRead,
    OrderProfitTrendData,
)

ORDER_PROFIT_GROSS_PROFIT_PERMISSION = "field:sales:order-profit:gross-profit"
ORDER_PROFIT_MARGIN_PERMISSION = "field:sales:order-profit:profit-margin"

_GROSS_PROFIT_EXPORT_COLUMNS = {"order_profit", "avg_profit_per_order"}
_MARGIN_EXPORT_COLUMNS = {"gross_margin", "roi"}


def filter_order_profit_export_columns(
    columns: str | None,
    *,
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
    available_columns: tuple[str, ...],
) -> str:
    requested = [item.strip() for item in (columns or "").split(",") if item.strip()]
    selected = requested or list(available_columns)
    if not can_view_gross_profit:
        selected = [key for key in selected if key not in _GROSS_PROFIT_EXPORT_COLUMNS]
    if not can_view_profit_margin:
        selected = [key for key in selected if key not in _MARGIN_EXPORT_COLUMNS]
    return ",".join(selected)


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
                    "gross_profit_amount": None,
                    "gross_profit_currency_code": None,
                    "average_profit_per_order": None,
                }
            )
        if not can_view_profit_margin:
            updates.update({"gross_margin": None, "roi": None})
        items.append(item.model_copy(update=updates) if updates else item)

    summary_updates: dict[str, object] = {}
    if not can_view_gross_profit:
        summary_updates.update(
            {
                "order_profit_amount": None,
                "order_profit_currency_code": None,
            }
        )
    summary = (
        data.summary.model_copy(update=summary_updates)
        if summary_updates
        else data.summary
    )
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
        if not can_view_profit_margin:
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
