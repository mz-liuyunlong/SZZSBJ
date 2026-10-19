"""Domestic warehouse Lingxing endpoint contracts (Gate 2, phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Literal, cast

from pydantic import JsonValue

WAREHOUSE_LIST_ENDPOINT: Final = "/erp/sc/data/local_inventory/warehouse"
INVENTORY_DETAILS_ENDPOINT: Final = "/erp/sc/routing/data/local_inventory/inventoryDetails"
BATCH_DETAIL_LIST_ENDPOINT: Final = "/erp/sc/routing/data/local_inventory/getBatchDetailList"
BATCH_STATEMENT_LIST_ENDPOINT: Final = (
    "/erp/sc/routing/data/local_inventory/getBatchStatementList"
)

type PmcDomesticEndpoint = Literal[
    "/erp/sc/data/local_inventory/warehouse",
    "/erp/sc/routing/data/local_inventory/inventoryDetails",
    "/erp/sc/routing/data/local_inventory/getBatchDetailList",
    "/erp/sc/routing/data/local_inventory/getBatchStatementList",
]

PMC_DOMESTIC_ENDPOINTS: frozenset[str] = frozenset(
    {
        WAREHOUSE_LIST_ENDPOINT,
        INVENTORY_DETAILS_ENDPOINT,
        BATCH_DETAIL_LIST_ENDPOINT,
        BATCH_STATEMENT_LIST_ENDPOINT,
    }
)

PMC_DOMESTIC_OBJECT_PREFIX: Final = "pmc_domestic_"
PMC_DOMESTIC_DATE_FORMAT: Final = "%Y-%m-%d"
PMC_DOMESTIC_MAX_WINDOW_DAYS: Final = 90


class PmcDomesticContractError(ValueError):
    """Contract validation failed before any network call."""


@dataclass(frozen=True, slots=True)
class PmcDomesticEndpointSpec:
    interface_key: str
    registry_interface_id: str
    api_path: PmcDomesticEndpoint
    object_type: str
    allowed_body_fields: frozenset[str]
    required_body_fields: frozenset[str]
    max_page_size: int
    returns_total: bool
    requires_date_window: bool


PMC_DOMESTIC_ENDPOINT_SPECS: dict[str, PmcDomesticEndpointSpec] = {
    WAREHOUSE_LIST_ENDPOINT: PmcDomesticEndpointSpec(
        interface_key="domesticWarehouseList",
        registry_interface_id="LX-41E509578C0D",
        api_path=WAREHOUSE_LIST_ENDPOINT,
        object_type=f"{PMC_DOMESTIC_OBJECT_PREFIX}warehouse_list",
        allowed_body_fields=frozenset({"offset", "length", "is_delete", "sub_type", "type"}),
        required_body_fields=frozenset({"offset", "length"}),
        max_page_size=500,
        returns_total=True,
        requires_date_window=False,
    ),
    INVENTORY_DETAILS_ENDPOINT: PmcDomesticEndpointSpec(
        interface_key="domesticInventoryDetails",
        registry_interface_id="LX-41B3AF612B29",
        api_path=INVENTORY_DETAILS_ENDPOINT,
        object_type=f"{PMC_DOMESTIC_OBJECT_PREFIX}inventory_details",
        allowed_body_fields=frozenset({"offset", "length", "sku", "wid"}),
        required_body_fields=frozenset({"offset", "length"}),
        max_page_size=800,
        returns_total=True,
        requires_date_window=False,
    ),
    BATCH_DETAIL_LIST_ENDPOINT: PmcDomesticEndpointSpec(
        interface_key="domesticBatchDetailList",
        registry_interface_id="LX-1181D4F827FB",
        api_path=BATCH_DETAIL_LIST_ENDPOINT,
        object_type=f"{PMC_DOMESTIC_OBJECT_PREFIX}batch_detail_list",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "search_field",
                "search_value",
                "show_zero_stock",
                "stock_in_type_list",
                "wids",
            }
        ),
        required_body_fields=frozenset({"offset", "length"}),
        max_page_size=400,
        returns_total=True,
        requires_date_window=False,
    ),
    BATCH_STATEMENT_LIST_ENDPOINT: PmcDomesticEndpointSpec(
        interface_key="domesticBatchStatementList",
        registry_interface_id="LX-BCB9BCE2437F",
        api_path=BATCH_STATEMENT_LIST_ENDPOINT,
        object_type=f"{PMC_DOMESTIC_OBJECT_PREFIX}batch_statement_list",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_date",
                "end_date",
                "search_field",
                "search_value",
                "statement_type_list",
                "time_filter_field",
                "wid_list",
            }
        ),
        required_body_fields=frozenset(
            {"offset", "length", "start_date", "end_date", "time_filter_field"}
        ),
        max_page_size=400,
        returns_total=True,
        requires_date_window=True,
    ),
}


def get_pmc_domestic_spec(api_path: str) -> PmcDomesticEndpointSpec:
    spec = PMC_DOMESTIC_ENDPOINT_SPECS.get(api_path)
    if spec is None:
        raise PmcDomesticContractError("PMC domestic endpoint is not registered")
    return spec


def validate_pmc_domestic_window(start: date, end: date) -> None:
    if start > end:
        raise PmcDomesticContractError("PMC domestic window start is after end")
    if (end - start).days > PMC_DOMESTIC_MAX_WINDOW_DAYS:
        raise PmcDomesticContractError("PMC domestic window exceeds max days")


def build_pmc_domestic_page_body(
    api_path: str,
    *,
    offset: int,
    length: int,
    start_date: date | None = None,
    end_date: date | None = None,
    extra: JsonValue = None,
) -> JsonValue:
    spec = get_pmc_domestic_spec(api_path)
    if offset < 0:
        raise PmcDomesticContractError("PMC domestic offset is invalid")
    if not 1 <= length <= spec.max_page_size:
        raise PmcDomesticContractError("PMC domestic page size is invalid")
    if spec.requires_date_window:
        if start_date is None or end_date is None:
            raise PmcDomesticContractError("PMC domestic date window is required")
        validate_pmc_domestic_window(start_date, end_date)
    body: dict[str, Any] = {"offset": offset, "length": length}
    if spec.requires_date_window and start_date is not None and end_date is not None:
        body["start_date"] = start_date.strftime(PMC_DOMESTIC_DATE_FORMAT)
        body["end_date"] = end_date.strftime(PMC_DOMESTIC_DATE_FORMAT)
        body.setdefault("time_filter_field", "operate_time")
    if extra is not None:
        if not isinstance(extra, dict):
            raise PmcDomesticContractError("PMC domestic extra filters must be an object")
        unknown = set(extra) - spec.allowed_body_fields
        if unknown:
            raise PmcDomesticContractError("PMC domestic extra filters are outside the contract")
        body.update(extra)
    missing = spec.required_body_fields - set(body)
    if missing:
        raise PmcDomesticContractError("PMC domestic body is missing required fields")
    return cast(JsonValue, body)


def pmc_domestic_provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict) or "code" not in payload:
        return None
    return str(payload["code"])


def pmc_domestic_response_items(_api_path: str, payload: JsonValue) -> list[JsonValue] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list):
        return data
    return None


def pmc_domestic_response_total(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    return total


def pmc_domestic_response_succeeded(endpoint: str, response: object, payload: JsonValue) -> bool:
    del response
    return (
        endpoint in PMC_DOMESTIC_ENDPOINTS
        and pmc_domestic_provider_code(payload) == "0"
        and pmc_domestic_response_items(endpoint, payload) is not None
    )


def default_statement_window_end(today: date) -> tuple[date, date]:
    end = today
    start = end - timedelta(days=PMC_DOMESTIC_MAX_WINDOW_DAYS - 1)
    return start, end
