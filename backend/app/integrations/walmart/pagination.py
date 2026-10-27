"""Bounded, all-or-nothing pagination for approved read-only Walmart operations.

No network, queue or database coupling is introduced. A configured WalmartClient
does the protected SCF dispatch; results are returned only if pagination ends
cleanly. This prevents publishing silently truncated pages.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.integrations.walmart.client import WalmartClient
from app.integrations.walmart.contracts import ContractError


class PaginationRejected(RuntimeError):
    """Stable error code; does not include raw Walmart payloads or parameters."""


@dataclass(frozen=True, slots=True)
class PageContract:
    operation: str
    items_path: tuple[str, ...]
    mode: Literal["offset", "cursor"]
    limit_field: str = "limit"
    offset_field: str = "offset"
    cursor_field: str = "nextCursor"
    next_cursor_path: tuple[str, ...] = ()
    total_path: tuple[str, ...] = ()


def _lookup(payload: Any, path: tuple[str, ...]) -> Any:
    current = payload
    for name in path:
        if not isinstance(current, Mapping) or name not in current:
            raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
        current = current[name]
    return current


def collect_read_pages(
    client: WalmartClient,
    *,
    store_code: str,
    contract: PageContract,
    params: Mapping[str, str | int | bool] | None = None,
    page_size: int = 50,
    max_pages: int = 50,
    max_items: int = 2500,
) -> tuple[dict[str, Any], ...]:
    """Return full bounded page set or fail, never return a partial result.

    The function does not retry transport errors: token refresh, throttling,
    concurrency and upstream rate limits remain the responsibility of the
    independently protected execution environment.
    """
    if not 1 <= page_size <= 100 or not 1 <= max_pages <= 100:
        raise PaginationRejected("WALMART_PAGE_LIMIT_INVALID")
    if not 1 <= max_items <= 10000:
        raise PaginationRejected("WALMART_PAGE_LIMIT_INVALID")
    if not contract.items_path or contract.mode == "cursor" and not contract.next_cursor_path:
        raise PaginationRejected("WALMART_PAGE_CONTRACT_INVALID")
    if client.registry.get(contract.operation).method != "GET":
        raise PaginationRejected("WALMART_PAGE_WRITE_FORBIDDEN")
    base = dict(params or {})
    forbidden = {contract.limit_field, contract.offset_field, contract.cursor_field}
    if forbidden.intersection(base):
        raise PaginationRejected("WALMART_PAGE_PARAMETER_CONFLICT")
    collected: list[dict[str, Any]] = []
    offset = 0
    cursor: str | None = None
    seen_cursors: set[str] = set()
    for _ in range(max_pages):
        query = dict(base)
        query[contract.limit_field] = page_size
        if contract.mode == "offset":
            query[contract.offset_field] = offset
        elif cursor is not None:
            query[contract.cursor_field] = cursor
        try:
            result = client.call(
                store_code,
                contract.operation,
                params=query,
                allow_writes=False,
            )
        except ContractError:
            raise
        except Exception:
            raise PaginationRejected("WALMART_PAGE_REQUEST_FAILED") from None
        if not 200 <= result.status_code < 300:
            raise PaginationRejected("WALMART_PAGE_REQUEST_FAILED")
        items = _lookup(result.data, contract.items_path)
        if not isinstance(items, list) or len(items) > page_size:
            raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
        if any(not isinstance(item, dict) for item in items):
            raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
        if len(collected) + len(items) > max_items:
            raise PaginationRejected("WALMART_PAGE_ITEM_LIMIT_EXCEEDED")
        collected.extend(items)
        total = _lookup(result.data, contract.total_path) if contract.total_path else None
        if total is not None and (type(total) is not int or total < 0):
            raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
        if contract.mode == "offset":
            offset += len(items)
            if total is not None:
                if len(collected) > total:
                    raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
                if len(collected) == total:
                    return tuple(collected)
                if not items:
                    raise PaginationRejected("WALMART_PAGE_INCOMPLETE")
            elif len(items) < page_size:
                return tuple(collected)
        else:
            next_cursor = _lookup(result.data, contract.next_cursor_path)
            if next_cursor in (None, ""):
                if total is not None and len(collected) != total:
                    raise PaginationRejected("WALMART_PAGE_INCOMPLETE")
                return tuple(collected)
            if not isinstance(next_cursor, str) or len(next_cursor) > 2048:
                raise PaginationRejected("WALMART_PAGE_SHAPE_CHANGED")
            if next_cursor in seen_cursors or not items:
                raise PaginationRejected("WALMART_PAGE_CURSOR_LOOP")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
    raise PaginationRejected("WALMART_PAGE_LIMIT_REACHED")
