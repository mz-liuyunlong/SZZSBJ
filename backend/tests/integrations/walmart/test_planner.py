"""Offline tests: no Walmart, Tencent, SSH or database I/O."""
import pytest

from app.integrations.walmart.planner import API_SPECS, STORE_ROUTES, WalmartPlanError, plan_call


def test_routes_and_disabled_store() -> None:
    assert len(STORE_ROUTES) == 9
    assert STORE_ROUTES["HK2615"][1] == "43.135.153.225"
    assert STORE_ROUTES["CN2502"][1] is None


def test_colleague_get_catalog() -> None:
    assert len(API_SPECS) == 4
    assert set(API_SPECS) == {
        "wfs_inventory", "inbound_shipments",
        "inbound_shipment_items", "inventory_log",
    }


def test_authorized_plan() -> None:
    plan = plan_call(
        "HK2615", "wfs_inventory",
        {"limit": 20, "offset": 0},
        allowed_stores=frozenset({"HK2615"}),
    )
    assert plan.method == "GET"
    assert plan.path == "/v3/wfs/inventory"
    assert plan.expected_exit_ip == "43.135.153.225"


@pytest.mark.parametrize(
    ("store", "api", "params", "scope", "error"),
    [
        ("CN2502", "wfs_inventory", {}, frozenset({"CN2502"}), "COLLECTION_DISABLED"),
        ("UNKNOWN", "wfs_inventory", {}, frozenset({"UNKNOWN"}), "WALMART_STORE_UNKNOWN"),
        ("HK2615", "wfs_inventory", {}, frozenset(), "WALMART_STORE_FORBIDDEN"),
        ("HK2615", "not_registered", {}, frozenset({"HK2615"}), "WALMART_API_NOT_REGISTERED"),
        ("HK2615", "wfs_inventory", {"url": "https://example.com"}, frozenset({"HK2615"}), "WALMART_PARAM_NOT_ALLOWED"),
        ("HK2615", "wfs_inventory", {"limit": True}, frozenset({"HK2615"}), "WALMART_PARAMS_INVALID"),
        ("HK2615", "wfs_inventory", {"limit": 101}, frozenset({"HK2615"}), "WALMART_PARAMS_INVALID"),
        ("HK2615", "inbound_shipments", {"fromCreatedDate": 1700000000002, "toCreatedDate": 1700000000001}, frozenset({"HK2615"}), "WALMART_DATE_RANGE_INVALID"),
    ],
)
def test_fail_closed(store: str, api: str, params: dict[str, object],
                     scope: frozenset[str], error: str) -> None:
    with pytest.raises(WalmartPlanError, match=f"^{error}$"):
        plan_call(store, api, params, allowed_stores=scope)
