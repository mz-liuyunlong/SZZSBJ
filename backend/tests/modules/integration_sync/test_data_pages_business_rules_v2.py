import inspect
from decimal import Decimal

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DataPagesRealSyncRunner,
    _cost_totals,
    _money_decimal,
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
    assert "coalesce(r.refund_amount,0)" in source
    assert "calculation_warnings_json" in source
    assert "return_rate_30d" in source
    assert "fact_walmart_wfs_fee_actual" in source


def test_daily_sales_storage_fee_sql_matches_persisted_model_column() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "storage_fee_estimated_total_amount=:storage_total" in source
    assert "storage_fee_expected_total_amount" not in source


def test_refund_match_requires_store_item_and_msku() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._match_refund_order_line)

    assert "and store_id=cast(:store_id as text)" in source
    assert "and item_id=cast(:item_id as text)" in source
    assert "and trim(msku)=trim(cast(:msku as text))" in source
    assert "local_sku" not in source.split("where source_account_ref", 1)[1]


def test_daily_sales_uses_current_product_management_and_fact_backed_history() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "at=effective_at" not in source
    assert "Product Management current data is the single source of truth" in source
    assert "fact_walmart_sales_item_daily" in source
    assert "sales_history_7d_incomplete" in source
    assert "sales_history_30d_incomplete" in source
    assert (
        "from mart_daily_sales_item_day where source_account_ref=:account and business_date_la between"
        not in source
    )


def test_refund_attribution_requires_matching_salestat_key() -> None:
    source = inspect.getsource(DataPagesRealSyncRunner._refresh_daily_sales_mart)

    assert "and exists (" in source
    assert "select 1 from s where s.source_account_ref=f.source_account_ref" in source
    assert "and s.business_date_la=b.business_date_la" in source
