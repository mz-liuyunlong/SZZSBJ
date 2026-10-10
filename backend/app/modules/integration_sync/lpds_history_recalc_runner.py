"""Controlled, database-only LPDS historical recalculation.

The runner supports canonical rebuilds and preserved-input LPDS-only projections. It is
dry-run by default at the CLI boundary and never dispatches a sync task or calls an
external API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from time import monotonic
from typing import Any, Final, Literal, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Table, delete, func, insert, select, text, update
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment
from app.modules.data_pages.models import DailySalesItemDayMart, OrderProfitSkuDayMart
from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DAILY_SALES_V2_VERSION,
    _low_price_delivery_surcharge,
)
from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DataPagesRealSyncRunner as CanonicalLpdsMartRunner,
)
from app.modules.integration_sync.models import IntegrationSyncRun

EXPECTED_ALEMBIC_REVISION: Final = "20261010_0033_add_wfs_low_price_surcharge"
LEGACY_CALC_VERSION: Final = "real-data-2.0+business-rules-1+purchase-day-refund-v2+sem+rp+rnc"
EXPECTED_CALC_VERSION: Final = "real-data-2.0+business-rules-1+refund-v3-lpds"
BACKUP_SCHEMA_VERSION: Final = 1
COMMIT_CONFIRM_TOKEN: Final = "CONFIRM_LPDS_HISTORY_RECALC"
RESTORE_CONFIRM_TOKEN: Final = "CONFIRM_LPDS_HISTORY_RESTORE"
DATA_PAGES_INTERFACE_KEYS: Final = frozenset(
    {
        "walmartListingList",
        "saleStatPageList",
        "walmartReturnOrderList",
        "walmartAdItemSpList",
    }
)
LA_TZ: Final = ZoneInfo("America/Los_Angeles")

RunMode = Literal["dry-run", "commit"]
RecalculationMode = Literal["canonical", "lpds-only"]
DaySelection = Literal["eligible", "skip-current", "empty"]
ManifestStatus = Literal["succeeded", "failed", "skipped"]

MANIFEST_FIELDS: Final = frozenset(
    {
        "business_date",
        "mode",
        "recalculation_mode",
        "status",
        "error_code",
        "stage",
        "elapsed_seconds",
        "daily_rows",
        "order_profit_rows",
        "comparable_profit_groups",
        "mixed_null_profit_groups",
        "comparable_profit_delta_daily",
        "comparable_profit_delta_order",
        "mixed_null_explained_gap_change",
        "unexplained_profit_gap_change",
        "external_api",
        "sync",
    }
)
MANIFEST_STAGES: Final = frozenset(
    {
        "selection",
        "transaction_setup",
        "transaction_configuration",
        "database_contract",
        "concurrency_gate",
        "eligibility",
        "snapshot",
        "backup",
        "recalculation",
        "validation",
        "commit",
        "rollback",
        "post_transaction_verification",
        "complete",
    }
)
CONTINUABLE_DAY_ERROR_CODES: Final = frozenset(
    {
        "LPDS_BUSINESS_KEYS_CHANGED",
        "LPDS_DAILY_CALC_VERSION_INVALID",
        "LPDS_DATE_CHANGED",
        "LPDS_DUPLICATE_BUSINESS_KEY",
        "LPDS_FORMULA_MISMATCH",
        "LPDS_NON_LPDS_FIELDS_CHANGED",
        "LPDS_ONLY_PROFIT_RATIO_INPUT_INVALID",
        "LPDS_ONLY_PROJECTION_MISMATCH",
        "LPDS_ONLY_ROW_ID_MISSING",
        "LPDS_ONLY_ROW_UPDATE_MISMATCH",
        "LPDS_ORDER_CALC_VERSION_INVALID",
        "LPDS_PROFIT_GAP_INVARIANT_FAILED",
        "LPDS_ROW_COUNT_CHANGED",
        "LPDS_SURCHARGE_NULL",
        "LPDS_SURCHARGE_ROLLUP_MISMATCH",
        "LPDS_TARGET_NO_LONGER_ELIGIBLE",
        "LPDS_VERSION_PROFILE_INCOMPLETE",
        "LPDS_VERSION_PROFILE_MIXED_OR_UNKNOWN",
    }
)

MONEY_QUANTUM: Final = Decimal("0.0001")
RATIO_QUANTUM: Final = Decimal("0.000001")

DAILY_LPDS_ONLY_COLUMNS: Final = frozenset(
    {
        "wfs_low_price_surcharge_amount",
        "wfs_fee_total_amount",
        "gross_profit_amount",
        "gross_margin",
        "roi",
        "calc_version",
    }
)
ORDER_LPDS_ONLY_COLUMNS: Final = frozenset(
    {
        "wfs_low_price_surcharge_amount",
        "wfs_fee_total_amount",
        "gross_profit_amount",
        "gross_margin",
        "roi",
        "calc_version",
    }
)

DAILY_TABLE: Final[Table] = cast(Table, DailySalesItemDayMart.__table__)
ORDER_TABLE: Final[Table] = cast(Table, OrderProfitSkuDayMart.__table__)
TABLES: Final[tuple[Table, Table]] = (DAILY_TABLE, ORDER_TABLE)
TABLE_BY_NAME: Final[dict[str, Table]] = {table.name: table for table in TABLES}


class LpdsHistoryRecalcError(RuntimeError):
    """Safe runner failure containing only a stable error code."""

    def __init__(
        self,
        code: str,
        *,
        stage: str | None = None,
        rolled_back: bool | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.rolled_back = rolled_back


class SessionFactory(Protocol):
    def __call__(self) -> Session: ...


@dataclass(frozen=True, slots=True)
class TableSnapshot:
    table_name: str
    row_count: int
    business_key_hash: str
    content_hash: str
    calc_versions: tuple[tuple[str, int], ...]
    surcharge_sum: Decimal
    profit_sum: Decimal
    wfs_sum: Decimal
    rows: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ScopeDigest:
    row_count: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class DaySnapshot:
    business_date: date
    daily: TableSnapshot
    order_profit: TableSnapshot


@dataclass(frozen=True, slots=True)
class ProfitGapSummary:
    comparable_profit_groups: int
    mixed_null_profit_groups: int
    comparable_profit_delta_daily: Decimal
    comparable_profit_delta_order: Decimal
    mixed_null_explained_gap_change: Decimal
    unexplained_profit_gap_change: Decimal


@dataclass(frozen=True, slots=True)
class DayRunResult:
    business_date: date
    mode: RunMode
    before: DaySnapshot
    after: DaySnapshot
    backup_filename: str | None
    recalculation_mode: RecalculationMode = "canonical"

    def safe_lines(self) -> tuple[str, ...]:
        surcharge_delta = self.after.daily.surcharge_sum - self.before.daily.surcharge_sum
        daily_profit_delta = self.after.daily.profit_sum - self.before.daily.profit_sum
        order_profit_delta = (
            self.after.order_profit.profit_sum - self.before.order_profit.profit_sum
        )
        pre_profit_gap = self.before.order_profit.profit_sum - self.before.daily.profit_sum
        post_profit_gap = self.after.order_profit.profit_sum - self.after.daily.profit_sum
        profit_gap = _profit_gap_summary(
            self.before,
            self.after,
            require_lpds_explanation=self.recalculation_mode == "lpds-only",
            validate=False,
        )
        return (
            (
                "LPDS_DAY_COMPLETE "
                f"date={self.business_date.isoformat()} mode={self.mode} "
                f"recalculation_mode={self.recalculation_mode} "
                f"daily_rows={self.after.daily.row_count} "
                f"order_profit_rows={self.after.order_profit.row_count}"
            ),
            (
                "LPDS_DAY_SUMMARY "
                f"surcharge_before={self.before.daily.surcharge_sum} "
                f"surcharge_after={self.after.daily.surcharge_sum} "
                f"surcharge_delta={surcharge_delta} "
                f"profit_before={self.before.daily.profit_sum} "
                f"profit_after={self.after.daily.profit_sum} "
                f"profit_delta={daily_profit_delta}"
            ),
            (
                "LPDS_DAY_ORDER_PROFIT_SUMMARY "
                f"surcharge_before={self.before.order_profit.surcharge_sum} "
                f"surcharge_after={self.after.order_profit.surcharge_sum} "
                f"profit_before={self.before.order_profit.profit_sum} "
                f"profit_after={self.after.order_profit.profit_sum} "
                f"profit_delta={order_profit_delta} "
                f"wfs_before={self.before.order_profit.wfs_sum} "
                f"wfs_after={self.after.order_profit.wfs_sum}"
            ),
            (
                "LPDS_DAY_PROFIT_GAP_SUMMARY "
                f"daily_profit_delta={daily_profit_delta} "
                f"order_profit_delta={order_profit_delta} "
                f"pre_profit_gap={pre_profit_gap} "
                f"post_profit_gap={post_profit_gap} "
                f"comparable_profit_groups={profit_gap.comparable_profit_groups} "
                f"mixed_null_profit_groups={profit_gap.mixed_null_profit_groups} "
                "comparable_profit_delta_daily="
                f"{profit_gap.comparable_profit_delta_daily} "
                "comparable_profit_delta_order="
                f"{profit_gap.comparable_profit_delta_order} "
                "mixed_null_explained_gap_change="
                f"{profit_gap.mixed_null_explained_gap_change} "
                "unexplained_profit_gap_change="
                f"{profit_gap.unexplained_profit_gap_change}"
            ),
            (
                "LPDS_DAY_HASHES "
                f"daily_key_before={self.before.daily.business_key_hash} "
                f"daily_key_after={self.after.daily.business_key_hash} "
                f"daily_content_before={self.before.daily.content_hash} "
                f"daily_content_after={self.after.daily.content_hash} "
                f"order_key_before={self.before.order_profit.business_key_hash} "
                f"order_key_after={self.after.order_profit.business_key_hash} "
                f"order_content_before={self.before.order_profit.content_hash} "
                f"order_content_after={self.after.order_profit.content_hash}"
            ),
            (
                "LPDS_DAY_VERSIONS "
                f"daily_before={self.before.daily.calc_versions} "
                f"daily_after={self.after.daily.calc_versions} "
                f"order_before={self.before.order_profit.calc_versions} "
                f"order_after={self.after.order_profit.calc_versions}"
            ),
            f"LPDS_DAY_BACKUP file={self.backup_filename or 'NOT_CREATED'}",
        )


@dataclass(frozen=True, slots=True)
class DayManifestEntry:
    business_date: date
    mode: RunMode
    recalculation_mode: RecalculationMode
    status: ManifestStatus
    error_code: str | None
    stage: str
    elapsed_seconds: float
    daily_rows: int
    order_profit_rows: int
    comparable_profit_groups: int
    mixed_null_profit_groups: int
    comparable_profit_delta_daily: Decimal
    comparable_profit_delta_order: Decimal
    mixed_null_explained_gap_change: Decimal
    unexplained_profit_gap_change: Decimal

    @classmethod
    def succeeded(cls, result: DayRunResult, elapsed_seconds: float) -> DayManifestEntry:
        summary = _profit_gap_summary(
            result.before,
            result.after,
            require_lpds_explanation=result.recalculation_mode == "lpds-only",
            validate=False,
        )
        return cls(
            business_date=result.business_date,
            mode=result.mode,
            recalculation_mode=result.recalculation_mode,
            status="succeeded",
            error_code=None,
            stage="complete",
            elapsed_seconds=elapsed_seconds,
            daily_rows=result.after.daily.row_count,
            order_profit_rows=result.after.order_profit.row_count,
            comparable_profit_groups=summary.comparable_profit_groups,
            mixed_null_profit_groups=summary.mixed_null_profit_groups,
            comparable_profit_delta_daily=summary.comparable_profit_delta_daily,
            comparable_profit_delta_order=summary.comparable_profit_delta_order,
            mixed_null_explained_gap_change=summary.mixed_null_explained_gap_change,
            unexplained_profit_gap_change=summary.unexplained_profit_gap_change,
        )

    @classmethod
    def empty(
        cls,
        *,
        business_date: date,
        mode: RunMode,
        recalculation_mode: RecalculationMode,
        status: ManifestStatus,
        error_code: str,
        stage: str,
        elapsed_seconds: float,
        daily_rows: int = 0,
        order_profit_rows: int = 0,
    ) -> DayManifestEntry:
        return cls(
            business_date=business_date,
            mode=mode,
            recalculation_mode=recalculation_mode,
            status=status,
            error_code=error_code,
            stage=stage,
            elapsed_seconds=elapsed_seconds,
            daily_rows=daily_rows,
            order_profit_rows=order_profit_rows,
            comparable_profit_groups=0,
            mixed_null_profit_groups=0,
            comparable_profit_delta_daily=Decimal("0"),
            comparable_profit_delta_order=Decimal("0"),
            mixed_null_explained_gap_change=Decimal("0"),
            unexplained_profit_gap_change=Decimal("0"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "business_date": self.business_date.isoformat(),
            "mode": self.mode,
            "recalculation_mode": self.recalculation_mode,
            "status": self.status,
            "error_code": self.error_code,
            "stage": self.stage,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "daily_rows": self.daily_rows,
            "order_profit_rows": self.order_profit_rows,
            "comparable_profit_groups": self.comparable_profit_groups,
            "mixed_null_profit_groups": self.mixed_null_profit_groups,
            "comparable_profit_delta_daily": str(self.comparable_profit_delta_daily),
            "comparable_profit_delta_order": str(self.comparable_profit_delta_order),
            "mixed_null_explained_gap_change": str(self.mixed_null_explained_gap_change),
            "unexplained_profit_gap_change": str(self.unexplained_profit_gap_change),
            "external_api": "NOT_CALLED",
            "sync": "NOT_TRIGGERED",
        }

    def safe_line(self) -> str:
        return (
            "LPDS_DAY_MANIFEST "
            f"date={self.business_date.isoformat()} mode={self.mode} "
            f"recalculation_mode={self.recalculation_mode} status={self.status} "
            f"error_code={self.error_code or 'NONE'} stage={self.stage} "
            f"elapsed_seconds={self.elapsed_seconds:.3f}"
        )


@dataclass(frozen=True, slots=True)
class LpdsHistoryRunResult:
    mode: RunMode
    completed: tuple[DayRunResult, ...]
    skipped_current_dates: tuple[date, ...]
    skipped_empty_dates: tuple[date, ...]
    recalculation_mode: RecalculationMode = "canonical"
    manifest_entries: tuple[DayManifestEntry, ...] = ()
    failure_limit_reached: bool = False

    @property
    def failed(self) -> tuple[DayManifestEntry, ...]:
        return tuple(entry for entry in self.manifest_entries if entry.status == "failed")

    def safe_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        for result in self.completed:
            lines.extend(result.safe_lines())
        lines.extend(entry.safe_line() for entry in self.manifest_entries)
        lines.append(
            "LPDS_HISTORY_COMPLETE "
            f"mode={self.mode} recalculation_mode={self.recalculation_mode} "
            f"completed_days={len(self.completed)} "
            f"skipped_current_days={len(self.skipped_current_dates)} "
            f"skipped_empty_days={len(self.skipped_empty_dates)} "
            f"failed_days={len(self.failed)} "
            f"failure_limit_reached={str(self.failure_limit_reached).lower()} "
            "external_api=NOT_CALLED sync=NOT_TRIGGERED"
        )
        return tuple(lines)


@dataclass(frozen=True, slots=True)
class BackupDocument:
    metadata: dict[str, Any]
    tables: dict[str, tuple[dict[str, Any], ...]]
    payload_sha256: str


def resolve_bounded_dates(
    *,
    exact_date: date | None,
    start_date: date | None,
    end_date: date | None,
    limit_days: int,
) -> tuple[date, ...]:
    if not 1 <= limit_days <= 366:
        raise LpdsHistoryRecalcError("LPDS_LIMIT_DAYS_INVALID")
    if exact_date is not None:
        if start_date is not None or end_date is not None:
            raise LpdsHistoryRecalcError("LPDS_DATE_SCOPE_AMBIGUOUS")
        return (exact_date,)
    if start_date is None or end_date is None:
        raise LpdsHistoryRecalcError("LPDS_DATE_SCOPE_REQUIRED")
    if end_date < start_date:
        raise LpdsHistoryRecalcError("LPDS_DATE_SCOPE_INVALID")
    count = (end_date - start_date).days + 1
    if count > limit_days:
        raise LpdsHistoryRecalcError("LPDS_DATE_SCOPE_EXCEEDS_LIMIT")
    return tuple(start_date + timedelta(days=offset) for offset in range(count))


def prepare_manifest_output(path: Path) -> None:
    if path.is_symlink():
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_PERMISSIONS_INVALID")
    if path.exists():
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_ALREADY_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except OSError:
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_WRITE_FAILED") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_manifest_entry(path: Path, entry: DayManifestEntry) -> None:
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_WRITE_FAILED") from None
    try:
        if os.fstat(descriptor).st_mode & 0o777 != 0o600:
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_PERMISSIONS_INVALID")
        line = json.dumps(
            entry.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(f"{line}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except LpdsHistoryRecalcError:
        raise
    except OSError:
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_WRITE_FAILED") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_success_manifest(
    path: Path,
    *,
    recalculation_mode: RecalculationMode,
    limit_days: int,
) -> tuple[date, ...]:
    if not 1 <= limit_days <= 366:
        raise LpdsHistoryRecalcError("LPDS_LIMIT_DAYS_INVALID")
    if path.is_symlink() or not path.is_file():
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_PERMISSIONS_INVALID")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        if os.fstat(descriptor).st_mode & 0o777 != 0o600:
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_PERMISSIONS_INVALID")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = None
            lines = handle.read().splitlines()
    except LpdsHistoryRecalcError:
        raise
    except OSError:
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    succeeded: list[date] = []
    seen: set[date] = set()
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID") from None
        if not isinstance(payload, dict) or set(payload) != MANIFEST_FIELDS:
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID")
        if payload.get("external_api") != "NOT_CALLED" or payload.get("sync") != "NOT_TRIGGERED":
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_SAFETY_INVALID")
        try:
            business_date = date.fromisoformat(str(payload["business_date"]))
        except (TypeError, ValueError):
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID") from None
        if business_date in seen:
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_DUPLICATE_DATE")
        seen.add(business_date)
        if (
            payload.get("mode") != "dry-run"
            or payload.get("recalculation_mode") != recalculation_mode
            or payload.get("status") not in ("succeeded", "failed", "skipped")
            or payload.get("stage") not in MANIFEST_STAGES
        ):
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID")
        if payload["status"] != "succeeded":
            error_code = payload.get("error_code")
            if not isinstance(error_code, str) or not error_code.startswith("LPDS_"):
                raise LpdsHistoryRecalcError("LPDS_MANIFEST_INVALID")
            continue
        if payload.get("error_code") is not None or payload.get("stage") != "complete":
            raise LpdsHistoryRecalcError("LPDS_MANIFEST_SUCCESS_INVALID")
        succeeded.append(business_date)

    if not succeeded:
        raise LpdsHistoryRecalcError("LPDS_MANIFEST_NO_SUCCEEDED_DATES")
    if len(succeeded) > limit_days:
        raise LpdsHistoryRecalcError("LPDS_DATE_SCOPE_EXCEEDS_LIMIT")
    return tuple(succeeded)


def classify_version_profiles(
    daily_versions: Mapping[str, int],
    order_versions: Mapping[str, int],
) -> DaySelection:
    if not daily_versions and not order_versions:
        return "empty"
    if not daily_versions or not order_versions:
        raise LpdsHistoryRecalcError("LPDS_VERSION_PROFILE_INCOMPLETE")
    daily = frozenset(daily_versions)
    order = frozenset(order_versions)
    if daily == {EXPECTED_CALC_VERSION} and order == {EXPECTED_CALC_VERSION}:
        return "skip-current"
    if daily == {LEGACY_CALC_VERSION} and order == {LEGACY_CALC_VERSION}:
        return "eligible"
    raise LpdsHistoryRecalcError("LPDS_VERSION_PROFILE_MIXED_OR_UNKNOWN")


def validate_lpds_formula(rows: Iterable[Mapping[str, Any]]) -> None:
    for row in rows:
        surcharge = row.get("wfs_low_price_surcharge_amount")
        if surcharge is None:
            raise LpdsHistoryRecalcError("LPDS_SURCHARGE_NULL")
        sales = _decimal(row.get("sales_amount"))
        quantity = _decimal(row.get("sales_qty"))
        expected = _low_price_delivery_surcharge(sales, quantity)
        if _decimal(surcharge) != expected:
            raise LpdsHistoryRecalcError("LPDS_FORMULA_MISMATCH")


class LpdsHistoryRepository:
    """Narrow SQL boundary for the controlled runner."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def configure_transaction(self) -> None:
        self.session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        self.session.execute(text("SET LOCAL statement_timeout = '90s'"))
        self.session.execute(text("SET LOCAL idle_in_transaction_session_timeout = '120s'"))

    def lock_controlled_tables(self) -> None:
        self.session.execute(
            text(
                "LOCK TABLE mart_daily_sales_item_day, mart_order_profit_sku_day, "
                "gov_integration_sync_runs IN SHARE ROW EXCLUSIVE MODE"
            )
        )

    def assert_database_contract(self, app_env: AppEnvironment) -> None:
        if DAILY_SALES_V2_VERSION != EXPECTED_CALC_VERSION:
            raise LpdsHistoryRecalcError("LPDS_CODE_VERSION_MISMATCH")
        columns = set(
            self.session.execute(
                text(
                    "select table_name,column_name from information_schema.columns "
                    "where table_schema=any(current_schemas(false)) and "
                    "((table_name='mart_daily_sales_item_day' and "
                    "column_name='wfs_low_price_surcharge_amount') or "
                    "(table_name='mart_order_profit_sku_day' and "
                    "column_name='wfs_low_price_surcharge_amount'))"
                )
            ).all()
        )
        expected_columns = {
            ("mart_daily_sales_item_day", "wfs_low_price_surcharge_amount"),
            ("mart_order_profit_sku_day", "wfs_low_price_surcharge_amount"),
        }
        if columns != expected_columns:
            raise LpdsHistoryRecalcError("LPDS_DATABASE_COLUMNS_MISSING")
        if app_env is AppEnvironment.PRODUCTION:
            revision = self.session.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
            if revision != EXPECTED_ALEMBIC_REVISION:
                raise LpdsHistoryRecalcError("LPDS_ALEMBIC_REVISION_MISMATCH")

    def assert_no_active_data_pages_sync(self, source_account_ref: str, day: date) -> None:
        active = self.session.execute(
            select(IntegrationSyncRun.window_start, IntegrationSyncRun.window_end).where(
                IntegrationSyncRun.source_account_ref == source_account_ref,
                IntegrationSyncRun.interface_key.in_(DATA_PAGES_INTERFACE_KEYS),
                IntegrationSyncRun.status.in_(("queued", "running")),
            )
        ).all()
        for window_start, window_end in active:
            if window_start is None or window_end is None:
                raise LpdsHistoryRecalcError("LPDS_ACTIVE_DATA_PAGES_SYNC")
            start_day = _as_la_date(window_start)
            end_day = _as_la_date(window_end)
            if start_day <= day <= end_day:
                raise LpdsHistoryRecalcError("LPDS_ACTIVE_DATA_PAGES_SYNC")

    def version_profiles(
        self,
        source_account_ref: str,
        day: date,
    ) -> tuple[dict[str, int], dict[str, int]]:
        return (
            self._version_profile(DAILY_TABLE, source_account_ref, day),
            self._version_profile(ORDER_TABLE, source_account_ref, day),
        )

    def snapshot(self, source_account_ref: str, day: date) -> DaySnapshot:
        return DaySnapshot(
            business_date=day,
            daily=self._table_snapshot(DAILY_TABLE, source_account_ref, day),
            order_profit=self._table_snapshot(ORDER_TABLE, source_account_ref, day),
        )

    def non_target_digest(self, source_account_ref: str, day: date) -> dict[str, ScopeDigest]:
        result: dict[str, ScopeDigest] = {}
        for table in TABLES:
            order_columns = _business_key_columns(table.name)
            order_sql = ",".join(order_columns)
            row = (
                self.session.execute(
                    text(
                        "select count(*)::bigint row_count,"
                        "coalesce(md5(string_agg(md5(row_to_json(scoped)::text),'' "
                        f"order by {order_sql})),md5('')) content_hash "
                        f"from (select * from {table.name} where source_account_ref=:account "
                        "and business_date_la<>:day) scoped"
                    ),
                    {"account": source_account_ref, "day": day},
                )
                .mappings()
                .one()
            )
            result[table.name] = ScopeDigest(
                row_count=int(row["row_count"]),
                content_hash=str(row["content_hash"]),
            )
        return result

    def restore_snapshot(self, source_account_ref: str, snapshot: DaySnapshot) -> None:
        for table, table_snapshot in (
            (DAILY_TABLE, snapshot.daily),
            (ORDER_TABLE, snapshot.order_profit),
        ):
            self.session.execute(
                delete(table).where(
                    table.c.source_account_ref == source_account_ref,
                    table.c.business_date_la == snapshot.business_date,
                )
            )
            if table_snapshot.rows:
                self.session.execute(insert(table), list(table_snapshot.rows))

    def apply_lpds_only(self, before: DaySnapshot) -> None:
        """Apply only the LPDS projection while preserving every historical input."""
        projected = _project_lpds_only_snapshot(before)
        self._apply_projected_rows(
            DAILY_TABLE,
            projected.daily.rows,
            DAILY_LPDS_ONLY_COLUMNS,
        )
        self._apply_projected_rows(
            ORDER_TABLE,
            projected.order_profit.rows,
            ORDER_LPDS_ONLY_COLUMNS,
        )

    def _apply_projected_rows(
        self,
        table: Table,
        rows: Sequence[Mapping[str, Any]],
        allowed_columns: frozenset[str],
    ) -> None:
        for row in rows:
            row_id = row.get("id")
            if row_id is None:
                raise LpdsHistoryRecalcError("LPDS_ONLY_ROW_ID_MISSING")
            values = {column: row.get(column) for column in allowed_columns}
            result = self.session.execute(
                update(table)
                .where(table.c.id == row_id)
                .values(**values, updated_at=table.c.updated_at)
            )
            if getattr(result, "rowcount", None) != 1:
                raise LpdsHistoryRecalcError("LPDS_ONLY_ROW_UPDATE_MISMATCH")

    def _version_profile(
        self,
        table: Table,
        source_account_ref: str,
        day: date,
    ) -> dict[str, int]:
        rows = self.session.execute(
            select(table.c.calc_version, func.count())
            .where(
                table.c.source_account_ref == source_account_ref,
                table.c.business_date_la == day,
            )
            .group_by(table.c.calc_version)
        ).all()
        return {str(version): int(count) for version, count in rows}

    def _table_snapshot(
        self,
        table: Table,
        source_account_ref: str,
        day: date,
    ) -> TableSnapshot:
        keys = _business_key_columns(table.name)
        rows = tuple(
            dict(row)
            for row in self.session.execute(
                select(table)
                .where(
                    table.c.source_account_ref == source_account_ref,
                    table.c.business_date_la == day,
                )
                .order_by(*(table.c[column] for column in keys))
            ).mappings()
        )
        versions = Counter(str(row["calc_version"]) for row in rows)
        return TableSnapshot(
            table_name=table.name,
            row_count=len(rows),
            business_key_hash=_rows_hash(rows, include_columns=keys),
            content_hash=_rows_hash(rows),
            calc_versions=tuple(sorted(versions.items())),
            surcharge_sum=_sum_decimal(rows, "wfs_low_price_surcharge_amount"),
            profit_sum=_sum_decimal(rows, "gross_profit_amount"),
            wfs_sum=_sum_decimal(rows, "wfs_fee_total_amount"),
            rows=rows,
        )


