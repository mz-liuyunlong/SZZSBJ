from datetime import date

import pytest

from app.modules.data_pages.registry import DATA_PAGE_API_REGISTRY
from app.modules.integration_sync.data_pages_mart_refresh import (
    DATA_PAGES_MART_REFRESH_SPECS,
    DataPagesMartRefreshPlanError,
    build_mart_refresh_plan,
    mart_refresh_keys,
    mart_refresh_spec_for,
)


def test_mart_refresh_specs_match_data_page_registry() -> None:
    assert mart_refresh_keys() == frozenset(DATA_PAGE_API_REGISTRY)
    assert len(DATA_PAGES_MART_REFRESH_SPECS) == 3

    for key, spec in DATA_PAGES_MART_REFRESH_SPECS.items():
        assert spec.mart_table == DATA_PAGE_API_REGISTRY[key].mart_object
        assert spec.refresh_mode == "delete_insert"
        assert spec.source_tables


def test_daily_sales_refresh_depends_on_all_dim_and_fact_sources() -> None:
    spec = mart_refresh_spec_for("daily_sales")

    assert spec.requires_business_date_window is True
    assert spec.granularity == "business_date_item"
    assert set(spec.source_tables) == {
        "dim_lingxing_stores",
        "dim_walmart_listings",
        "dim_walmart_advertisers",
        "fact_walmart_sales_item_daily",
        "fact_walmart_order_items",
        "fact_walmart_refund_items",
        "fact_walmart_ad_item_sp_daily",
    }


def test_order_profit_refresh_depends_on_daily_sales_mart_and_profit_facts() -> None:
    spec = mart_refresh_spec_for("order_profit")

    assert spec.requires_business_date_window is True
    assert spec.granularity == "business_date_sku"
    assert "mart_daily_sales_item_day" in spec.source_tables
    assert "fact_walmart_order_items" in spec.source_tables
    assert "fact_walmart_refund_items" in spec.source_tables


def test_listing_management_refresh_can_build_current_snapshot_plan() -> None:
    plan = build_mart_refresh_plan(
        "listing_management",
        source_account_ref="default",
    )

    assert plan.mart_table == "mart_listing_management_current"
    assert plan.business_date_from is None
    assert plan.business_date_to is None
    assert "dim_walmart_listings" in plan.source_tables


def test_business_date_marts_require_date_window() -> None:
    with pytest.raises(DataPagesMartRefreshPlanError) as exc_info:
        build_mart_refresh_plan("daily_sales", source_account_ref="default")

    assert str(exc_info.value) == "DATA_PAGES_MART_REFRESH_WINDOW_REQUIRED"


def test_mart_refresh_plan_rejects_invalid_window() -> None:
    with pytest.raises(DataPagesMartRefreshPlanError) as exc_info:
        build_mart_refresh_plan(
            "order_profit",
            source_account_ref="default",
            business_date_from=date(2026, 9, 2),
            business_date_to=date(2026, 9, 1),
        )

    assert str(exc_info.value) == "DATA_PAGES_MART_REFRESH_WINDOW_INVALID"


def test_mart_refresh_plan_rejects_unsafe_account_ref() -> None:
    with pytest.raises(DataPagesMartRefreshPlanError) as exc_info:
        build_mart_refresh_plan(
            "listing_management",
            source_account_ref=" default",
        )

    assert str(exc_info.value) == "DATA_PAGES_MART_REFRESH_SOURCE_ACCOUNT_REF_INVALID"


def test_mart_refresh_plan_captures_safe_business_window() -> None:
    plan = build_mart_refresh_plan(
        "daily_sales",
        source_account_ref="default",
        business_date_from=date(2026, 9, 1),
        business_date_to=date(2026, 9, 2),
    )

    assert plan.key == "daily_sales"
    assert plan.refresh_mode == "delete_insert"
    assert plan.business_date_from == date(2026, 9, 1)
    assert plan.business_date_to == date(2026, 9, 2)
