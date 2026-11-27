from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.api import ApiError
from app.modules.data_pages.field_access import require_sales_sort_access
from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    OrderProfitSkuDayMart,
    WalmartListingInventoryDailyFact,
)
from app.modules.data_pages.sales_report_sort import (
    DAILY_FIELDS,
    PROFIT_FIELDS,
    profit_value,
    sort_export_rows,
    sort_values,
    sql_order,
)
from app.modules.data_pages.schemas import DailySalesQuery, OrderProfitQuery


@pytest.mark.parametrize("daily", [True, False])
@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("currency", ["USD", "CNY"])
def test_every_sort_compiles(daily, direction, currency):
    model = DailySalesItemDayMart if daily else OrderProfitSkuDayMart
    for field in DAILY_FIELDS if daily else PROFIT_FIELDS:
        order = sql_order(
            model,
            field,
            direction,
            currency,
            daily=daily,
            inventory=WalmartListingInventoryDailyFact if daily else None,
        )
        statement = select(model).order_by(order, model.id.asc()).offset(50).limit(50)
        sql = str(statement.compile(dialect=postgresql.dialect())).upper()
        assert "NULLS LAST" in sql
        assert sql.index("ORDER BY") < sql.index("LIMIT")


@pytest.mark.parametrize("schema", [DailySalesQuery, OrderProfitQuery])
def test_sort_query_rejects_unknown_fields_and_directions(schema):
    assert schema(sort_field="sales_qty", sort_direction="desc").sort_field == "sales_qty"
    with pytest.raises(ValidationError):
        schema(sort_field="gross_profit_amount; DROP TABLE x")
    with pytest.raises(ValidationError):
        schema(sort_direction="bad")


@pytest.mark.parametrize("field", ["order_profit", "ad_spend", "refund_amount", "total_cost"])
def test_profit_sort_rejected_without_profit_permission(field):
    with pytest.raises(ApiError):
        require_sales_sort_access(field, can_view_gross_profit=False, can_view_profit_margin=False)


@pytest.mark.parametrize("field", ["gross_margin", "roi"])
def test_margin_sort_rejected_without_both_permissions(field):
    with pytest.raises(ApiError):
        require_sales_sort_access(field, can_view_gross_profit=True, can_view_profit_margin=False)
    with pytest.raises(ApiError):
        require_sales_sort_access(field, can_view_gross_profit=False, can_view_profit_margin=True)
    require_sales_sort_access(field, can_view_gross_profit=True, can_view_profit_margin=True)


def test_global_sort_ties_zero_negative_null_and_export():
    values = [(4, None), (3, Decimal("0")), (2, Decimal("-2")), (1, Decimal("0"))]
    for direction, expected in [("asc", [2, 1, 3, 4]), ("desc", [1, 3, 2, 4])]:
        sorted_rows = sort_values(values, lambda row: row[1], direction, lambda row: row[0])
        assert [r[0] for r in sorted_rows] == expected
        assert [r[0] for r in sorted_rows[:2] + sorted_rows[2:]] == expected
    export_rows = [("2026-01-01", {"product_id": str(k), "order_profit": v}) for k, v in values]
    assert [r[1]["product_id"] for r in sort_export_rows(export_rows, "order_profit", "asc")] == [
        "2",
        "1",
        "3",
        "4",
    ]
    require_sales_sort_access(
        "sales_qty", can_view_gross_profit=False, can_view_profit_margin=False
    )


def test_profit_sort_uses_aggregated_values_not_day_rows():
    grouped = [
        SimpleNamespace(id="a", sales_amount=Decimal("60"), sales_qty=Decimal("6")),
        SimpleNamespace(id="b", sales_amount=Decimal("50"), sales_qty=Decimal("2")),
        SimpleNamespace(id="c", sales_amount=Decimal("0"), sales_qty=Decimal("0")),
    ]
    ordered = sort_values(grouped, lambda r: profit_value(r, "avg_price"), "desc", lambda r: r.id)
    assert [r.id for r in ordered] == ["b", "a", "c"]


@pytest.mark.parametrize("schema", [DailySalesQuery, OrderProfitQuery])
def test_identity_sort_fields_are_not_supported(schema):
    for field in ("store", "owner", "sku", "msku", "product_id"):
        with pytest.raises(ValidationError):
            schema(sort_field=field)


def test_sales_sort_field_counts():
    assert len(DAILY_FIELDS) == 30
    assert len(PROFIT_FIELDS) == 31