class LpdsHistoryRecalcRunner:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        app_env: AppEnvironment,
        repository_factory: Callable[[Session], LpdsHistoryRepository] = LpdsHistoryRepository,
        canonical_runner_factory: Callable[[Session, str, date], Any] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.app_env = app_env
        self.repository_factory = repository_factory
        self.canonical_runner_factory = canonical_runner_factory or _canonical_runner

    def run(
        self,
        *,
        source_account_ref: str,
        exact_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit_days: int = 1,
        commit: bool = False,
        backup_dir: Path | None = None,
        allow_production: bool = False,
        confirm_token: str | None = None,
        restore_from: Path | None = None,
        recalculation_mode: RecalculationMode = "canonical",
        continue_on_error: bool = False,
        manifest_jsonl: Path | None = None,
        only_success_manifest: Path | None = None,
        max_failures: int = 50,
    ) -> LpdsHistoryRunResult:
        account = _validate_account(source_account_ref)
        if recalculation_mode not in ("canonical", "lpds-only"):
            raise LpdsHistoryRecalcError("LPDS_RECALCULATION_MODE_INVALID")
        if max_failures < 1:
            raise LpdsHistoryRecalcError("LPDS_MAX_FAILURES_INVALID")
        mode: RunMode = "commit" if commit else "dry-run"
        self._validate_authorization(
            mode=mode,
            allow_production=allow_production,
            confirm_token=confirm_token,
            restore=restore_from is not None,
            backup_dir=backup_dir,
        )
        if restore_from is not None:
            if continue_on_error or manifest_jsonl is not None or only_success_manifest is not None:
                raise LpdsHistoryRecalcError("LPDS_RESTORE_BATCH_OPTIONS_FORBIDDEN")
            if recalculation_mode != "canonical":
                raise LpdsHistoryRecalcError("LPDS_RESTORE_MODE_FORBIDDEN")
            if any(value is not None for value in (exact_date, start_date, end_date)):
                raise LpdsHistoryRecalcError("LPDS_RESTORE_DATE_SCOPE_FORBIDDEN")
            backup = read_backup(restore_from)
            snapshot = _snapshot_from_backup(backup, account)
            result = self._restore_day(
                account,
                snapshot,
                mode=mode,
                backup_dir=backup_dir,
            )
            return LpdsHistoryRunResult(mode, (result,), (), (), recalculation_mode)

        if continue_on_error and manifest_jsonl is None:
            raise LpdsHistoryRecalcError("LPDS_CONTINUE_REQUIRES_MANIFEST")
        if commit and only_success_manifest is None:
            raise LpdsHistoryRecalcError("LPDS_COMMIT_SUCCESS_MANIFEST_REQUIRED")
        if not commit and only_success_manifest is not None:
            raise LpdsHistoryRecalcError("LPDS_DRY_RUN_SUCCESS_MANIFEST_FORBIDDEN")
        if manifest_jsonl is not None and only_success_manifest is not None:
            if manifest_jsonl.resolve() == only_success_manifest.resolve():
                raise LpdsHistoryRecalcError("LPDS_MANIFEST_PATH_CONFLICT")
        if only_success_manifest is not None:
            if any(value is not None for value in (exact_date, start_date, end_date)):
                raise LpdsHistoryRecalcError("LPDS_MANIFEST_DATE_SCOPE_AMBIGUOUS")
            days = read_success_manifest(
                only_success_manifest,
                recalculation_mode=recalculation_mode,
                limit_days=limit_days,
            )
        else:
            days = resolve_bounded_dates(
                exact_date=exact_date,
                start_date=start_date,
                end_date=end_date,
                limit_days=limit_days,
            )
        if manifest_jsonl is not None:
            prepare_manifest_output(manifest_jsonl)

        completed: list[DayRunResult] = []
        skipped_current: list[date] = []
        skipped_empty: list[date] = []
        manifest_entries: list[DayManifestEntry] = []
        failures = 0
        failure_limit_reached = False
        for day in days:
            started_at = monotonic()
            try:
                daily, order = self._version_profiles(account, day)
                selection = classify_version_profiles(daily, order)
                if selection == "skip-current":
                    skipped_current.append(day)
                    entry = DayManifestEntry.empty(
                        business_date=day,
                        mode=mode,
                        recalculation_mode=recalculation_mode,
                        status="skipped",
                        error_code="LPDS_ALREADY_CURRENT",
                        stage="selection",
                        elapsed_seconds=monotonic() - started_at,
                        daily_rows=sum(daily.values()),
                        order_profit_rows=sum(order.values()),
                    )
                elif selection == "empty":
                    skipped_empty.append(day)
                    entry = DayManifestEntry.empty(
                        business_date=day,
                        mode=mode,
                        recalculation_mode=recalculation_mode,
                        status="skipped",
                        error_code="LPDS_EMPTY_DATE",
                        stage="selection",
                        elapsed_seconds=monotonic() - started_at,
                    )
                else:
                    result = self._recalculate_day(
                        account,
                        day,
                        mode=mode,
                        backup_dir=backup_dir,
                        recalculation_mode=recalculation_mode,
                    )
                    completed.append(result)
                    entry = DayManifestEntry.succeeded(result, monotonic() - started_at)
            except LpdsHistoryRecalcError as error:
                entry = DayManifestEntry.empty(
                    business_date=day,
                    mode=mode,
                    recalculation_mode=recalculation_mode,
                    status="failed",
                    error_code=error.code,
                    stage=error.stage or "selection",
                    elapsed_seconds=monotonic() - started_at,
                )
                manifest_entries.append(entry)
                if manifest_jsonl is not None:
                    write_manifest_entry(manifest_jsonl, entry)
                if (
                    not continue_on_error
                    or error.code not in CONTINUABLE_DAY_ERROR_CODES
                    or error.rolled_back is False
                ):
                    raise
                failures += 1
                if failures >= max_failures:
                    failure_limit_reached = True
                    break
                continue

            manifest_entries.append(entry)
            if manifest_jsonl is not None:
                write_manifest_entry(manifest_jsonl, entry)

        return LpdsHistoryRunResult(
            mode=mode,
            completed=tuple(completed),
            skipped_current_dates=tuple(skipped_current),
            skipped_empty_dates=tuple(skipped_empty),
            recalculation_mode=recalculation_mode,
            manifest_entries=tuple(manifest_entries),
            failure_limit_reached=failure_limit_reached,
        )

    def _version_profiles(
        self,
        account: str,
        day: date,
    ) -> tuple[dict[str, int], dict[str, int]]:
        with self.session_factory() as session:
            try:
                versions = self.repository_factory(session).version_profiles(account, day)
                session.rollback()
            except LpdsHistoryRecalcError as error:
                try:
                    session.rollback()
                except Exception:
                    raise LpdsHistoryRecalcError(
                        "LPDS_ROLLBACK_FAILED",
                        stage="selection",
                        rolled_back=False,
                    ) from None
                raise LpdsHistoryRecalcError(
                    error.code,
                    stage=error.stage or "selection",
                    rolled_back=True,
                ) from error
            except Exception:
                try:
                    session.rollback()
                except Exception:
                    raise LpdsHistoryRecalcError(
                        "LPDS_ROLLBACK_FAILED",
                        stage="selection",
                        rolled_back=False,
                    ) from None
                raise LpdsHistoryRecalcError(
                    "LPDS_UNEXPECTED_ERROR",
                    stage="selection",
                    rolled_back=True,
                ) from None
        return versions

    def _validate_authorization(
        self,
        *,
        mode: RunMode,
        allow_production: bool,
        confirm_token: str | None,
        restore: bool,
        backup_dir: Path | None,
    ) -> None:
        if self.app_env is AppEnvironment.PRODUCTION and not allow_production:
            raise LpdsHistoryRecalcError("LPDS_PRODUCTION_NOT_AUTHORIZED")
        if mode == "commit":
            expected = RESTORE_CONFIRM_TOKEN if restore else COMMIT_CONFIRM_TOKEN
            if confirm_token != expected:
                raise LpdsHistoryRecalcError("LPDS_COMMIT_CONFIRMATION_REQUIRED")
            if backup_dir is None:
                raise LpdsHistoryRecalcError("LPDS_BACKUP_DIR_REQUIRED")

    def _recalculate_day(
        self,
        account: str,
        day: date,
        *,
        mode: RunMode,
        backup_dir: Path | None,
        recalculation_mode: RecalculationMode = "canonical",
    ) -> DayRunResult:
        session = self.session_factory()
        transaction = session.begin()
        backup_filename: str | None = None
        stage = "transaction_setup"
        try:
            repository = self.repository_factory(session)
            stage = "transaction_configuration"
            repository.configure_transaction()
            repository.lock_controlled_tables()
            stage = "database_contract"
            repository.assert_database_contract(self.app_env)
            stage = "concurrency_gate"
            repository.assert_no_active_data_pages_sync(account, day)
            stage = "eligibility"
            daily_versions, order_versions = repository.version_profiles(account, day)
            if classify_version_profiles(daily_versions, order_versions) != "eligible":
                raise LpdsHistoryRecalcError("LPDS_TARGET_NO_LONGER_ELIGIBLE")
            stage = "snapshot"
            before = repository.snapshot(account, day)
            non_target_before = repository.non_target_digest(account, day)
            if mode == "commit":
                stage = "backup"
                backup_filename = write_backup(
                    cast(Path, backup_dir),
                    account,
                    before,
                    purpose="before-recalculation",
                ).name

            stage = "recalculation"
            if recalculation_mode == "canonical":
                canonical = self.canonical_runner_factory(session, account, day)
                if getattr(canonical, "client", None) is not None:
                    raise LpdsHistoryRecalcError("LPDS_EXTERNAL_CLIENT_FORBIDDEN")
                canonical._refresh_daily_sales_mart()
                canonical._refresh_order_profit_mart()
            else:
                repository.apply_lpds_only(before)

            stage = "validation"
            after = repository.snapshot(account, day)
            non_target_after = repository.non_target_digest(account, day)
            _validate_recalculation(
                before,
                after,
                non_target_before,
                non_target_after,
                recalculation_mode=recalculation_mode,
            )
            stage = "commit" if mode == "commit" else "rollback"
            if mode == "commit":
                transaction.commit()
            else:
                transaction.rollback()
        except Exception as error:
            rolled_back = False
            try:
                if transaction.is_active:
                    transaction.rollback()
                    rolled_back = True
            except Exception:
                raise LpdsHistoryRecalcError(
                    "LPDS_ROLLBACK_FAILED",
                    stage=stage,
                    rolled_back=False,
                ) from None
            if isinstance(error, LpdsHistoryRecalcError):
                raise LpdsHistoryRecalcError(
                    error.code,
                    stage=error.stage or stage,
                    rolled_back=rolled_back,
                ) from error
            raise LpdsHistoryRecalcError(
                "LPDS_UNEXPECTED_ERROR",
                stage=stage,
                rolled_back=rolled_back,
            ) from None
        finally:
            session.close()

        persisted = after if mode == "commit" else before
        try:
            self._verify_persisted_state(account, persisted, non_target_before)
        except Exception as error:
            code = (
                error.code
                if isinstance(error, LpdsHistoryRecalcError)
                else "LPDS_POST_TRANSACTION_VERIFICATION_FAILED"
            )
            raise LpdsHistoryRecalcError(
                code,
                stage="post_transaction_verification",
                rolled_back=mode == "dry-run",
            ) from error
        return DayRunResult(
            day,
            mode,
            before,
            after,
            backup_filename,
            recalculation_mode,
        )

    def _restore_day(
        self,
        account: str,
        backup_snapshot: DaySnapshot,
        *,
        mode: RunMode,
        backup_dir: Path | None,
    ) -> DayRunResult:
        day = backup_snapshot.business_date
        session = self.session_factory()
        transaction = session.begin()
        backup_filename: str | None = None
        try:
            repository = self.repository_factory(session)
            repository.configure_transaction()
            repository.lock_controlled_tables()
            repository.assert_database_contract(self.app_env)
            repository.assert_no_active_data_pages_sync(account, day)
            before = repository.snapshot(account, day)
            non_target_before = repository.non_target_digest(account, day)
            if mode == "commit":
                backup_filename = write_backup(
                    cast(Path, backup_dir),
                    account,
                    before,
                    purpose="before-restore",
                ).name
            repository.restore_snapshot(account, backup_snapshot)
            after = repository.snapshot(account, day)
            non_target_after = repository.non_target_digest(account, day)
            _validate_restoration(backup_snapshot, after, non_target_before, non_target_after)
            if mode == "commit":
                transaction.commit()
            else:
                transaction.rollback()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
        finally:
            session.close()

        persisted = backup_snapshot if mode == "commit" else before
        self._verify_persisted_state(account, persisted, non_target_before)
        return DayRunResult(day, mode, before, after, backup_filename)

    def _verify_persisted_state(
        self,
        account: str,
        expected: DaySnapshot,
        expected_non_target: Mapping[str, ScopeDigest],
    ) -> None:
        with self.session_factory() as session:
            repository = self.repository_factory(session)
            actual = repository.snapshot(account, expected.business_date)
            actual_non_target = repository.non_target_digest(account, expected.business_date)
            session.rollback()
        if not _same_snapshot(expected, actual) or expected_non_target != actual_non_target:
            raise LpdsHistoryRecalcError("LPDS_POST_TRANSACTION_VERIFICATION_FAILED")


