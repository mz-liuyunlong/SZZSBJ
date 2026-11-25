from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Numeric, String, Table, create_engine, select
from sqlalchemy.dialects import postgresql

from app.modules.data_pages.field_access import (
    filter_daily_sales_list_data,
    filter_order_profit_list_data,
)
from app.modules.data_pages.models import DailySalesItemDayMart, OrderProfitSkuDayMart
from app.modules.data_pages.sales_report_totals import (
    COUNT_ATTRIBUTES,
    MONEY_ATTRIBUTES,
    merge_summary_statement,
    range_report_totals,
    report_totals_from_mapping,
    sql_aggregate_statement,
    sql_report_totals,
)
from app.modules.data_pages.schemas import (
    DailySalesListData,
    DailySalesSummaryRead,
    OrderProfitListData,
    OrderProfitSummaryRead,
    SalesReportTableTotalsRead,
)


def _row(**updates):
    values = dict.fromkeys((*COUNT_ATTRIBUTES.values(), *MONEY_ATTRIBUTES.values()), Decimal("0"))
    values.update(
        source_account_ref="allowed",
        item_id="a",
        exchange_rate=Decimal("7"),
        purchase_cost_unit_cny=Decimal("14"),
        first_leg_cost_unit_cny=Decimal("10"),
        cost_quantity=2,
    )
    values.update(updates)
    return values


def _rows():
    return [
        _row(
            sales_qty=2,
            sales_amount=20,
            order_count=2,
            gross_profit_amount=2,
            purchase_cost_total_usd=4,
            first_leg_cost_total_usd=3,
            ad_spend_amount=1,
        ),
        _row(
            item_id="b",
            sales_qty=3,
            sales_amount=90,
            order_count=1,
            gross_profit_amount=-5,
            exchange_rate=6,
            purchase_cost_unit_cny=12,
            first_leg_cost_unit_cny=12,
            cost_quantity=3,
            purchase_cost_total_usd=6,
            first_leg_cost_total_usd=6,
            ad_spend_amount=4,
            sem_ad_spend_amount=1,
        ),
    ]


def test_sql_footer_preserves_scope_and_ignores_paging():
    metadata = MetaData()
    numeric = (
        set(COUNT_ATTRIBUTES.values())
        | set(MONEY_ATTRIBUTES.values())
        | {
            "exchange_rate",
            "purchase_cost_unit_cny",
            "first_leg_cost_unit_cny",
            "cost_quantity",
        }
    )
    table = Table(
        "sales_totals_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("source_account_ref", String),
        Column("item_id", String),
        *(Column(name, Numeric()) for name in sorted(numeric)),
    )
    model = SimpleNamespace(**dict(table.c.items()))
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            _rows() + [_row(source_account_ref="denied", sales_qty=1000, sales_amount=10000)],
        )
        base = select(table).where(table.c.source_account_ref == "allowed")
        first = sql_report_totals(
            connection,
            base.order_by(table.c.sales_qty.asc()).limit(1),
            model,
            daily=True,
            inventory=20,
        )
        second = sql_report_totals(
            connection,
            base.order_by(table.c.sales_qty.desc()).offset(1).limit(1),
            model,
            daily=True,
            inventory=20,
        )
        assert first == second
        assert first["usd"]["sales_qty"] == 5
        assert first["usd"]["order_count"] == 3
        assert first["usd"]["sales_amount"] == 110
        assert first["cny"]["sales_amount"] == 680
        assert first["usd"]["avg_price"] == 22
        assert first["cny"]["avg_price"] == 136
        assert first["usd"]["order_profit"] == -3
        assert first["cny"]["order_profit"] == -16
        assert first["usd"]["purchase_cost_total"] == 10
        assert first["cny"]["purchase_cost_total"] == 64
        assert first["usd"]["total_ad_spend"] == 6
        assert first["usd"]["roi"] == Decimal(-3) / Decimal(19)
        assert first["usd"]["return_rate_30d"] is None
        assert first["usd"]["wfs_inventory"] == 20
        connection.execute(
            table.update()
            .where(table.c.item_id == "b")
            .values(
                gross_profit_amount=None,
                purchase_cost_total_usd=None,
                purchase_cost_unit_cny=None,
            )
        )
        partial = sql_report_totals(connection, base, model, daily=True)
        assert partial["usd"]["order_profit"] is None
        assert partial["usd"]["purchase_cost_total"] is None
        assert partial["cny"]["purchase_cost_total"] is None
        assert partial["usd"]["gross_margin"] is None
        assert partial["usd"]["roi"] is None
        empty = sql_report_totals(
            connection, base.where(table.c.item_id == "missing"), model, daily=True
        )
        assert empty["usd"]["sales_qty"] == 0
        assert empty["usd"]["sales_amount"] == 0
        assert empty["usd"]["avg_price"] is None
    engine.dispose()


