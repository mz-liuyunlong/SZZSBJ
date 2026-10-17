import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.modules.data_pages import daily_sales_export, order_profit_export
from app.modules.data_pages.field_access import filter_order_profit_export_columns


def _financial_row() -> SimpleNamespace:
    return SimpleNamespace(
        business_date_la=date(2026, 10, 17),
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        store_name="Synthetic Store",
        item_id="synthetic-item",
        msku="synthetic-msku",
        local_sku="synthetic-sku",
        local_name="Synthetic Product",
        title="Synthetic Product",
        owner_ref="synthetic-owner",
        platform_code="walmart",
        gross_sales_qty=Decimal("5"),
        gross_order_count=Decimal("4"),
        gross_sales_amount=Decimal("100"),
        sales_qty=Decimal("5"),
        order_count=Decimal("4"),
        sales_amount=Decimal("100"),
        sample_order_count=Decimal("0"),
        sample_qty=Decimal("0"),
        cost_quantity=Decimal("5"),
        sample_amount=Decimal("0"),
        return_qty=Decimal("1"),
        refund_amount=Decimal("2"),
        return_rate_30d=Decimal("0.2"),
        ad_spend_amount=Decimal("3"),
        sem_ad_spend_amount=Decimal("4"),
        wfs_fee_total_amount=Decimal("5"),
        wfs_low_price_surcharge_amount=Decimal("1"),
        wfs_fee_unit_amount=Decimal("1"),
        commission_fee_amount=Decimal("6"),
        purchase_cost_total_usd=Decimal("20"),
        purchase_cost_unit_cny=Decimal("28"),
        first_leg_cost_total_usd=Decimal("10"),
        first_leg_cost_unit_cny=Decimal("14"),
        storage_fee_total_amount=Decimal("2"),
        storage_fee_unit_amount=Decimal("0.4"),
        gross_profit_amount=Decimal("14"),
        cost_status="complete",
    )


class _DailyRepository:
    def daily_sales_inventory_snapshot_map(self, _rows: object) -> dict[object, object]:
        return {}


@pytest.mark.parametrize("dimension", ["item_id", "sku", "msku"])
@pytest.mark.parametrize("requested", [None, "sales_amount,total_cost,order_profit,roi"])
def test_daily_sales_real_csv_excludes_profit_reconstruction_columns(
    monkeypatch: pytest.MonkeyPatch,
    requested: str | None,
    dimension: daily_sales_export.DailySalesExportDimension,
) -> None:
    row = _financial_row()
    monkeypatch.setattr(
        daily_sales_export,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [row],
    )
    columns = filter_order_profit_export_columns(
        requested,
        can_view_gross_profit=False,
        can_view_profit_margin=False,
        available_columns=tuple(daily_sales_export.DAILY_SALES_EXPORT_COLUMNS),
    )
    csv_content, filename = daily_sales_export.export_daily_sales_csv(
        SimpleNamespace(repository=_DailyRepository()),  # type: ignore[arg-type]
        query=SimpleNamespace(start_date=date(2026, 10, 17), end_date=date(2026, 10, 17)),
        account_refs=frozenset({"synthetic-account"}),
        period="day",
        dimension=dimension,
        columns=columns,
    )

    records = list(csv.reader(StringIO(csv_content)))
    assert len(records) == 2
    assert "销售额" in records[0]
    assert not {
        "退款金额",
        "总广告费",
        "WFS总配送费",
        "佣金",
        "采购总成本",
        "头程总成本",
        "仓储费",
        "总成本",
        "订单利润",
        "平均利润/单",
        "利润率",
        "ROI",
    } & set(records[0])
    assert "100" in records[1]
    assert f"-{dimension}-" in filename


@pytest.mark.parametrize("dimension", ["item_id", "sku", "msku"])
@pytest.mark.parametrize("requested", [None, "sales_amount,total_cost,order_profit,roi"])
def test_order_profit_real_csv_excludes_profit_reconstruction_columns(
    monkeypatch: pytest.MonkeyPatch,
    requested: str | None,
    dimension: order_profit_export.OrderProfitExportDimension,
) -> None:
    row = _financial_row()
    monkeypatch.setattr(
        order_profit_export,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [row],
    )
    monkeypatch.setattr(
        order_profit_export,
        "_current_wfs_inventory_by_item",
        lambda _service, _rows, _store_id: {},
    )
    columns = filter_order_profit_export_columns(
        requested,
        can_view_gross_profit=False,
        can_view_profit_margin=False,
        available_columns=tuple(order_profit_export.ORDER_PROFIT_EXPORT_COLUMNS),
    )
    csv_content, filename = order_profit_export.export_order_profit_csv(
        SimpleNamespace(),  # type: ignore[arg-type]
        query=SimpleNamespace(
            start_date=date(2026, 10, 17),
            end_date=date(2026, 10, 17),
            store_id=None,
        ),
        account_refs=frozenset({"synthetic-account"}),
        period="day",
        dimension=dimension,
        columns=columns,
    )

    records = list(csv.reader(StringIO(csv_content)))
    assert len(records) == 2
    assert "销售额" in records[0]
    assert not {
        "退款金额",
        "总广告费",
        "WFS总配送费",
        "佣金",
        "采购总成本",
        "头程总成本",
        "仓储费",
        "总成本",
        "订单利润",
        "平均利润/单",
        "利润率",
        "ROI",
    } & set(records[0])
    assert "100" in records[1]
    assert f"-{dimension}-" in filename