def write_backup(
    backup_dir: Path,
    source_account_ref: str,
    snapshot: DaySnapshot,
    *,
    purpose: str,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    account_digest = hashlib.sha256(source_account_ref.encode()).hexdigest()[:12]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = backup_dir / (
        f"lpds-{purpose}-{snapshot.business_date.isoformat()}-{account_digest}-{timestamp}.json"
    )
    metadata: dict[str, Any] = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "purpose": purpose,
        "created_at": datetime.now(UTC),
        "source_account_ref": source_account_ref,
        "business_date": snapshot.business_date,
        "expected_calc_version": EXPECTED_CALC_VERSION,
    }
    tables = {
        snapshot.daily.table_name: snapshot.daily.rows,
        snapshot.order_profit.table_name: snapshot.order_profit.rows,
    }
    payload = {"metadata": _encode(metadata), "tables": _encode(tables)}
    payload_sha256 = _json_hash(payload)
    document = {**payload, "payload_sha256": payload_sha256}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if path.stat().st_mode & 0o077:
        path.unlink(missing_ok=True)
        raise LpdsHistoryRecalcError("LPDS_BACKUP_PERMISSIONS_INVALID")
    return path


def read_backup(path: Path) -> BackupDocument:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise LpdsHistoryRecalcError("LPDS_BACKUP_PERMISSIONS_INVALID")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_INVALID") from None
    if not isinstance(raw, dict):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_INVALID")
    payload = {"metadata": raw.get("metadata"), "tables": raw.get("tables")}
    digest = raw.get("payload_sha256")
    if not isinstance(digest, str) or not hmac.compare_digest(digest, _json_hash(payload)):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_HASH_MISMATCH")
    metadata = _decode(payload["metadata"])
    tables = _decode(payload["tables"])
    if not isinstance(metadata, dict) or not isinstance(tables, dict):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_INVALID")
    normalized_tables: dict[str, tuple[dict[str, Any], ...]] = {}
    if set(tables) != set(TABLE_BY_NAME):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_TABLES_INVALID")
    for table_name, rows in tables.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise LpdsHistoryRecalcError("LPDS_BACKUP_INVALID")
        normalized_tables[table_name] = tuple(cast(dict[str, Any], row) for row in rows)
    return BackupDocument(metadata, normalized_tables, digest)