@pytest.mark.parametrize(
    "model,daily", [(DailySalesItemDayMart, True), (OrderProfitSkuDayMart, False)]
)
def test_postgresql_footer_query_has_no_paging(model, daily):
    query = select(model).where(model.source_account_ref == "allowed").limit(10).offset(20)
    sql = str(
        sql_aggregate_statement(query, model, daily=daily).compile(
            dialect=postgresql.dialect(),
        )
    ).upper()
    assert "LIMIT" not in sql and "OFFSET" not in sql and "ORDER BY" not in sql
    assert "SOURCE_ACCOUNT_REF" in sql and "SUM(" in sql


def test_range_totals_use_raw_cost_completeness_and_one_inventory_per_group():
    rows = [SimpleNamespace(**row) for row in _rows()]
    rows.append(
        SimpleNamespace(
            **_row(sales_qty=1, sales_amount=10, order_count=1, gross_profit_amount=None)
        )
    )
    grouped = [
        SimpleNamespace(wfs_available_quantity=12),
        SimpleNamespace(wfs_available_quantity=8),
    ]
    totals = range_report_totals(rows, grouped)
    assert totals["usd"]["sales_qty"] == 6
    assert totals["usd"]["sales_amount"] == 120
    assert totals["usd"]["wfs_inventory"] == 20
    assert totals["usd"]["order_profit"] is None
    assert totals["cny"]["sales_amount"] == Decimal("792")
    grouped[1].wfs_available_quantity = None
    assert range_report_totals(rows, grouped)["usd"]["wfs_inventory"] is None


@pytest.mark.parametrize("daily", [True, False])
def test_footer_permission_redaction(daily):
    totals = SalesReportTableTotalsRead.model_validate(
        range_report_totals(
            [SimpleNamespace(**row) for row in _rows()],
            [SimpleNamespace(wfs_available_quantity=20)],
        )
    )
    if daily:
        data = DailySalesListData(items=[], summary=DailySalesSummaryRead(table_totals=totals))
        redact = filter_daily_sales_list_data
    else:
        data = OrderProfitListData(items=[], summary=OrderProfitSummaryRead(table_totals=totals))
        redact = filter_order_profit_list_data
    restricted = redact(data, can_view_gross_profit=False, can_view_profit_margin=False)
    assert restricted.summary.table_totals is not None
    for values in (restricted.summary.table_totals.usd, restricted.summary.table_totals.cny):
        assert values["sales_qty"] == 5
        assert values["wfs_inventory"] == 20
        for key in (
            "order_profit",
            "avg_profit_per_order",
            "total_cost",
            "gross_margin",
            "roi",
            "ad_spend",
            "total_ad_spend",
            "refund_amount",
            "purchase_cost_total",
        ):
            assert values[key] is None
    no_margin = redact(data, can_view_gross_profit=True, can_view_profit_margin=False)
    assert no_margin.summary.table_totals is not None
    assert no_margin.summary.table_totals.usd["order_profit"] == -3
    assert no_margin.summary.table_totals.usd["gross_margin"] is None
    assert no_margin.summary.table_totals.usd["roi"] is None
    full = redact(data, can_view_gross_profit=True, can_view_profit_margin=True)
    assert full.summary.table_totals == totals


