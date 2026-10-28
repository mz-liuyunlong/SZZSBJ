"""Offline Walmart API request planning. No credentials, HTTP, or SSH."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

# References are names only, never credential values.
STORE_ROUTES: dict[str, tuple[str, str | None]] = {
    "HK2612": ("HK2612", "43.153.1.194"),
    "HK2613": ("HK2613", "43.153.26.207"),
    "HK2614": ("HK2614", "43.153.101.213"),
    "HK2615": ("HK2615", "43.135.153.225"),
    "CN2501": ("YC006", "43.173.120.215"),
    "CN2502": ("", None),  # Eligible; dedicated fixed egress not configured yet.
    "CN2601": ("YC005", "43.173.115.200"),
    "CN2602": ("YC007", "43.173.92.40"),
    "CN2603": ("YC008", "43.172.73.203"),
}

# Taken from the colleague's four-capability GET-only worker.
API_SPECS: dict[str, tuple[str, frozenset[str]]] = {
    "wfs_inventory": ("/v3/wfs/inventory", frozenset({"limit", "offset"})),
    "inbound_shipments": (
        "/v3/fulfillment/inbound-shipments",
        frozenset(
            {
                "limit",
                "offset",
                "fromCreateDate",
                "toCreateDate",
                "shipmentId",
                "inboundOrderId",
                "status",
            }
        ),
    ),
    "inbound_shipment_items": (
        "/v3/fulfillment/inbound-shipment-items",
        frozenset({"limit", "offset", "shipmentId"}),
    ),
    "inventory_log": (
        "/v3/fulfillment/inventory-log",
        frozenset(
            {
                "limit",
                "offset",
                "gtin",
                "startDate",
                "endDate",
                "shipmentId",
                "transactionType",
                "transactionLocation",
                "sort_by",
                "sort_order",
            }
        ),
    ),
}


class WalmartPlanError(ValueError):
    """Only stable error codes; never expose supplied credentials or values."""


@dataclass(frozen=True, slots=True)
class WalmartPlan:
    store_code: str
    api_key: str
    method: str
    path: str
    params: Mapping[str, str | int]
    expected_exit_ip: str


def plan_call(
    store_code: str,
    api_key: str,
    params: Mapping[str, object] | None = None,
    *,
    allowed_stores: frozenset[str] = frozenset(),
) -> WalmartPlan:
    """Return a validated offline plan; it cannot perform a real API call."""
    if store_code not in STORE_ROUTES:
        raise WalmartPlanError("WALMART_STORE_UNKNOWN")
    if store_code not in allowed_stores:
        raise WalmartPlanError("WALMART_STORE_FORBIDDEN")
    route = STORE_ROUTES[store_code]
    # Unconfigured stores cannot silently use another store's egress.
    if route[1] is None:
        raise WalmartPlanError("WALMART_EXIT_UNAVAILABLE")
    if api_key not in API_SPECS:
        raise WalmartPlanError("WALMART_API_NOT_REGISTERED")
    path, allowed = API_SPECS[api_key]
    provided = params if params is not None else {}
    if not isinstance(provided, Mapping) or len(provided) > 8:
        raise WalmartPlanError("WALMART_PARAMS_INVALID")
    normalized: dict[str, str | int] = {}
    for key, value in provided.items():
        if key not in allowed:
            raise WalmartPlanError("WALMART_PARAM_NOT_ALLOWED")
        if key == "limit":
            if type(value) is not int or not 1 <= value <= 100:
                raise WalmartPlanError("WALMART_PARAMS_INVALID")
        elif key == "offset":
            if type(value) is not int or not 0 <= value <= 1000000:
                raise WalmartPlanError("WALMART_PARAMS_INVALID")
        elif key in {"fromCreateDate", "toCreateDate", "startDate", "endDate"}:
            if not isinstance(value, str) or not 8 <= len(value) <= 40:
                raise WalmartPlanError("WALMART_PARAMS_INVALID")
            try:
                if key in {"startDate", "endDate"}:
                    date.fromisoformat(value)
                    if len(value) != 10:
                        raise ValueError("date must use YYYY-MM-DD")
                else:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if not (value.endswith("Z") or "+00:00" in value):
                        raise ValueError("datetime must be UTC")
            except ValueError:
                raise WalmartPlanError("WALMART_PARAMS_INVALID") from None
        elif not isinstance(value, str) or not 1 <= len(value) <= 64 or not value.isascii():
            raise WalmartPlanError("WALMART_PARAMS_INVALID")
        normalized[key] = value
    for start, end in (("startDate", "endDate"), ("fromCreateDate", "toCreateDate")):
        if start in normalized and end in normalized and normalized[start] > normalized[end]:
            raise WalmartPlanError("WALMART_DATE_RANGE_INVALID")
    return WalmartPlan(store_code, api_key, "GET", path, normalized, route[1])