def _snapshot_from_backup(backup: BackupDocument, source_account_ref: str) -> DaySnapshot:
    metadata = backup.metadata
    if metadata.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise LpdsHistoryRecalcError("LPDS_BACKUP_SCHEMA_UNSUPPORTED")
    if metadata.get("purpose") not in {"before-recalculation", "before-restore"}:
        raise LpdsHistoryRecalcError("LPDS_BACKUP_PURPOSE_INVALID")
    if metadata.get("expected_calc_version") != EXPECTED_CALC_VERSION:
        raise LpdsHistoryRecalcError("LPDS_BACKUP_VERSION_INVALID")
    if metadata.get("source_account_ref") != source_account_ref:
        raise LpdsHistoryRecalcError("LPDS_BACKUP_ACCOUNT_MISMATCH")
    business_date = metadata.get("business_date")
    if not isinstance(business_date, date) or isinstance(business_date, datetime):
        raise LpdsHistoryRecalcError("LPDS_BACKUP_DATE_INVALID")
    daily = _snapshot_from_rows(DAILY_TABLE.name, backup.tables[DAILY_TABLE.name])
    order = _snapshot_from_rows(ORDER_TABLE.name, backup.tables[ORDER_TABLE.name])
    for table_snapshot in (daily, order):
        expected_columns = set(TABLE_BY_NAME[table_snapshot.table_name].c.keys())
        for row in table_snapshot.rows:
            if set(row) != expected_columns:
                raise LpdsHistoryRecalcError("LPDS_BACKUP_COLUMNS_INVALID")
            if (
                row.get("source_account_ref") != source_account_ref
                or row.get("business_date_la") != business_date
            ):
                raise LpdsHistoryRecalcError("LPDS_BACKUP_SCOPE_INVALID")
    return DaySnapshot(business_date, daily, order)


