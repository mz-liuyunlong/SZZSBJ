"""Application package bootstrap hooks."""

from app.modules.data_pages.order_profit_range_aggregation import (
    install_order_profit_range_summary,
)

install_order_profit_range_summary()
