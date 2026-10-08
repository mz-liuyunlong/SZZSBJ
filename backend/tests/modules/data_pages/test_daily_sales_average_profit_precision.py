from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart
from app.modules.data_pages.service import DailySalesService


@pytest.mark.parametrize(
    ("profit", "orders", "expected"),
    [
        (Decimal("10.0000"), Decimal("3"), Decimal("3.3333")),
        (Decimal("-10.0000"), Decimal("3"), Decimal("-3.3333")),
        (Decimal("10.0000"), Decimal("6"), Decimal("1.6667")),
        (Decimal("10.0000"), Decimal("4"), Decimal("2.5000")),
        (Decimal("10.0000"), Decimal("0"), None),
        (None, Decimal("3"), None),
    ],
)
def test_daily_sales_average_profit_precision(
    profit: Decimal | None,
    orders: Decimal,
    expected: Decimal | None,
) -> None:
    row = DailySalesItemDayMart(
        id=UUID(int=1),
        business_date_la=date(2026, 9, 1),
        business_timezone="America/Los_Angeles",
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        sales_qty=Decimal("3"),
        order_count=orders,
        sales_amount=Decimal("30.0000"),
        sales_currency_code="USD",
        sem_ad_spend_amount=Decimal("0"),
        gross_profit_amount=profit,
        gross_profit_currency_code="USD",
        cost_status="complete",
        missing_cost_codes_json=[],
        calculation_warnings_json=[],
        sales_7d_trend_json=[],
        calc_version="synthetic-v1",
        calculated_at=datetime(2026, 10, 8, tzinfo=UTC),
    )

    service = DailySalesService(MagicMock(spec=Session))
    item = service._to_read(row, None)

    assert item.average_profit_per_order == expected

    serialized = item.model_dump(
        mode="json",
        context={"preserve_decimal_places": True},
    )
    assert serialized["average_profit_per_order"] == (
        format(expected, "f") if expected is not None else None
    )
