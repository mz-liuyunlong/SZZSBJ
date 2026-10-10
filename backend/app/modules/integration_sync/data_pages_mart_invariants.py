from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart, OrderProfitSkuDayMart

DAILY_BUSINESS_KEYS = (
    "business_date_la",
    "source_account_ref",
    "store_id",
    "item_id",
    "msku",
)
ORDER_BUSINESS_KEYS = ("business_date_la", "source_account_ref", "local_sku")
VOLATILE_COLUMNS = frozenset({"id", "calculated_at", "created_at", "updated_at"})
DAILY_TABLE = cast(Table, DailySalesItemDayMart.__table__)
ORDER_TABLE = cast(Table, OrderProfitSkuDayMart.__table__)


class ProfitTableSnapshot(Protocol):
    @property
    def profit_sum(self) -> Decimal: ...

    @property
    def rows(self) -> Sequence[Mapping[str, Any]]: ...


class ProfitDaySnapshot(Protocol):
    @property
    def daily(self) -> ProfitTableSnapshot: ...

    @property
    def order_profit(self) -> ProfitTableSnapshot: ...


class DataPagesMartInvariantError(RuntimeError):
    """Safe automatic MART failure with no row-level details."""

    def __init__(self, code: str, *, business_date: date | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.business_date = business_date


@dataclass(frozen=True, slots=True)
class ProfitGapSummary:
    comparable_profit_groups: int
    mixed_null_profit_groups: int
    comparable_profit_delta_daily: Decimal
    comparable_profit_delta_order: Decimal
    mixed_null_explained_gap_change: Decimal
    unexplained_profit_gap_change: Decimal


@dataclass(frozen=True, slots=True)
class AutomaticMartTableSnapshot:
    row_count: int
    business_key_hash: str
    stable_content_hash: str
    calc_versions: tuple[tuple[str, int], ...]
    surcharge_sum: Decimal
    profit_sum: Decimal
    rows: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class AutomaticMartDaySnapshot:
    business_date: date
    daily: AutomaticMartTableSnapshot
    order_profit: AutomaticMartTableSnapshot


def snapshot_automatic_marts(
    session: Session,
    source_account_ref: str,
    business_date: date,
) -> AutomaticMartDaySnapshot:
    daily_rows = tuple(
        dict(row)
        for row in session.execute(
            select(DAILY_TABLE)
            .where(
                DAILY_TABLE.c.source_account_ref == source_account_ref,
                DAILY_TABLE.c.business_date_la == business_date,
            )
            .order_by(
                DAILY_TABLE.c.store_id,
                DAILY_TABLE.c.item_id,
                DAILY_TABLE.c.msku,
            )
        ).mappings()
    )
    order_rows = tuple(
        dict(row)
        for row in session.execute(
            select(ORDER_TABLE)
            .where(
                ORDER_TABLE.c.source_account_ref == source_account_ref,
                ORDER_TABLE.c.business_date_la == business_date,
            )
            .order_by(ORDER_TABLE.c.local_sku)
        ).mappings()
    )
    return AutomaticMartDaySnapshot(
        business_date=business_date,
        daily=_automatic_table_snapshot(daily_rows, DAILY_BUSINESS_KEYS),
        order_profit=_automatic_table_snapshot(order_rows, ORDER_BUSINESS_KEYS),
    )


def validate_automatic_mart_replay(
    first: AutomaticMartDaySnapshot,
    replay: AutomaticMartDaySnapshot,
    *,
    expected_calc_version: str,
    surcharge_for: Callable[[Decimal, Decimal], Decimal],
) -> ProfitGapSummary:
    day = replay.business_date
    if first.business_date != day:
        raise DataPagesMartInvariantError("DATA_PAGES_MART_DATE_CHANGED", business_date=day)
    if (
        first.daily.row_count != replay.daily.row_count
        or first.order_profit.row_count != replay.order_profit.row_count
    ):
        raise DataPagesMartInvariantError(
            "DATA_PAGES_MART_ROW_COUNT_CHANGED",
            business_date=day,
        )
    if (
        first.daily.business_key_hash != replay.daily.business_key_hash
        or first.order_profit.business_key_hash != replay.order_profit.business_key_hash
    ):
        raise DataPagesMartInvariantError(
            "DATA_PAGES_MART_BUSINESS_KEYS_CHANGED",
            business_date=day,
        )
    expected_daily_versions = (
        ((expected_calc_version, replay.daily.row_count),) if replay.daily.row_count else ()
    )
    expected_order_versions = (
        ((expected_calc_version, replay.order_profit.row_count),)
        if replay.order_profit.row_count
        else ()
    )
    if (
        replay.daily.calc_versions != expected_daily_versions
        or replay.order_profit.calc_versions != expected_order_versions
    ):
        raise DataPagesMartInvariantError(
            "DATA_PAGES_MART_CALC_VERSION_INVALID",
            business_date=day,
        )
    for row in replay.daily.rows:
        expected = surcharge_for(
            _decimal(row.get("sales_amount")),
            _decimal(row.get("sales_qty")),
        )
        if _decimal(row.get("wfs_low_price_surcharge_amount")) != expected:
            raise DataPagesMartInvariantError(
                "DATA_PAGES_MART_LPDS_FORMULA_MISMATCH",
                business_date=day,
            )
    try:
        assert_surcharge_rollup(replay)
        summary = profit_gap_summary(
            first,
            replay,
            require_lpds_explanation=False,
            validate=True,
        )
    except DataPagesMartInvariantError as error:
        raise DataPagesMartInvariantError(error.code, business_date=day) from error
    if (
        first.daily.stable_content_hash != replay.daily.stable_content_hash
        or first.order_profit.stable_content_hash != replay.order_profit.stable_content_hash
    ):
        raise DataPagesMartInvariantError(
            "DATA_PAGES_MART_IDEMPOTENCY_FAILED",
            business_date=day,
        )
    return summary


def assert_surcharge_rollup(snapshot: ProfitDaySnapshot) -> None:
    daily_by_sku: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in snapshot.daily.rows:
        daily_by_sku[_daily_rollup_key(row)] += _decimal(row.get("wfs_low_price_surcharge_amount"))
    order_by_sku = {
        str(row.get("local_sku") or ""): _decimal(row.get("wfs_low_price_surcharge_amount"))
        for row in snapshot.order_profit.rows
    }
    if dict(daily_by_sku) != order_by_sku:
        raise DataPagesMartInvariantError("DATA_PAGES_MART_SURCHARGE_ROLLUP_MISMATCH")


def profit_gap_summary(
    before: ProfitDaySnapshot,
    after: ProfitDaySnapshot,
    *,
    require_lpds_explanation: bool,
    validate: bool,
) -> ProfitGapSummary:
    before_daily = _rows_by_rollup(before.daily.rows, daily=True)
    after_daily = _rows_by_rollup(after.daily.rows, daily=True)
    before_order = _rows_by_rollup(before.order_profit.rows, daily=False)
    after_order = _rows_by_rollup(after.order_profit.rows, daily=False)
    all_key_sets = (
        set(before_daily),
        set(after_daily),
        set(before_order),
        set(after_order),
    )
    failures = 0 if all(keys == all_key_sets[0] for keys in all_key_sets[1:]) else 1
    comparable_groups = 0
    mixed_null_groups = 0
    comparable_daily_delta = Decimal("0")
    comparable_order_delta = Decimal("0")
    mixed_null_explained_gap_change = Decimal("0")

    for key in set.union(*all_key_sets):
        before_daily_rows = before_daily.get(key, ())
        after_daily_rows = after_daily.get(key, ())
        before_order_rows = before_order.get(key, ())
        after_order_rows = after_order.get(key, ())
        if (
            not before_daily_rows
            or not after_daily_rows
            or len(before_order_rows) != 1
            or len(after_order_rows) != 1
        ):
            failures += 1
            continue

        before_by_identity = {
            tuple(row.get(column) for column in DAILY_BUSINESS_KEYS): row
            for row in before_daily_rows
        }
        after_by_identity = {
            tuple(row.get(column) for column in DAILY_BUSINESS_KEYS): row
            for row in after_daily_rows
        }
        if (
            len(before_by_identity) != len(before_daily_rows)
            or len(after_by_identity) != len(after_daily_rows)
            or set(before_by_identity) != set(after_by_identity)
        ):
            failures += 1
            continue

        before_order_row = before_order_rows[0]
        after_order_row = after_order_rows[0]
        before_has_null = any(row.get("gross_profit_amount") is None for row in before_daily_rows)
        after_has_null = any(row.get("gross_profit_amount") is None for row in after_daily_rows)
        before_order_null = before_order_row.get("gross_profit_amount") is None
        after_order_null = after_order_row.get("gross_profit_amount") is None
        daily_delta = _sum_decimal(after_daily_rows, "gross_profit_amount") - _sum_decimal(
            before_daily_rows,
            "gross_profit_amount",
        )
        order_delta = _decimal(after_order_row.get("gross_profit_amount")) - _decimal(
            before_order_row.get("gross_profit_amount")
        )
        daily_surcharge_delta = _sum_decimal(
            after_daily_rows,
            "wfs_low_price_surcharge_amount",
        ) - _sum_decimal(before_daily_rows, "wfs_low_price_surcharge_amount")
        before_surcharge_matches = _sum_decimal(
            before_daily_rows,
            "wfs_low_price_surcharge_amount",
        ) == _decimal(before_order_row.get("wfs_low_price_surcharge_amount"))
        after_surcharge_matches = _sum_decimal(
            after_daily_rows,
            "wfs_low_price_surcharge_amount",
        ) == _decimal(after_order_row.get("wfs_low_price_surcharge_amount"))

        if not before_has_null and not before_order_null:
            comparable_groups += 1
            comparable_daily_delta += daily_delta
            comparable_order_delta += order_delta
            group_pre_gap = _decimal(before_order_row.get("gross_profit_amount")) - _sum_decimal(
                before_daily_rows,
                "gross_profit_amount",
            )
            group_post_gap = _decimal(after_order_row.get("gross_profit_amount")) - _sum_decimal(
                after_daily_rows,
                "gross_profit_amount",
            )
            if (
                after_has_null
                or after_order_null
                or daily_delta != order_delta
                or group_pre_gap != group_post_gap
                or not before_surcharge_matches
                or not after_surcharge_matches
                or (require_lpds_explanation and daily_delta != -daily_surcharge_delta)
            ):
                failures += 1
            continue

        mixed_null_groups += 1
        if (
            not before_has_null
            or not before_order_null
            or not after_has_null
            or not after_order_null
            or not before_surcharge_matches
            or not after_surcharge_matches
        ):
            failures += 1

        if require_lpds_explanation:
            explained_gap_change = Decimal("0")
            for identity, before_row in before_by_identity.items():
                after_row = after_by_identity[identity]
                before_profit = before_row.get("gross_profit_amount")
                after_profit = after_row.get("gross_profit_amount")
                if (before_profit is None) != (after_profit is None):
                    failures += 1
                    continue
                if before_profit is None:
                    continue
                row_surcharge_delta = _decimal(
                    after_row.get("wfs_low_price_surcharge_amount")
                ) - _decimal(before_row.get("wfs_low_price_surcharge_amount"))
                if _decimal(after_profit) - _decimal(before_profit) != -row_surcharge_delta:
                    failures += 1
                explained_gap_change += row_surcharge_delta
            if order_delta != 0 or daily_delta != -explained_gap_change:
                failures += 1
        else:
            null_pattern_changed = any(
                (before_by_identity[identity].get("gross_profit_amount") is None)
                != (after_by_identity[identity].get("gross_profit_amount") is None)
                for identity in before_by_identity
            )
            if null_pattern_changed or order_delta != 0:
                failures += 1
            explained_gap_change = -daily_delta
        mixed_null_explained_gap_change += explained_gap_change

    global_gap_change = (
        after.order_profit.profit_sum
        - after.daily.profit_sum
        - before.order_profit.profit_sum
        + before.daily.profit_sum
    )
    unexplained_profit_gap_change = global_gap_change - mixed_null_explained_gap_change
    summary = ProfitGapSummary(
        comparable_profit_groups=comparable_groups,
        mixed_null_profit_groups=mixed_null_groups,
        comparable_profit_delta_daily=comparable_daily_delta,
        comparable_profit_delta_order=comparable_order_delta,
        mixed_null_explained_gap_change=mixed_null_explained_gap_change,
        unexplained_profit_gap_change=unexplained_profit_gap_change,
    )
    if validate and (
        failures
        or comparable_daily_delta != comparable_order_delta
        or unexplained_profit_gap_change != 0
    ):
        raise DataPagesMartInvariantError("DATA_PAGES_MART_PROFIT_INVARIANT_FAILED")
    return summary


def _automatic_table_snapshot(
    rows: Sequence[Mapping[str, Any]],
    business_keys: Sequence[str],
) -> AutomaticMartTableSnapshot:
    normalized = tuple(dict(row) for row in rows)
    versions = Counter(str(row.get("calc_version")) for row in normalized)
    stable_columns = (
        tuple(column for column in normalized[0] if column not in VOLATILE_COLUMNS)
        if normalized
        else ()
    )
    return AutomaticMartTableSnapshot(
        row_count=len(normalized),
        business_key_hash=_rows_hash(normalized, business_keys),
        stable_content_hash=_rows_hash(normalized, stable_columns),
        calc_versions=tuple(sorted(versions.items())),
        surcharge_sum=_sum_decimal(normalized, "wfs_low_price_surcharge_amount"),
        profit_sum=_sum_decimal(normalized, "gross_profit_amount"),
        rows=normalized,
    )


def _rows_by_rollup(
    rows: Sequence[Mapping[str, Any]],
    *,
    daily: bool,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _daily_rollup_key(row) if daily else str(row.get("local_sku") or "")
        grouped[key].append(row)
    return {key: tuple(group) for key, group in grouped.items()}


def _daily_rollup_key(row: Mapping[str, Any]) -> str:
    return str(row.get("local_sku") or row.get("item_id") or "")


def _rows_hash(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> str:
    normalized = [{column: _encode(row.get(column)) for column in columns} for row in rows]
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _sum_decimal(rows: Iterable[Mapping[str, Any]], column: str) -> Decimal:
    return sum((_decimal(row.get(column)) for row in rows), Decimal("0"))


def _decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, UUID):
        return {"__type__": "uuid", "value": str(value)}
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value
