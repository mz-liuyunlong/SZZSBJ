"""Lingxing「查询WFS成本计价明细」contract (interface key LX-8437AD0BCB9E).

Contract snapshot: docs/integrations/lingxing/contracts/inventory-lx-8437ad0bcb9e.md.
The request deliberately omits ``businessType`` (full pull until the code coverage is
probed), ``sidList`` (all stores) and every search filter.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import JsonValue

WFS_COST_VALUATION_ENDPOINT: Final = "/basicOpen/multiplatform/wfs/cost/valuation/detail"
WFS_COST_VALUATION_INTERFACE_ID: Final = "LX-8437AD0BCB9E"
WFS_COST_VALUATION_OBJECT_TYPE: Final = "wfs_cost_valuation_flow"
WFS_COST_VALUATION_MAX_PAGE_SIZE: Final = 200
WFS_COST_VALUATION_MAX_WINDOW_DAYS: Final = 92
WFS_COST_VALUATION_DATE_TYPE_INOUT: Final = 0

WFS_COST_VALUATION_ALLOWED_BODY_FIELDS: Final = frozenset(
    {"startDate", "endDate", "dateType", "sortField", "sortType", "offset", "length"}
)
WFS_COST_VALUATION_REQUIRED_BODY_FIELDS: Final = frozenset(
    {"startDate", "endDate", "dateType", "offset", "length"}
)


class WfsCostValuationContractError(ValueError):
    """Contract validation failed before any network call."""


def validate_wfs_cost_valuation_window(start: date, end: date) -> None:
    if start > end or (end - start).days + 1 > WFS_COST_VALUATION_MAX_WINDOW_DAYS:
        raise WfsCostValuationContractError("WFS_COST_VALUATION_WINDOW_INVALID")


def build_wfs_cost_valuation_body(
    *, start: date, end: date, offset: int, length: int
) -> dict[str, JsonValue]:
    validate_wfs_cost_valuation_window(start, end)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise WfsCostValuationContractError("WFS_COST_VALUATION_OFFSET_INVALID")
    if (
        isinstance(length, bool)
        or not isinstance(length, int)
        or not 1 <= length <= WFS_COST_VALUATION_MAX_PAGE_SIZE
    ):
        raise WfsCostValuationContractError("WFS_COST_VALUATION_LENGTH_INVALID")
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dateType": WFS_COST_VALUATION_DATE_TYPE_INOUT,
        "sortField": "dateLocal",
        "sortType": "asc",
        "offset": offset,
        "length": length,
    }


def _page(payload: JsonValue) -> dict[str, JsonValue] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    page = data.get("page")
    return page if isinstance(page, dict) else None


def wfs_cost_valuation_provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict) or "code" not in payload:
        return None
    return str(payload["code"])


def wfs_cost_valuation_records(payload: JsonValue) -> list[JsonValue] | None:
    page = _page(payload)
    if page is None:
        return None
    records = page.get("records")
    return records if isinstance(records, list) else None


def wfs_cost_valuation_total(payload: JsonValue) -> int | None:
    page = _page(payload)
    if page is None:
        return None
    total = page.get("total")
    if isinstance(total, str) and total.isdigit():
        return int(total)
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    return total


def wfs_cost_valuation_response_succeeded(
    endpoint: str, response: object, payload: JsonValue
) -> bool:
    del response
    return (
        endpoint == WFS_COST_VALUATION_ENDPOINT
        and wfs_cost_valuation_provider_code(payload) == "0"
        and wfs_cost_valuation_records(payload) is not None
    )
