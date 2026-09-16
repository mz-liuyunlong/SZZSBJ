from app.modules.integration_sync.data_pages_catalog import (
    DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY,
)
from app.modules.integration_sync.data_pages_request_plans import (
    DATA_PAGES_REQUEST_PLAN_SPECS,
    data_pages_request_plan_parser_keys,
    request_plan_for,
    sync_interface_for_request_plan,
)


def test_request_plans_cover_every_data_pages_sync_interface() -> None:
    assert data_pages_request_plan_parser_keys() == frozenset(
        DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY
    )


def test_request_plan_endpoint_paths_match_sync_catalog() -> None:
    for plan in DATA_PAGES_REQUEST_PLAN_SPECS:
        sync_interface = sync_interface_for_request_plan(plan.parser_key)
        assert plan.endpoint_path == sync_interface.endpoint_path
        assert plan.page_size_field
        assert (plan.page_field is None) != (plan.offset_field is None)


def test_sale_stat_plan_requires_explicit_result_type_fanout() -> None:
    plan = request_plan_for("sale_stat_page_list")

    assert plan.static_body_dict()["data_type"] == 1
    assert plan.fanout_field == "result_type"
    assert plan.fanout_values == (1, 2, 3)
    assert plan.date_window_kind == "date"
    assert plan.start_field == "start_date"
    assert plan.end_field == "end_date"
    assert plan.store_scope_field == "sids"


def test_order_plan_uses_global_purchase_time_window() -> None:
    plan = request_plan_for("order_v2_list")

    assert plan.static_body_dict()["date_type"] == "global_purchase_time"
    assert plan.date_window_kind == "datetime"
    assert plan.start_field == "start_time"
    assert plan.end_field == "end_time"
    assert plan.store_scope_field == "store_id"


def test_return_plan_keeps_only_refund_records() -> None:
    plan = request_plan_for("walmart_return_order_list")

    assert plan.static_body_dict()["dateType"] == "1"
    assert plan.static_body_dict()["returnTypeList"] == ("REFUND",)
    assert plan.date_window_kind == "date"
    assert plan.store_scope_field == "storeIdList"


def test_ad_item_plan_depends_on_advertiser_list() -> None:
    plan = request_plan_for("walmart_ad_item_sp_list")

    assert plan.dependency_parser_key == "walmart_advertiser_list"
    assert "advertiserIds" in plan.runtime_required_fields
    assert "campaignType" in plan.runtime_required_fields
    assert plan.date_window_kind == "date"


def test_listing_plan_keeps_initial_no_store_filter_boundary() -> None:
    plan = request_plan_for("walmart_listing_list")

    assert plan.store_scope_field is None
    assert plan.static_body_fields == ()
