"""WFS shipment-board Lingxing endpoint contracts (read-only).

Two multi-platform warehouse endpoints feed the WFS shipment board:

* ``queryWFSCargoPage``   — WFS cargo (Walmart inbound shipment) headers with the nested
  ``cargo_good_list`` (declared / shipped / received / damaged per MSKU).
* ``queryShippingListPage`` — platform-warehouse shipping lists (SP orders) that carry the
  warehouse, carrier/channel, actual departure/arrival and tracking for a cargo.

Both are ``offset``/``length`` pages (max 200) with an optional creation-time window in
``Y-m-d`` and return ``data.total`` (string) plus ``data.records``.  The provider documents
``queryShippingListPage`` as "write" in the registry export; it is a query endpoint with no
side effect, and this module only ever sends it page/window filters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal, cast

from pydantic import JsonValue

WFS_CARGO_PAGE_ENDPOINT: Final = "/cepf/warehouse/api/openApi/queryWFSCargoPage"
WFS_SHIPPING_LIST_PAGE_ENDPOINT: Final = "/cepf/warehouse/api/openApi/queryShippingListPage"

type PmcWfsEndpoint = Literal[
    "/cepf/warehouse/api/openApi/queryWFSCargoPage",
    "/cepf/warehouse/api/openApi/queryShippingListPage",
]

PMC_WFS_ENDPOINTS: frozenset[str] = frozenset(
    {WFS_CARGO_PAGE_ENDPOINT, WFS_SHIPPING_LIST_PAGE_ENDPOINT}
)

PMC_WFS_OBJECT_PREFIX: Final = "pmc_wfs_"
PMC_WFS_DATE_FORMAT: Final = "%Y-%m-%d"
PMC_WFS_MAX_PAGE_SIZE: Final = 200
# Creation-time windows may span the whole WFS history we track (2026-06-01 onwards).
PMC_WFS_MAX_WINDOW_DAYS: Final = 400


class PmcWfsContractError(ValueError):
    """Contract validation failed before any network call."""


@dataclass(frozen=True, slots=True)
class PmcWfsEndpointSpec:
    interface_key: str
    registry_interface_id: str
    api_path: PmcWfsEndpoint
    object_type: str
    allowed_body_fields: frozenset[str]
    required_body_fields: frozenset[str]
    max_page_size: int
    returns_total: bool
    requires_date_window: bool


PMC_WFS_ENDPOINT_SPECS: dict[str, PmcWfsEndpointSpec] = {
    WFS_CARGO_PAGE_ENDPOINT: PmcWfsEndpointSpec(
        interface_key="wfsCargoPage",
        registry_interface_id="LX-C95DBD64F2A9",
        api_path=WFS_CARGO_PAGE_ENDPOINT,
        object_type=f"{PMC_WFS_OBJECT_PREFIX}cargo_page",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_time",
                "end_time",
                "store_id",
                "cargo_status_list",
                "update_time_ge",
                "update_time_le",
                "cargo_update_time_ge",
                "cargo_update_time_le",
                "inbound_order_id",
            }
        ),
        required_body_fields=frozenset({"offset", "length"}),
        max_page_size=PMC_WFS_MAX_PAGE_SIZE,
        returns_total=True,
        requires_date_window=True,
    ),
    WFS_SHIPPING_LIST_PAGE_ENDPOINT: PmcWfsEndpointSpec(
        interface_key="wfsShippingListPage",
        registry_interface_id="LX-C99E2D00C76D",
        api_path=WFS_SHIPPING_LIST_PAGE_ENDPOINT,
        object_type=f"{PMC_WFS_OBJECT_PREFIX}shipping_list_page",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_time",
                "end_time",
                "store_id",
                "shipping_list_status",
                "shipping_list_codes",
                "cargo_code",
            }
        ),
        required_body_fields=frozenset({"offset", "length"}),
        max_page_size=PMC_WFS_MAX_PAGE_SIZE,
        returns_total=True,
        requires_date_window=True,
    ),
}

PMC_WFS_SPECS_BY_INTERFACE_KEY: dict[str, PmcWfsEndpointSpec] = {
    spec.interface_key: spec for spec in PMC_WFS_ENDPOINT_SPECS.values()
}


def get_pmc_wfs_spec(api_path: str) -> PmcWfsEndpointSpec:
    spec = PMC_WFS_ENDPOINT_SPECS.get(api_path)
    if spec is None:
        raise PmcWfsContractError("PMC WFS endpoint is not registered")
    return spec


def validate_pmc_wfs_window(start: date, end: date) -> None:
    if start > end:
        raise PmcWfsContractError("PMC WFS window start is after end")
    if (end - start).days > PMC_WFS_MAX_WINDOW_DAYS:
        raise PmcWfsContractError("PMC WFS window exceeds max days")


def build_pmc_wfs_page_body(
    api_path: str,
    *,
    offset: int,
    length: int,
    start_date: date | None = None,
    end_date: date | None = None,
    extra: JsonValue = None,
) -> JsonValue:
    """Build the exact JSON body sent to Lingxing; refuses anything outside the contract."""

    spec = get_pmc_wfs_spec(api_path)
    if isinstance(offset, bool) or offset < 0:
        raise PmcWfsContractError("PMC WFS offset is invalid")
    if isinstance(length, bool) or not 1 <= length <= spec.max_page_size:
        raise PmcWfsContractError("PMC WFS page size is invalid")
    if spec.requires_date_window:
        if start_date is None or end_date is None:
            raise PmcWfsContractError("PMC WFS date window is required")
        validate_pmc_wfs_window(start_date, end_date)
    body: dict[str, Any] = {"offset": offset, "length": length}
    if start_date is not None and end_date is not None:
        body["start_time"] = start_date.strftime(PMC_WFS_DATE_FORMAT)
        body["end_time"] = end_date.strftime(PMC_WFS_DATE_FORMAT)
    if extra is not None:
        if not isinstance(extra, dict):
            raise PmcWfsContractError("PMC WFS extra filters must be an object")
        unknown = set(extra) - spec.allowed_body_fields
        if unknown:
            raise PmcWfsContractError("PMC WFS extra filters are outside the contract")
        body.update(extra)
    missing = spec.required_body_fields - set(body)
    if missing:
        raise PmcWfsContractError("PMC WFS body is missing required fields")
    return cast(JsonValue, body)


def pmc_wfs_provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict) or "code" not in payload:
        return None
    return str(payload["code"])


def pmc_wfs_response_items(_api_path: str, payload: JsonValue) -> list[JsonValue] | None:
    """``data.records`` for both endpoints; ``None`` when the shape is not a record page."""

    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    records = data.get("records")
    if isinstance(records, list):
        return records
    return None


def pmc_wfs_response_total(payload: JsonValue) -> int | None:
    """``data.total`` arrives as a numeric string ("806"); accept int or digit strings."""

    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    total = data.get("total")
    if isinstance(total, bool):
        return None
    if isinstance(total, int):
        return total if total >= 0 else None
    if isinstance(total, str) and total.strip().isdigit():
        return int(total.strip())
    return None


def pmc_wfs_response_succeeded(endpoint: str, response: object, payload: JsonValue) -> bool:
    del response
    return (
        endpoint in PMC_WFS_ENDPOINTS
        and pmc_wfs_provider_code(payload) == "0"
        and pmc_wfs_response_items(endpoint, payload) is not None
    )
