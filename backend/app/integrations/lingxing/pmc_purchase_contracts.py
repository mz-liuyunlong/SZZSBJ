"""PMC purchase-board read-only endpoint contracts (Gate 2, PR-A).

Source of truth for field names and limits is the backend registry
``app/integrations/lingxing/data/official_verified_interfaces.csv`` (rows
``LX-03B82747B50A``, ``LX-D332F931885E``, ``LX-4B9473A2D2E1``) and the repository
contract snapshots under ``docs/integrations/lingxing/contracts/``. Nothing here
authorizes outbound traffic: real calls still require ``LINGXING_ENABLE_REAL_CALLS``,
a governance interface row with ``outbound_enabled`` and a manual run authorization.

All three endpoints are read-only, ``offset/length`` paginated, capped at 500 rows per
page and share ``token_bucket_capacity = 1`` on the provider side, so callers must
issue requests serially.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Literal, cast

from pydantic import JsonValue

PURCHASE_PLAN_ENDPOINT: Final = "/erp/sc/routing/data/local_inventory/getPurchasePlans"
PURCHASE_ORDER_ENDPOINT: Final = "/erp/sc/routing/data/local_inventory/purchaseOrderList"
RECEIPT_ORDER_ENDPOINT: Final = "/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList"

type PmcPurchaseEndpoint = Literal[
    "/erp/sc/routing/data/local_inventory/getPurchasePlans",
    "/erp/sc/routing/data/local_inventory/purchaseOrderList",
    "/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList",
]

PMC_PURCHASE_ENDPOINTS: frozenset[str] = frozenset(
    {PURCHASE_PLAN_ENDPOINT, PURCHASE_ORDER_ENDPOINT, RECEIPT_ORDER_ENDPOINT}
)

PMC_PURCHASE_OBJECT_PREFIX: Final = "pmc_purchase_"
PMC_PURCHASE_MAX_PAGE_SIZE: Final = 500
# Rocky 2026-09-19: production pulls start at 2026-08-01; earlier history only on request.
# Windows are bounded so a single manual run stays a bounded, reviewable unit of work.
PMC_PURCHASE_MAX_WINDOW_DAYS: Final = 90
PMC_PURCHASE_DATE_FORMAT: Final = "%Y-%m-%d"


@dataclass(frozen=True, slots=True)
class PmcPurchaseEndpointSpec:
    """Registry-derived request contract for one PMC purchase endpoint."""

    interface_key: str
    registry_interface_id: str
    api_path: PmcPurchaseEndpoint
    object_type: str
    allowed_body_fields: frozenset[str]
    required_body_fields: frozenset[str]
    store_field: str | None
    date_range_fields: tuple[str, str]
    date_dimension_field: str | None
    returns_total: bool
    max_page_size: int = PMC_PURCHASE_MAX_PAGE_SIZE

    @property
    def window_body_fields(self) -> frozenset[str]:
        fields = {"offset", "length", *self.date_range_fields}
        if self.date_dimension_field is not None:
            fields.add(self.date_dimension_field)
        return frozenset(fields)


PMC_PURCHASE_ENDPOINT_SPECS: dict[str, PmcPurchaseEndpointSpec] = {
    PURCHASE_PLAN_ENDPOINT: PmcPurchaseEndpointSpec(
        interface_key="purchasePlanList",
        registry_interface_id="LX-03B82747B50A",
        api_path=PURCHASE_PLAN_ENDPOINT,
        object_type=f"{PMC_PURCHASE_OBJECT_PREFIX}plan_list",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_date",
                "end_date",
                "search_field_time",
                "sids",
                "status",
                "plan_sns",
                "is_combo",
                "is_related_process_plan",
            }
        ),
        required_body_fields=frozenset({"offset", "length"}),
        # ``sids`` are Lingxing store ids, not the source account ref used for the
        # capture allowlist, so it is not modelled as the transport store_field.
        # Gate 2 pulls all stores; store attribution happens downstream.
        store_field=None,
        date_range_fields=("start_date", "end_date"),
        date_dimension_field="search_field_time",
        returns_total=True,
    ),
    PURCHASE_ORDER_ENDPOINT: PmcPurchaseEndpointSpec(
        interface_key="purchaseOrderList",
        registry_interface_id="LX-D332F931885E",
        api_path=PURCHASE_ORDER_ENDPOINT,
        object_type=f"{PMC_PURCHASE_OBJECT_PREFIX}order_list",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_date",
                "end_date",
                "search_field_time",
                "order_sn",
                "custom_order_sn",
                "purchase_type",
            }
        ),
        # Registry marks start_date / end_date as required for this endpoint.
        required_body_fields=frozenset({"offset", "length", "start_date", "end_date"}),
        store_field=None,
        date_range_fields=("start_date", "end_date"),
        date_dimension_field="search_field_time",
        # Registry: returns_total=否. Pagination must stop on a short page.
        returns_total=False,
    ),
    RECEIPT_ORDER_ENDPOINT: PmcPurchaseEndpointSpec(
        interface_key="purchaseReceiptOrderList",
        registry_interface_id="LX-4B9473A2D2E1",
        api_path=RECEIPT_ORDER_ENDPOINT,
        object_type=f"{PMC_PURCHASE_OBJECT_PREFIX}receipt_order_list",
        allowed_body_fields=frozenset(
            {
                "offset",
                "length",
                "start_date",
                "end_date",
                "date_type",
                "order_sns",
                "order_type",
                "qc_status",
                "status",
                "wid",
            }
        ),
        required_body_fields=frozenset({"offset", "length"}),
        store_field=None,
        date_range_fields=("start_date", "end_date"),
        date_dimension_field="date_type",
        returns_total=True,
    ),
}

PMC_PURCHASE_SPECS_BY_INTERFACE_KEY: dict[str, PmcPurchaseEndpointSpec] = {
    spec.interface_key: spec for spec in PMC_PURCHASE_ENDPOINT_SPECS.values()
}


class PmcPurchaseContractError(ValueError):
    """Raised before any network activity when a request would violate the contract."""


def get_pmc_purchase_spec(api_path: str) -> PmcPurchaseEndpointSpec:
    spec = PMC_PURCHASE_ENDPOINT_SPECS.get(api_path)
    if spec is None:
        raise PmcPurchaseContractError("PMC purchase endpoint is not registered")
    return spec


def validate_pmc_purchase_window(start_date: date, end_date: date) -> None:
    """Enforce the bounded date window every manual purchase run must respect."""

    if end_date < start_date:
        raise PmcPurchaseContractError("PMC purchase window end precedes start")
    if end_date - start_date > timedelta(days=PMC_PURCHASE_MAX_WINDOW_DAYS - 1):
        raise PmcPurchaseContractError("PMC purchase window exceeds the allowed span")


def build_pmc_purchase_page_body(
    api_path: str,
    *,
    offset: int,
    length: int,
    start_date: date,
    end_date: date,
    date_dimension: str | None = None,
    extra: JsonValue = None,
) -> JsonValue:
    """Build one offset-page request body that satisfies the endpoint contract.

    ``extra`` may carry additional documented filters (for example ``sids`` or
    ``status``); unknown keys or pagination/date overrides are rejected so signing
    input and transmitted JSON can never drift from the reviewed contract.
    """

    spec = get_pmc_purchase_spec(api_path)
    if isinstance(offset, bool) or isinstance(length, bool):
        raise PmcPurchaseContractError("PMC purchase pagination values are invalid")
    if offset < 0:
        raise PmcPurchaseContractError("PMC purchase offset is invalid")
    if not 1 <= length <= spec.max_page_size:
        raise PmcPurchaseContractError("PMC purchase page size is invalid")
    validate_pmc_purchase_window(start_date, end_date)

    start_field, end_field = spec.date_range_fields
    body: dict[str, Any] = {
        "offset": offset,
        "length": length,
        start_field: start_date.strftime(PMC_PURCHASE_DATE_FORMAT),
        end_field: end_date.strftime(PMC_PURCHASE_DATE_FORMAT),
    }
    if date_dimension is not None:
        if spec.date_dimension_field is None:
            raise PmcPurchaseContractError("PMC purchase endpoint has no date dimension")
        body[spec.date_dimension_field] = date_dimension

    if extra is not None:
        if not isinstance(extra, dict):
            raise PmcPurchaseContractError("PMC purchase extra filters must be an object")
        overlap = set(extra) & spec.window_body_fields
        if overlap:
            raise PmcPurchaseContractError("PMC purchase extra filters override window fields")
        unknown = set(extra) - spec.allowed_body_fields
        if unknown:
            raise PmcPurchaseContractError("PMC purchase extra filters are outside the contract")
        body.update(extra)

    missing = spec.required_body_fields - set(body)
    if missing:
        raise PmcPurchaseContractError("PMC purchase body is missing required fields")
    return cast(JsonValue, body)


def pmc_purchase_provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict) or "code" not in payload:
        return None
    return str(payload["code"])


def pmc_purchase_response_items(api_path: str, payload: JsonValue) -> list[JsonValue] | None:
    """Return the row array for a page, or ``None`` when the shape is not recognised.

    Plan and purchase-order responses carry rows directly in ``data``; the receipt
    endpoint nests them as ``data.list`` (contract snapshot ``warehouse-receipt-lx-4b9473a2d2e1``).
    """

    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if api_path == RECEIPT_ORDER_ENDPOINT:
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            return cast(list[JsonValue], data["list"])
        return None
    if isinstance(data, list):
        return data
    return None


def pmc_purchase_response_total(api_path: str, payload: JsonValue) -> int | None:
    """Return the provider total when the endpoint publishes one (never for purchase orders)."""

    spec = PMC_PURCHASE_ENDPOINT_SPECS.get(api_path)
    if spec is None or not spec.returns_total or not isinstance(payload, dict):
        return None
    container: JsonValue = payload
    if api_path == RECEIPT_ORDER_ENDPOINT:
        container = payload.get("data")
    if not isinstance(container, dict):
        return None
    total = container.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    return total


def pmc_purchase_response_succeeded(endpoint: str, response: object, payload: JsonValue) -> bool:
    """Success evaluator for ``LingxingReadonlyClient`` restricted to purchase endpoints."""

    del response
    return (
        endpoint in PMC_PURCHASE_ENDPOINTS
        and pmc_purchase_provider_code(payload) == "0"
        and pmc_purchase_response_items(endpoint, payload) is not None
    )