def _snapshot_from_rows(table_name: str, rows: Sequence[Mapping[str, Any]]) -> TableSnapshot:
    normalized = tuple(dict(row) for row in rows)
    keys = _business_key_columns(table_name)
    versions = Counter(str(row["calc_version"]) for row in normalized)
    return TableSnapshot(
        table_name=table_name,
        row_count=len(normalized),
        business_key_hash=_rows_hash(normalized, include_columns=keys),
        content_hash=_rows_hash(normalized),
        calc_versions=tuple(sorted(versions.items())),
        surcharge_sum=_sum_decimal(normalized, "wfs_low_price_surcharge_amount"),
        profit_sum=_sum_decimal(normalized, "gross_profit_amount"),
        wfs_sum=_sum_decimal(normalized, "wfs_fee_total_amount"),
        rows=normalized,
    )


def _validate_recalculation(
    before: DaySnapshot,
    after: DaySnapshot,
    non_target_before: Mapping[str, ScopeDigest],
    non_target_after: Mapping[str, ScopeDigest],
    *,
    recalculation_mode: RecalculationMode = "canonical",
) -> None:
    if before.business_date != after.business_date:
        raise LpdsHistoryRecalcError("LPDS_DATE_CHANGED")
    if (
        before.daily.row_count != after.daily.row_count
        or before.order_profit.row_count != after.order_profit.row_count
    ):
        raise LpdsHistoryRecalcError("LPDS_ROW_COUNT_CHANGED")
    if (
        before.daily.business_key_hash != after.daily.business_key_hash
        or before.order_profit.business_key_hash != after.order_profit.business_key_hash
    ):
        raise LpdsHistoryRecalcError("LPDS_BUSINESS_KEYS_CHANGED")
    expected_versions = ((EXPECTED_CALC_VERSION, after.daily.row_count),)
    if after.daily.calc_versions != expected_versions:
        raise LpdsHistoryRecalcError("LPDS_DAILY_CALC_VERSION_INVALID")
    expected_order_versions = ((EXPECTED_CALC_VERSION, after.order_profit.row_count),)
    if after.order_profit.calc_versions != expected_order_versions:
        raise LpdsHistoryRecalcError("LPDS_ORDER_CALC_VERSION_INVALID")
    _assert_unique(after.daily.rows, _business_key_columns(DAILY_TABLE.name))
    _assert_unique(after.order_profit.rows, _business_key_columns(ORDER_TABLE.name))
    validate_lpds_formula(after.daily.rows)
    _assert_surcharge_rollup(after)
    _assert_profit_gap_invariant(
        before,
        after,
        require_lpds_explanation=recalculation_mode == "lpds-only",
    )
    if recalculation_mode == "lpds-only":
        _assert_lpds_only_projection(before, after)
    if non_target_before != non_target_after:
        raise LpdsHistoryRecalcError("LPDS_NON_TARGET_ROWS_CHANGED")