@pytest.mark.parametrize(
    "model,daily", [(DailySalesItemDayMart, True), (OrderProfitSkuDayMart, False)]
)
def test_footer_columns_share_existing_summary_select(model, daily):
    from sqlalchemy import func

    base = select(func.sum(model.sales_qty)).where(model.source_account_ref == "allowed")
    merged = merge_summary_statement(base, model, daily=daily)
    sql = str(merged.compile(dialect=postgresql.dialect())).upper()
    assert sql.count("SELECT ") == 1
    assert sql.count(" FROM ") + sql.count("\nFROM ") == 1
    assert "LIMIT" not in sql and "OFFSET" not in sql
    assert "SOURCE_ACCOUNT_REF" in sql
    assert "USD_SALES_QTY" in sql and "CNY_SALES_AMOUNT" in sql


def test_combined_summary_matches_separate_aggregate():
    from sqlalchemy import func

    metadata = MetaData()
    numeric = (
        set(COUNT_ATTRIBUTES.values())
        | set(MONEY_ATTRIBUTES.values())
        | {
            "exchange_rate",
            "purchase_cost_unit_cny",
            "first_leg_cost_unit_cny",
            "cost_quantity",
        }
    )
    table = Table(
        "combined_totals_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("source_account_ref", String),
        Column("item_id", String),
        *(Column(name, Numeric()) for name in sorted(numeric)),
    )
    model = SimpleNamespace(**dict(table.c.items()))
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(), _rows() + [_row(source_account_ref="denied", sales_qty=1000)]
        )
        base = select(table).where(table.c.source_account_ref == "allowed")
        expected = sql_report_totals(connection, base, model, daily=True, inventory=20)
        summary = base.with_only_columns(
            func.sum(table.c.sales_qty), func.sum(table.c.sales_amount)
        )
        combined = connection.execute(merge_summary_statement(summary, model, daily=True)).one()
        assert combined[0] == 5 and combined[1] == 110
        assert report_totals_from_mapping(combined._mapping, inventory=20) == expected
    engine.dispose()


def test_existing_summary_footer_uses_no_page_rows_and_respects_permissions():
    daily = DailySalesListData(
        items=[],
        summary=DailySalesSummaryRead(
            sales_qty=Decimal("5"),
            order_count=Decimal("4"),
            sales_amount=Decimal("100"),
            order_profit_amount=Decimal("20"),
            ad_spend_amount=Decimal("8"),
            sem_ad_spend_amount=Decimal("2"),
            total_ad_spend_amount=Decimal("10"),
            wfs_available_quantity=Decimal("30"),
            refund_event_qty=Decimal("99"),
        ),
    )
    allowed = filter_daily_sales_list_data(
        daily,
        can_view_gross_profit=True,
        can_view_profit_margin=True,
    ).summary.table_totals
    assert allowed is not None
    assert allowed.usd["sales_qty"] == 5
    assert allowed.usd["avg_price"] == 20
    assert allowed.usd["gross_margin"] == 20
    assert allowed.cny["sales_amount"] == 660
    assert allowed.usd["wfs_inventory"] == 30
    assert allowed.usd.get("return_qty") is None
    assert allowed.usd.get("purchase_cost_total") is None
    denied = filter_daily_sales_list_data(
        daily,
        can_view_gross_profit=False,
        can_view_profit_margin=False,
    ).summary.table_totals
    assert denied is not None
    assert denied.usd["sales_qty"] == 5
    assert denied.usd["order_profit"] is None
    assert denied.usd["ad_spend"] is None
    assert denied.usd["gross_margin"] is None
    profit = OrderProfitListData(
        items=[],
        summary=OrderProfitSummaryRead(
            sales_qty=Decimal("5"),
            sales_amount=Decimal("100"),
            return_qty=Decimal("2"),
            refund_amount=Decimal("15"),
        ),
    )
    totals = filter_order_profit_list_data(
        profit,
        can_view_gross_profit=True,
        can_view_profit_margin=True,
    ).summary.table_totals
    assert totals is not None
    assert totals.usd["return_qty"] == 2
    assert totals.usd["refund_amount"] == 15
    assert totals.usd.get("wfs_inventory") is None
