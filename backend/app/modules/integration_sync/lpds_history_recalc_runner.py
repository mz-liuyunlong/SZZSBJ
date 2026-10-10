"""Controlled, database-only LPDS historical recalculation.

The runner deliberately calls the canonical DATA-PAGES MART refresh methods with no
provider client.  It is dry-run by default at the CLI boundary and never dispatches a
sync task or calls an external API.
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
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Table, delete, func, insert, select, text
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
DaySelection = Literal["eligible", "skip-current", "empty"]

DAILY_TABLE: Final[Table] = cast(Table, DailySalesItemDayMart.__table__)
ORDER_TABLE: Final[Table] = cast(Table, OrderProfitSkuDayMart.__table__)
TABLES: Final[tuple[Table, Table]] = (DAILY_TABLE, ORDER_TABLE)
TABLE_BY_NAME: Final[dict[str, Table]] = {table.name: table for table in TABLES}


class LpdsHistoryRecalcError(RuntimeError):
    """Safe runner failure containing only a stable error code."""


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
class DayRunResult:
    business_date: date
    mode: RunMode
    before: DaySnapshot
    after: DaySnapshot
    backup_filename: str | None

    def safe_lines(self) -> tuple[str, ...]:
        surcharge_delta = self.after.daily.surcharge_sum - self.before.daily.surcharge_sum
        daily_profit_delta = self.after.daily.profit_sum - self.before.daily.profit_sum
        order_profit_delta = (
            self.after.order_profit.profit_sum - self.before.order_profit.profit_sum
        )
        pre_profit_gap = self.before.order_profit.profit_sum - self.before.daily.profit_sum
        post_profit_gap = self.after.order_profit.profit_sum - self.after.daily.profit_sum
        return (
            (
                "LPDS_DAY_COMPLETE "
                f"date={self.business_date.isoformat()} mode={self.mode} "
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
                f"post_profit_gap={post_profit_gap}"
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
class LpdsHistoryRunResult:
    mode: RunMode
    completed: tuple[DayRunResult, ...]
    skipped_current_dates: tuple[date, ...]
    skipped_empty_dates: tuple[date, ...]

    def safe_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        for result in self.completed:
            lines.extend(result.safe_lines())
        lines.append(
            "LPDS_HISTORY_COMPLETE "
            f"mode={self.mode} completed_days={len(self.completed)} "
            f"skipped_current_days={len(self.skipped_current_dates)} "
            f"skipped_empty_days={len(self.skipped_empty_dates)} "
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
    ) -> LpdsHistoryRunResult:
        account = _validate_account(source_account_ref)
        mode: RunMode = "commit" if commit else "dry-run"
        self._validate_authorization(
            mode=mode,
            allow_production=allow_production,
            confirm_token=confirm_token,
            restore=restore_from is not None,
            backup_dir=backup_dir,
        )
        if restore_from is not None:
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
            return LpdsHistoryRunResult(mode, (result,), (), ())

        days = resolve_bounded_dates(
            exact_date=exact_date,
            start_date=start_date,
            end_date=end_date,
            limit_days=limit_days,
        )
        eligible: list[date] = []
        skipped_current: list[date] = []
        skipped_empty: list[date] = []
        for day in days:
            with self.session_factory() as session:
                daily, order = self.repository_factory(session).version_profiles(account, day)
                selection = classify_version_profiles(daily, order)
                session.rollback()
            if selection == "eligible":
                eligible.append(day)
            elif selection == "skip-current":
                skipped_current.append(day)
            else:
                skipped_empty.append(day)

        completed: list[DayRunResult] = []
        for day in eligible:
            completed.append(
                self._recalculate_day(
                    account,
                    day,
                    mode=mode,
                    backup_dir=backup_dir,
                )
            )
        return LpdsHistoryRunResult(
            mode,
            tuple(completed),
            tuple(skipped_current),
            tuple(skipped_empty),
        )

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
    ) -> DayRunResult:
        session = self.session_factory()
        transaction = session.begin()
        backup_filename: str | None = None
        try:
            repository = self.repository_factory(session)
            repository.configure_transaction()
            repository.lock_controlled_tables()
            repository.assert_database_contract(self.app_env)
            repository.assert_no_active_data_pages_sync(account, day)
            daily_versions, order_versions = repository.version_profiles(account, day)
            if classify_version_profiles(daily_versions, order_versions) != "eligible":
                raise LpdsHistoryRecalcError("LPDS_TARGET_NO_LONGER_ELIGIBLE")
            before = repository.snapshot(account, day)
            non_target_before = repository.non_target_digest(account, day)
            if mode == "commit":
                backup_filename = write_backup(
                    cast(Path, backup_dir),
                    account,
                    before,
                    purpose="before-recalculation",
                ).name

            canonical = self.canonical_runner_factory(session, account, day)
            if getattr(canonical, "client", None) is not None:
                raise LpdsHistoryRecalcError("LPDS_EXTERNAL_CLIENT_FORBIDDEN")
            canonical._refresh_daily_sales_mart()
            canonical._refresh_order_profit_mart()

            after = repository.snapshot(account, day)
            non_target_after = repository.non_target_digest(account, day)
            _validate_recalculation(before, after, non_target_before, non_target_after)
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

        persisted = after if mode == "commit" else before
        self._verify_persisted_state(account, persisted, non_target_before)
        return DayRunResult(day, mode, before, after, backup_filename)

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
    _assert_profit_gap_invariant(before, after)
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


def _assert_profit_gap_invariant(before: DaySnapshot, after: DaySnapshot) -> None:
    daily_profit_delta = after.daily.profit_sum - before.daily.profit_sum
    order_profit_delta = after.order_profit.profit_sum - before.order_profit.profit_sum
    pre_profit_gap = before.order_profit.profit_sum - before.daily.profit_sum
    post_profit_gap = after.order_profit.profit_sum - after.daily.profit_sum
    if daily_profit_delta != order_profit_delta or pre_profit_gap != post_profit_gap:
        raise LpdsHistoryRecalcError("LPDS_PROFIT_GAP_INVARIANT_FAILED")


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
