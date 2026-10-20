"""Read-only, complete Lingxing settlement pagination."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from time import sleep
from typing import Any

INTERFACE_ID = "LX-DB6D62E9EE37"


class WfsCollectionError(ValueError):
    """Safe collection error."""


@dataclass(frozen=True)
class WfsCollectionResult:
    rows: tuple[dict[str, Any], ...]
    total: int
    pages: int


PageFetcher = Callable[[str, Mapping[str, Any]], Any]


def collect_wfs_settlements(
    *,
    fetch_page: PageFetcher,
    store_id: str,
    start_date: date,
    end_date: date,
    msku: str | None = None,
    page_size: int = 20,
    max_pages: int = 500,
    interval_seconds: float = 0,
) -> WfsCollectionResult:
    if (
        not store_id.isdigit()
        or start_date > end_date
        or not 1 <= page_size <= 20
        or max_pages < 1
        or interval_seconds < 0
        or (msku is not None and not msku.strip())
    ):
        raise WfsCollectionError("WFS_INVALID_SCOPE")

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    expected_total: int | None = None

    for page in range(max_pages):
        params: dict[str, Any] = {
            "offset": page * page_size,
            "length": page_size,
            "sids": store_id,
            "platformCodeS": ["10008"],
            "transactionTypeS": [0],
            "currencyCode": "USD",
            "searchDateType": "2",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }
        if msku is not None:
            params["searchField"] = "msku"
            params["searchValue"] = msku.strip()

        response = fetch_page(INTERFACE_ID, params)
        if not isinstance(response, dict) or response.get("code") != 0:
            raise WfsCollectionError("WFS_PROVIDER_ERROR")

        data = response.get("data")
        rows = data.get("list") if isinstance(data, dict) else None
        top_total = response.get("total")
        nested_total = data.get("total") if isinstance(data, dict) else None

        if top_total is not None and nested_total is not None and top_total != nested_total:
            raise WfsCollectionError("WFS_CONFLICTING_TOTAL")

        total = top_total if top_total is not None else nested_total

        if (
            not isinstance(rows, list)
            or type(total) is not int
            or total < 0
            or len(rows) > page_size
        ):
            raise WfsCollectionError("WFS_INVALID_PAGE")

        if expected_total is None:
            expected_total = total
            if total > page_size * max_pages:
                raise WfsCollectionError("WFS_PAGE_LIMIT")
        elif total != expected_total:
            raise WfsCollectionError("WFS_TOTAL_CHANGED")

        for row in rows:
            if not isinstance(row, dict):
                raise WfsCollectionError("WFS_INVALID_ROW")
            uid, index = row.get("uniqueId"), row.get("rowIndex")
            if uid is None or index is None:
                raise WfsCollectionError("WFS_MISSING_LINE_ID")
            key = (str(uid), str(index))
            if key in seen:
                raise WfsCollectionError("WFS_DUPLICATE_LINE")
            seen.add(key)

        collected.extend(rows)
        if len(collected) == expected_total:
            return WfsCollectionResult(tuple(collected), expected_total, page + 1)
        if len(rows) != page_size:
            raise WfsCollectionError("WFS_INCOMPLETE_PAGE")
        if interval_seconds:
            sleep(interval_seconds)

    raise WfsCollectionError("WFS_MAX_PAGES")