def _validate_restoration(
    backup: DaySnapshot,
    restored: DaySnapshot,
    non_target_before: Mapping[str, ScopeDigest],
    non_target_after: Mapping[str, ScopeDigest],
) -> None:
    if not _same_snapshot(backup, restored):
        raise LpdsHistoryRecalcError("LPDS_RESTORE_CONTENT_MISMATCH")
    if non_target_before != non_target_after:
        raise LpdsHistoryRecalcError("LPDS_NON_TARGET_ROWS_CHANGED")


def _assert_surcharge_rollup(snapshot: DaySnapshot) -> None:
    daily_by_sku: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in snapshot.daily.rows:
        key = str(row.get("local_sku") or row.get("item_id") or "")
        daily_by_sku[key] += _decimal(row.get("wfs_low_price_surcharge_amount"))
    order_by_sku = {
        str(row.get("local_sku") or ""): _decimal(row.get("wfs_low_price_surcharge_amount"))
        for row in snapshot.order_profit.rows
    }
    if dict(daily_by_sku) != order_by_sku:
        raise LpdsHistoryRecalcError("LPDS_SURCHARGE_ROLLUP_MISMATCH")


def _assert_profit_gap_invariant(
    before: DaySnapshot,
    after: DaySnapshot,
    *,
    require_lpds_explanation: bool,
) -> None:
    _profit_gap_summary(
        before,
        after,
        require_lpds_explanation=require_lpds_explanation,
        validate=True,
    )


