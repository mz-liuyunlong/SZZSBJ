import inspect
from decimal import Decimal

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DAILY_SALES_V2_VERSION,
    DataPagesRealSyncRunner,
    _cost_totals,
    _estimated_refund_sales_amount,
    _money_decimal,
    _net_commission_after_refund,
)
from app.modules.product_management.daily_sales_costs import DailySalesCostResolution


def test_money_decimal_accepts_currency_formatted_zero() -> None:
    assert _money_decimal("$0.000000") == Decimal("0.000000")
    assert _money_decimal("USD 1,234.50") == Decimal("1234.50")
    assert _money_decimal("¥9.90") == Decimal("9.90")


def test_daily_sales_cost_totals_use_product_management_units_and_sales_qty() -> None:
    cost = DailySalesCostResolution(
        owner_ref="owner-a",
        purchase_cost_unit_cny=Decimal("14"),
        first_leg_cost_unit_cny=Decimal("7"),
        wfs_fee_unit_usd=Decimal("4.25"),
        storage_fee_unit_usd=Decimal("0.08"),
        exchange_rate=Decimal("7"),
        fx_date=None,
        fx_source="sku-pricing-defaults-v1",
        rule_version="sku-pricing-defaults-v1",
        calculation_status="ok",
        root_missing_codes=(),
    )

    purchase, first_leg, wfs, storage = _cost_totals(cost, Decimal("3"))

    assert purchase == Decimal("6")
    assert first_leg == Decimal("3")
    assert wfs == Decimal("12.75")
    assert storage == Decimal("0.24")


def test_daily_sales_uses_strict_triple_and_includes_sample_only_rows() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "store_id+item_id+msku" in source
    assert "select business_date_la,source_account_ref,store_id,item_id,msku from sample" in source
    assert "gross_sales_qty" in source
    assert "sample_order_count" in source
    assert "sample_qty" in source
    assert "cost_quantity" in source
    assert "coalesce(sample.sample_qty,0)" in source
    assert "after_sales_refund_items" in source
    assert "purchase_time_at::date=:day" in source
    assert "provider_refund_amount" in source
    assert "avg_paid_sales_price_x_return_qty" in source
    assert "calculation_warnings_json" in source
    assert "return_rate_30d" in source
    assert "fact_walmart_wfs_fee_actual" in source


def test_daily_sales_storage_fee_sql_matches_persisted_model_column() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "storage_fee_estimated_total_amount=:storage_total" in source
    assert "storage_fee_expected_total_amount" not in source


def test_daily_sales_sales_amount_does_not_subtract_refunds() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    expected_sales_formula = (
        "greatest(coalesce(s.sales_amount,0)-coalesce(sample.sample_amount,0),0)"
    )
    assert expected_sales_formula in source
    assert (
        "greatest(coalesce(s.sales_amount,0)-coalesce(sample.sample_amount,0)"
        "-coalesce(r.provider_refund_amount,0),0)" not in source
    )
    assert (
        "greatest(coalesce(s.sales_amount,0)-coalesce(sample.sample_amount,0)"
        "-coalesce(r.refund_amount,0),0)" not in source
    )


def test_daily_sales_refund_truth_does_not_use_legacy_refund_chain() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "after_sales_refund_items" in source
    assert "fact_walmart_refund_items" not in source
    assert "'refund_date_basis','purchase_time_at'" in source
    assert "dws_walmart_refund_business_amounts" not in source
    assert "REFUND_COMPLETED" not in source
    assert "purchaseTimeLocale" not in source


def test_daily_sales_uses_current_product_management_and_fact_backed_history() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "at=effective_at" not in source
    assert "Product Management current data is the single source of truth" in source
    assert "fact_walmart_sales_item_daily" in source
    assert "sales_history_7d_incomplete" in source
    assert "sales_history_30d_incomplete" in source
    legacy_history_query = (
        "from mart_daily_sales_item_day where source_account_ref=:account "
        "and business_date_la between"
    )
    assert legacy_history_query not in source


def test_rolling_return_rate_uses_refund_purchase_dates_without_timezone_conversion() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "r.purchase_time_at::date between :start_day and :end_day" in source
    assert "sum(coalesce(r.return_qty,0)) return_qty" in source
    assert "fact_walmart_refund_items" not in source
    assert "interval '15 hours'" not in source
    assert "timezone(" not in source
    assert "sale_day.business_date_la=r.purchase_time_at::date" in source
    assert "sale_day.allocation_status='direct'" in source


def test_daily_sales_preserves_sample_sales_amount() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "sum(coalesce(s.unit_price_amount,0)*coalesce(s.quantity,0)) sample_amount" in source
    assert "sample_amount=:sample_amount" not in source
    assert "sample_cost_amount" not in source


def test_daily_sales_profit_deducts_refund_sales_and_sem_spend_without_merging_ad_spend() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)
    order_profit_source = inspect.getsource(DataPagesRealSyncRunner._refresh_order_profit_mart)

    assert "m.sem_ad_spend_amount,m.commission_rate,m.commission_fee_amount" in source
    assert 'sem_ad_spend = _decimal(row["sem_ad_spend_amount"]) or Decimal("0")' in source
    assert "refund_amount = _estimated_refund_sales_amount" in source
    assert "net_commission = (" in source
    assert '- (refund_amount or Decimal("0"))' in source
    assert "- sem_ad_spend" in source
    assert "commission_fee_amount=:commission" in source
    assert "sum(coalesce(return_qty,0))" in order_profit_source
    assert "refund_loss_amount" in order_profit_source
    assert (
        "sum(coalesce(refund_amount,0) * (1 - coalesce(commission_rate,0)))" in order_profit_source
    )
    assert "sum(coalesce(ad_spend_amount,0))" in order_profit_source
    assert "sum(gross_profit_amount)" in order_profit_source


def test_order_profit_json_rollups_are_deterministically_ordered() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_order_profit_mart)

    assert "jsonb_agg(distinct item_id order by item_id)" in source
    assert "jsonb_agg(distinct store_id order by store_id)" in source


def test_refund_amount_uses_average_sales_price_and_return_qty() -> None:
    assert _estimated_refund_sales_amount(
        Decimal("40.00"),
        Decimal("4"),
        Decimal("2"),
    ) == Decimal("20.00")
    assert (
        _estimated_refund_sales_amount(
            Decimal("40.00"),
            Decimal("0"),
            Decimal("1"),
        )
        is None
    )
    assert _estimated_refund_sales_amount(
        Decimal("40.00"),
        Decimal("4"),
        Decimal("0"),
    ) == Decimal("0")


def test_daily_sales_profit_formula_returns_refunded_commission() -> None:
    sales = Decimal("10.00")
    refund_amount = _estimated_refund_sales_amount(
        sales,
        Decimal("1"),
        Decimal("1"),
    )
    assert refund_amount == Decimal("10.00")

    net_commission = _net_commission_after_refund(
        sales,
        refund_amount,
        Decimal("0.10"),
    )
    assert net_commission == Decimal("0.0000")

    gross_profit = sales - refund_amount - net_commission - Decimal("7.00")

    assert gross_profit == Decimal("-7.0000")


def test_daily_sales_calc_version_fits_persisted_varchar_64() -> None:
    assert DAILY_SALES_V2_VERSION.endswith("+refund-v3-lpds")
    assert len(DAILY_SALES_V2_VERSION) <= 64