def test_empty_default_csv_keeps_only_safe_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        daily_sales_export,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [],
    )
    columns = filter_order_profit_export_columns(
        None,
        can_view_gross_profit=False,
        can_view_profit_margin=False,
        available_columns=tuple(daily_sales_export.DAILY_SALES_EXPORT_COLUMNS),
    )
    csv_content, _ = daily_sales_export.export_daily_sales_csv(
        SimpleNamespace(repository=_DailyRepository()),  # type: ignore[arg-type]
        query=SimpleNamespace(start_date=None, end_date=None),
        account_refs=frozenset({"synthetic-account"}),
        period="day",
        dimension="item_id",
        columns=columns,
    )

    records = list(csv.reader(StringIO(csv_content)))
    assert len(records) == 1
    assert "总成本" not in records[0]
    assert "订单利润" not in records[0]
    assert "ROI" not in records[0]


@pytest.mark.parametrize(
    ("available_columns", "requested"),
    [
        (tuple(daily_sales_export.DAILY_SALES_EXPORT_COLUMNS), "unknown_column"),
        (tuple(daily_sales_export.DAILY_SALES_EXPORT_COLUMNS), "sales_amount,unknown_column"),
        (tuple(daily_sales_export.DAILY_SALES_EXPORT_COLUMNS), " , "),
        (tuple(order_profit_export.ORDER_PROFIT_EXPORT_COLUMNS), "unknown_column"),
        (tuple(order_profit_export.ORDER_PROFIT_EXPORT_COLUMNS), "sales_amount,unknown_column"),
        (tuple(order_profit_export.ORDER_PROFIT_EXPORT_COLUMNS), " , "),
    ],
)
def test_export_filter_rejects_unknown_mixed_and_empty_columns(
    available_columns: tuple[str, ...],
    requested: str,
) -> None:
    with pytest.raises(ApiError) as error:
        filter_order_profit_export_columns(
            requested,
            can_view_gross_profit=False,
            can_view_profit_margin=False,
            available_columns=available_columns,
        )

    assert error.value.status_code == 422
    assert error.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("columns", [None, "", "unknown_column", "sales_amount,unknown_column"])
def test_daily_sales_exporter_invalid_columns_fail_closed_without_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
    columns: str | None,
) -> None:
    monkeypatch.setattr(
        daily_sales_export,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [_financial_row()],
    )

    csv_content, _ = daily_sales_export.export_daily_sales_csv(
        SimpleNamespace(repository=_DailyRepository()),  # type: ignore[arg-type]
        query=SimpleNamespace(start_date=None, end_date=None),
        account_refs=frozenset({"synthetic-account"}),
        period="day",
        dimension="item_id",
        columns=columns,
    )

    assert list(csv.reader(StringIO(csv_content))) == [
        ["统计日期"],
        ["2026-10-17"],
    ]


@pytest.mark.parametrize("columns", [None, "", "unknown_column", "sales_amount,unknown_column"])
def test_order_profit_exporter_invalid_columns_fail_closed_without_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
    columns: str | None,
) -> None:
    monkeypatch.setattr(
        order_profit_export,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [_financial_row()],
    )
    monkeypatch.setattr(
        order_profit_export,
        "_current_wfs_inventory_by_item",
        lambda _service, _rows, _store_id: {},
    )

    csv_content, _ = order_profit_export.export_order_profit_csv(
        SimpleNamespace(),  # type: ignore[arg-type]
        query=SimpleNamespace(start_date=None, end_date=None, store_id=None),
        account_refs=frozenset({"synthetic-account"}),
        period="day",
        dimension="item_id",
        columns=columns,
    )

    assert list(csv.reader(StringIO(csv_content))) == [
        ["统计日期"],
        ["2026-10-17"],
    ]


@pytest.mark.parametrize("export_kind", ["daily_sales", "order_profit"])
def test_explicit_sensitive_only_real_csv_stays_empty(
    monkeypatch: pytest.MonkeyPatch,
    export_kind: str,
) -> None:
    is_daily_sales = export_kind == "daily_sales"
    export_module = daily_sales_export if is_daily_sales else order_profit_export
    available_columns = tuple(
        daily_sales_export.DAILY_SALES_EXPORT_COLUMNS
        if is_daily_sales
        else order_profit_export.ORDER_PROFIT_EXPORT_COLUMNS
    )
    columns = filter_order_profit_export_columns(
        "refund_amount,total_ad_spend,wfs_fee_total,purchase_cost_total,order_profit,roi",
        can_view_gross_profit=False,
        can_view_profit_margin=False,
        available_columns=available_columns,
    )
    assert columns == ""

    monkeypatch.setattr(
        export_module,
        "_filtered_daily_sales_rows",
        lambda _service, **_kwargs: [_financial_row()],
    )
    query = SimpleNamespace(start_date=None, end_date=None, store_id=None)
    if is_daily_sales:
        csv_content, _ = daily_sales_export.export_daily_sales_csv(
            SimpleNamespace(repository=_DailyRepository()),  # type: ignore[arg-type]
            query=query,
            account_refs=frozenset({"synthetic-account"}),
            period="day",
            dimension="item_id",
            columns=columns,
        )
    else:
        monkeypatch.setattr(
            order_profit_export,
            "_current_wfs_inventory_by_item",
            lambda _service, _rows, _store_id: {},
        )
        csv_content, _ = order_profit_export.export_order_profit_csv(
            SimpleNamespace(),  # type: ignore[arg-type]
            query=query,
            account_refs=frozenset({"synthetic-account"}),
            period="day",
            dimension="item_id",
            columns=columns,
        )

    assert list(csv.reader(StringIO(csv_content))) == [
        ["统计日期"],
        ["2026-10-17"],
    ]