def _profit_gap_summary(
    before: DaySnapshot,
    after: DaySnapshot,
    *,
    require_lpds_explanation: bool,
    validate: bool,
) -> ProfitGapSummary:
    daily_keys = _business_key_columns(DAILY_TABLE.name)
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
            tuple(row.get(column) for column in daily_keys): row for row in before_daily_rows
        }
        after_by_identity = {
            tuple(row.get(column) for column in daily_keys): row for row in after_daily_rows
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
        explained_gap_change = Decimal("0")
        if (
            not before_has_null
            or not before_order_null
            or not after_has_null
            or not after_order_null
            or not before_surcharge_matches
            or not after_surcharge_matches
        ):
            failures += 1
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
        raise LpdsHistoryRecalcError("LPDS_PROFIT_GAP_INVARIANT_FAILED")
    return summary


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


def _project_lpds_only_snapshot(before: DaySnapshot) -> DaySnapshot:
    daily_rows = tuple(_project_lpds_only_daily_row(row) for row in before.daily.rows)
    daily_by_sku: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        daily_by_sku[_daily_rollup_key(row)].append(row)
    order_rows = tuple(
        _project_lpds_only_order_row(row, daily_by_sku.get(str(row.get("local_sku")), []))
        for row in before.order_profit.rows
    )
    return DaySnapshot(
        before.business_date,
        _snapshot_from_rows(DAILY_TABLE.name, daily_rows),
        _snapshot_from_rows(ORDER_TABLE.name, order_rows),
    )


def _project_lpds_only_daily_row(row: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(row)
    old_surcharge = _decimal(row.get("wfs_low_price_surcharge_amount"))
    new_surcharge = _money(
        _low_price_delivery_surcharge(
            _decimal(row.get("sales_amount")),
            _decimal(row.get("sales_qty")),
        )
    )
    surcharge_delta = new_surcharge - old_surcharge
    projected["wfs_low_price_surcharge_amount"] = new_surcharge
    projected["wfs_fee_total_amount"] = _adjust_optional_money(
        row.get("wfs_fee_total_amount"),
        surcharge_delta,
    )
    _apply_profit_delta(projected, row, surcharge_delta)
    projected["calc_version"] = EXPECTED_CALC_VERSION
    return projected


def _project_lpds_only_order_row(
    row: Mapping[str, Any],
    daily_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    projected = dict(row)
    new_surcharge = _money(
        sum(
            (_decimal(daily.get("wfs_low_price_surcharge_amount")) for daily in daily_rows),
            Decimal("0"),
        )
    )
    surcharge_delta = new_surcharge - _decimal(row.get("wfs_low_price_surcharge_amount"))
    projected["wfs_low_price_surcharge_amount"] = new_surcharge
    projected["wfs_fee_total_amount"] = _adjust_optional_money(
        row.get("wfs_fee_total_amount"),
        surcharge_delta,
    )
    if row.get("gross_profit_amount") is None or any(
        daily.get("gross_profit_amount") is None for daily in daily_rows
    ):
        projected["gross_profit_amount"] = None
        projected["gross_margin"] = None
        projected["roi"] = None
    else:
        _apply_profit_delta(projected, row, surcharge_delta)
    projected["calc_version"] = EXPECTED_CALC_VERSION
    return projected


def _apply_profit_delta(
    projected: dict[str, Any],
    original: Mapping[str, Any],
    surcharge_delta: Decimal,
) -> None:
    if surcharge_delta == 0:
        return
    original_profit = original.get("gross_profit_amount")
    if original_profit is None:
        projected["gross_profit_amount"] = None
        projected["gross_margin"] = original.get("gross_margin")
        projected["roi"] = original.get("roi")
        return

    new_profit = _money(_decimal(original_profit) - surcharge_delta)
    projected["gross_profit_amount"] = new_profit
    projected["gross_margin"] = _adjust_optional_ratio(
        original.get("gross_margin"),
        new_profit,
        _decimal(original.get("sales_amount")),
    )
    roi_denominator = (
        _decimal(original.get("purchase_cost_total_usd"))
        + _decimal(original.get("first_leg_cost_total_usd"))
        if original.get("purchase_cost_total_usd") is not None
        and original.get("first_leg_cost_total_usd") is not None
        else None
    )
    projected["roi"] = _adjust_optional_ratio(
        original.get("roi"),
        new_profit,
        roi_denominator,
    )


def _adjust_optional_money(value: Any, delta: Decimal) -> Decimal | None:
    if value is None:
        return None
    if delta == 0:
        return _decimal(value)
    return _money(_decimal(value) + delta)


def _adjust_optional_ratio(
    original: Any,
    numerator: Decimal,
    denominator: Decimal | None,
) -> Decimal | None:
    if original is None:
        return None
    if denominator is None or denominator <= 0:
        raise LpdsHistoryRecalcError("LPDS_ONLY_PROFIT_RATIO_INPUT_INVALID")
    return (numerator / denominator).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _assert_lpds_only_projection(before: DaySnapshot, after: DaySnapshot) -> None:
    _assert_preserved_columns(
        before.daily.rows,
        after.daily.rows,
        DAILY_TABLE,
        DAILY_LPDS_ONLY_COLUMNS,
    )
    _assert_preserved_columns(
        before.order_profit.rows,
        after.order_profit.rows,
        ORDER_TABLE,
        ORDER_LPDS_ONLY_COLUMNS,
    )
    expected = _project_lpds_only_snapshot(before)
    if (
        expected.daily.content_hash != after.daily.content_hash
        or expected.order_profit.content_hash != after.order_profit.content_hash
    ):
        raise LpdsHistoryRecalcError("LPDS_ONLY_PROJECTION_MISMATCH")


def _assert_preserved_columns(
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    table: Table,
    allowed_columns: frozenset[str],
) -> None:
    frozen_columns = tuple(column.name for column in table.c if column.name not in allowed_columns)
    if _rows_hash(before, include_columns=frozen_columns) != _rows_hash(
        after,
        include_columns=frozen_columns,
    ):
        raise LpdsHistoryRecalcError("LPDS_NON_LPDS_FIELDS_CHANGED")


def _daily_rollup_key(row: Mapping[str, Any]) -> str:
    return str(row.get("local_sku") or row.get("item_id") or "")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _assert_unique(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        identity = tuple(row.get(key) for key in keys)
        if identity in seen:
            raise LpdsHistoryRecalcError("LPDS_DUPLICATE_BUSINESS_KEY")
        seen.add(identity)


def _same_snapshot(left: DaySnapshot, right: DaySnapshot) -> bool:
    return (
        left.business_date == right.business_date
        and left.daily.row_count == right.daily.row_count
        and left.daily.business_key_hash == right.daily.business_key_hash
        and left.daily.content_hash == right.daily.content_hash
        and left.order_profit.row_count == right.order_profit.row_count
        and left.order_profit.business_key_hash == right.order_profit.business_key_hash
        and left.order_profit.content_hash == right.order_profit.content_hash
    )


def _canonical_runner(session: Session, source_account_ref: str, day: date) -> Any:
    return CanonicalLpdsMartRunner(
        session=session,
        client=None,
        source_account_ref=source_account_ref,
        business_date=day,
        page_size=100,
        campaign_type="SP",
        max_advertisers=1,
    )


def _business_key_columns(table_name: str) -> tuple[str, ...]:
    if table_name == DAILY_TABLE.name:
        return ("business_date_la", "source_account_ref", "store_id", "item_id", "msku")
    if table_name == ORDER_TABLE.name:
        return ("business_date_la", "source_account_ref", "local_sku")
    raise LpdsHistoryRecalcError("LPDS_TABLE_NOT_ALLOWED")


def _rows_hash(
    rows: Iterable[Mapping[str, Any]],
    *,
    include_columns: Sequence[str] | None = None,
) -> str:
    normalized = []
    for row in rows:
        selected = (
            {column: row.get(column) for column in include_columns}
            if include_columns is not None
            else dict(row)
        )
        normalized.append(_encode(selected))
    return _json_hash(normalized)


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"__lpds_type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__lpds_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__lpds_type__": "date", "value": value.isoformat()}
    if isinstance(value, UUID):
        return {"__lpds_type__": "uuid", "value": str(value)}
    if isinstance(value, Mapping):
        return {
            "__lpds_type__": "mapping",
            "items": [[str(key), _encode(item)] for key, item in value.items()],
        }
    if isinstance(value, (list, tuple)):
        return {"__lpds_type__": "sequence", "items": [_encode(item) for item in value]}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        kind = value.get("__lpds_type__")
        if kind == "mapping" and set(value) == {"__lpds_type__", "items"}:
            items = value["items"]
            if not isinstance(items, list):
                raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")
            decoded: dict[str, Any] = {}
            for item in items:
                if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                    raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")
                decoded[item[0]] = _decode(item[1])
            return decoded
        if kind == "sequence" and set(value) == {"__lpds_type__", "items"}:
            items = value["items"]
            if not isinstance(items, list):
                raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")
            return [_decode(item) for item in items]
        if set(value) == {"__lpds_type__", "value"}:
            raw = value["value"]
            if kind == "decimal":
                return Decimal(raw)
            if kind == "datetime":
                return datetime.fromisoformat(raw)
            if kind == "date":
                return date.fromisoformat(raw)
            if kind == "uuid":
                return UUID(raw)
            raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")
        raise LpdsHistoryRecalcError("LPDS_BACKUP_VALUE_UNSUPPORTED")
    return value


def _sum_decimal(rows: Iterable[Mapping[str, Any]], column: str) -> Decimal:
    return sum((_decimal(row.get(column)) for row in rows), Decimal("0"))


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_account(value: str) -> str:
    if not value or value != value.strip() or len(value) > 128:
        raise LpdsHistoryRecalcError("LPDS_SOURCE_ACCOUNT_REF_INVALID")
    return value


def _as_la_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LA_TZ).date()
