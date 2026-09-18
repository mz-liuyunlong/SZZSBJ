from app.main import create_app
from app.modules.data_pages.registry import DATA_PAGE_API_REGISTRY, registry_source_objects


def test_data_pages_registry_covers_expected_pages() -> None:
    assert set(DATA_PAGE_API_REGISTRY) == {
        "daily_sales",
        "order_profit",
        "listing_management",
    }

    expected_source_objects = {
        "daily_sales": [
            "mart_daily_sales_item_day",
            "fact_walmart_refund_items",
        ],
        "order_profit": ["mart_order_profit_sku_day"],
        "listing_management": ["mart_listing_management_current"],
    }

    for key, entry in DATA_PAGE_API_REGISTRY.items():
        assert entry.key == key
        assert entry.task_ref.startswith("DATA-PAGES-1")
        assert entry.route_path.startswith("/api/")
        assert entry.permission
        assert entry.mart_object.startswith("mart_")
        assert registry_source_objects(key) == expected_source_objects[key]
        assert entry.frontend_page.endswith(".tsx")
        assert entry.frontend_api_adapter.endswith("Api.ts")
        assert entry.empty_data_behavior
        assert entry.fallback_behavior
        assert entry.current_boundary
        assert len(entry.quality_checks) >= 4


def test_data_pages_registry_routes_exist_in_openapi() -> None:
    paths = create_app().openapi()["paths"]

    for entry in DATA_PAGE_API_REGISTRY.values():
        assert entry.route_path in paths
        assert "get" in paths[entry.route_path]


def test_data_pages_registry_is_read_only_and_mart_only() -> None:
    route_paths = [entry.route_path for entry in DATA_PAGE_API_REGISTRY.values()]
    mart_objects = [entry.mart_object for entry in DATA_PAGE_API_REGISTRY.values()]

    assert len(route_paths) == len(set(route_paths))
    assert len(mart_objects) == len(set(mart_objects))

    for entry in DATA_PAGE_API_REGISTRY.values():
        assert "RAW" not in entry.current_boundary.upper()
        assert "production database operation" in entry.current_boundary
        assert not entry.mart_object.startswith(("raw_", "ods_", "stg_", "fact_", "dim_"))
        assert all(check.strip() for check in entry.quality_checks)
