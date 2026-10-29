"""Explicit bounded pagination through the approved SCF read facade.

Response list paths are owner-reviewed configuration, never inferred from an
unknown API response. Any shape error fails all-or-nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.api import ApiError
from app.integrations.walmart.scf_bridge import _contains_secret_key
from app.modules.walmart_scf.unified import ScfGateway, approved_read


def _path(data: Any, parts: tuple[str, ...]) -> Any:
    for name in parts:
        if not isinstance(data, Mapping) or name not in data:
            raise ApiError(code="WALMART_PAGE_SHAPE_UNVERIFIED", status_code=502)
        data = data[name]
    return data


def collect_offset_pages(
    *,
    source_account_ref: str,
    store_id: str,
    verified_store_scope: frozenset[str],
    verified_source_account_scope: frozenset[str],
    operation: str,
    items_path: tuple[str, ...],
    params: Mapping[str, Any] | None = None,
    page_size: int = 50,
    max_pages: int = 5,
    max_items: int = 250,
    gateway: ScfGateway | None = None,
) -> tuple[dict[str, Any], ...]:
    if (
        not items_path
        or any(not part or not part.isidentifier() for part in items_path)
        or type(page_size) is not int
        or type(max_pages) is not int
        or type(max_items) is not int
        or not 1 <= page_size <= 100
        or not 1 <= max_pages <= 20
        or not 1 <= max_items <= 2000
    ):
        raise ApiError(code="WALMART_PAGE_CONFIG_INVALID", status_code=422)
    base = dict(params or {})
    if "limit" in base or "offset" in base:
        raise ApiError(code="WALMART_PAGE_PARAMETER_CONFLICT", status_code=422)
    rows: list[dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        query = {**base, "limit": page_size, "offset": offset}
        result = approved_read(
            source_account_ref=source_account_ref,
            store_id=store_id,
            verified_store_scope=verified_store_scope,
            verified_source_account_scope=verified_source_account_scope,
            operation=operation,
            params=query,
            gateway=gateway,
        )
        page = _path(result.data, items_path)
        if (
            not isinstance(page, list)
            or len(page) > page_size
            or any(not isinstance(row, dict) or _contains_secret_key(row) for row in page)
        ):
            raise ApiError(code="WALMART_PAGE_SHAPE_UNVERIFIED", status_code=502)
        if len(rows) + len(page) > max_items:
            raise ApiError(code="WALMART_PAGE_LIMIT_REACHED", status_code=422)
        rows.extend(page)
        if len(page) < page_size:
            return tuple(rows)
        offset += len(page)
    raise ApiError(code="WALMART_PAGE_LIMIT_REACHED", status_code=422)


def collect_cursor_pages(
    *,
    source_account_ref: str,
    store_id: str,
    verified_store_scope: frozenset[str],
    verified_source_account_scope: frozenset[str],
    operation: str,
    items_path: tuple[str, ...],
    cursor_path: tuple[str, ...],
    cursor_field: str = "nextCursor",
    params: Mapping[str, Any] | None = None,
    page_size: int = 50,
    max_pages: int = 5,
    max_items: int = 250,
    gateway: ScfGateway | None = None,
) -> tuple[dict[str, Any], ...]:
    """Bounded cursor pagination; no repeated cursor or partial results."""
    if (
        not items_path
        or not cursor_path
        or any(not part.isidentifier() for part in (*items_path, *cursor_path))
        or type(page_size) is not int
        or type(max_pages) is not int
        or type(max_items) is not int
        or not 1 <= page_size <= 100
        or not 1 <= max_pages <= 20
        or not 1 <= max_items <= 2000
        or cursor_field not in {"cursor", "nextCursor"}
    ):
        raise ApiError(code="WALMART_PAGE_CONFIG_INVALID", status_code=422)
    base = dict(params or {})
    if "limit" in base or cursor_field in base:
        raise ApiError(code="WALMART_PAGE_PARAMETER_CONFLICT", status_code=422)
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(max_pages):
        query: dict[str, Any] = {**base, "limit": page_size}
        if cursor is not None:
            query[cursor_field] = cursor
        result = approved_read(
            source_account_ref=source_account_ref,
            store_id=store_id,
            verified_store_scope=verified_store_scope,
            verified_source_account_scope=verified_source_account_scope,
            operation=operation,
            params=query,
            gateway=gateway,
        )
        page = _path(result.data, items_path)
        next_cursor = _path(result.data, cursor_path)
        if (
            not isinstance(page, list)
            or len(page) > page_size
            or any(not isinstance(row, dict) or _contains_secret_key(row) for row in page)
        ):
            raise ApiError(code="WALMART_PAGE_SHAPE_UNVERIFIED", status_code=502)
        if len(rows) + len(page) > max_items:
            raise ApiError(code="WALMART_PAGE_LIMIT_REACHED", status_code=422)
        rows.extend(page)
        if next_cursor in (None, ""):
            return tuple(rows)
        if (
            not isinstance(next_cursor, str)
            or len(next_cursor) > 2048
            or next_cursor in seen
            or not page
        ):
            raise ApiError(code="WALMART_PAGE_CURSOR_INVALID", status_code=502)
        seen.add(next_cursor)
        cursor = next_cursor
    raise ApiError(code="WALMART_PAGE_LIMIT_REACHED", status_code=422)
