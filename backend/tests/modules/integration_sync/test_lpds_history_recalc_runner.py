from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import AppEnvironment, Settings, SettingsError, get_test_database_url
from app.modules.integration_sync.lpds_history_recalc_runner import (
    COMMIT_CONFIRM_TOKEN,
    DAILY_TABLE,
    EXPECTED_CALC_VERSION,
    LEGACY_CALC_VERSION,
    ORDER_TABLE,
    DayRunResult,
    DaySnapshot,
    LpdsHistoryRecalcError,
    LpdsHistoryRecalcRunner,
    LpdsHistoryRepository,
    ScopeDigest,
    _canonical_runner,
    _project_lpds_only_snapshot,
    _snapshot_from_backup,
    _snapshot_from_rows,
    _validate_recalculation,
    classify_version_profiles,
    read_backup,
    resolve_bounded_dates,
    validate_lpds_formula,
    write_backup,
)
from scripts.recalculate_lpds_history import parse_args

DAY = date(2026, 1, 15)
ACCOUNT = "synthetic-account"


def _daily_row(
    *,
    version: str,
    surcharge: Decimal,
    profit: Decimal | None = None,
    item_id: str = "synthetic-item",
) -> dict[str, Any]:
    values = {
        "business_date_la": DAY,
        "source_account_ref": ACCOUNT,
        "store_id": "synthetic-store",
        "item_id": item_id,
        "msku": "synthetic-msku",
        "local_sku": "synthetic-sku",
        "sales_qty": Decimal("1"),
        "sales_amount": Decimal("9"),
        "wfs_low_price_surcharge_amount": surcharge,
        "wfs_fee_total_amount": Decimal("5") + surcharge,
        "gross_profit_amount": profit if profit is not None else Decimal("4") - surcharge,
        "calc_version": version,
    }
    return {column.name: values.get(column.name) for column in DAILY_TABLE.c}


def _order_row(
    *,
    version: str,
    surcharge: Decimal,
    profit: Decimal | None = None,
) -> dict[str, Any]:
    values = {
        "business_date_la": DAY,
        "source_account_ref": ACCOUNT,
        "local_sku": "synthetic-sku",
        "wfs_low_price_surcharge_amount": surcharge,
        "wfs_fee_total_amount": Decimal("5") + surcharge,
        "gross_profit_amount": profit if profit is not None else Decimal("4") - surcharge,
        "calc_version": version,
    }
    return {column.name: values.get(column.name) for column in ORDER_TABLE.c}


def _snapshot(
    *,
    version: str,
    surcharge: Decimal,
    daily_profit: Decimal | None = None,
    order_profit: Decimal | None = None,
) -> DaySnapshot:
    return DaySnapshot(
        DAY,
        _snapshot_from_rows(
            DAILY_TABLE.name,
            (_daily_row(version=version, surcharge=surcharge, profit=daily_profit),),
        ),
        _snapshot_from_rows(
            ORDER_TABLE.name,
            (_order_row(version=version, surcharge=surcharge, profit=order_profit),),
        ),
    )


def _mixed_null_snapshot() -> DaySnapshot:
    partial = _daily_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=None,
        item_id="synthetic-partial-item",
    )
    partial.update(
        {
            "msku": "synthetic-partial-msku",
            "sales_amount": Decimal("10"),
            "gross_profit_amount": None,
            "wfs_fee_total_amount": None,
            "cost_status": "partial",
        }
    )
    complete = _daily_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=Decimal("9.6985"),
        item_id="synthetic-complete-item",
    )
    complete.update(
        {
            "msku": "synthetic-complete-msku",
            "sales_qty": Decimal("4"),
            "sales_amount": Decimal("36"),
            "cost_status": "complete",
        }
    )
    order = _order_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=None,
    )
    order.update(
        {
            "sales_amount": Decimal("46"),
            "gross_profit_amount": None,
            "gross_margin": None,
            "roi": None,
            "cost_status": "partial",
        }
    )
    return DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, (partial, complete)),
        _snapshot_from_rows(ORDER_TABLE.name, (order,)),
    )


class _Transaction:
    def __init__(self) -> None:
        self.is_active = True
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.is_active = False
        self.committed = True

    def rollback(self) -> None:
        self.is_active = False
        self.rolled_back = True


class _Session:
    def __init__(self) -> None:
        self.transaction = _Transaction()
        self.rollback_calls = 0
        self.closed = False

    def begin(self) -> _Transaction:
        return self.transaction

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class _Repository:
    def __init__(
        self,
        snapshots: list[DaySnapshot],
        *,
        versions: tuple[dict[str, int], dict[str, int]] | None = None,
    ) -> None:
        self.snapshots = iter(snapshots)
        self.versions = versions or (
            {LEGACY_CALC_VERSION: 1},
            {LEGACY_CALC_VERSION: 1},
        )
        self.non_target = {
            DAILY_TABLE.name: ScopeDigest(10, "daily-non-target"),
            ORDER_TABLE.name: ScopeDigest(8, "order-non-target"),
        }
        self.restore_calls: list[tuple[str, DaySnapshot]] = []
        self.lpds_only_calls: list[DaySnapshot] = []

    def configure_transaction(self) -> None:
        return None

    def lock_controlled_tables(self) -> None:
        return None

    def assert_database_contract(self, _: AppEnvironment) -> None:
        return None

    def assert_no_active_data_pages_sync(self, _: str, __: date) -> None:
        return None

    def version_profiles(self, _: str, __: date) -> tuple[dict[str, int], dict[str, int]]:
        return self.versions

    def snapshot(self, _: str, __: date) -> DaySnapshot:
        return next(self.snapshots)

    def non_target_digest(self, _: str, __: date) -> dict[str, ScopeDigest]:
        return self.non_target

    def restore_snapshot(self, account: str, snapshot: DaySnapshot) -> None:
        self.restore_calls.append((account, snapshot))

    def apply_lpds_only(self, before: DaySnapshot) -> None:
        self.lpds_only_calls.append(before)


def test_cli_defaults_to_dry_run() -> None:
    args = parse_args(["--source-account-ref", ACCOUNT, "--date", DAY.isoformat()])

    assert args.commit is False
    assert args.dry_run is False
    assert args.mode == "canonical"


def test_cli_accepts_lpds_only_mode() -> None:
    args = parse_args(
        [
            "--source-account-ref",
            ACCOUNT,
            "--date",
            DAY.isoformat(),
            "--mode",
            "lpds-only",
        ]
    )

    assert args.mode == "lpds-only"


def test_unbounded_or_oversized_date_scope_is_rejected() -> None:
    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_DATE_SCOPE_REQUIRED"):
        resolve_bounded_dates(
            exact_date=None,
            start_date=None,
            end_date=None,
            limit_days=1,
        )
    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_DATE_SCOPE_EXCEEDS_LIMIT"):
        resolve_bounded_dates(
            exact_date=None,
            start_date=DAY,
            end_date=date(2026, 9, 28),
            limit_days=2,
        )


def test_version_selection_only_accepts_uniform_legacy_days() -> None:
    assert (
        classify_version_profiles(
            {LEGACY_CALC_VERSION: 2},
            {LEGACY_CALC_VERSION: 1},
        )
        == "eligible"
    )
    assert (
        classify_version_profiles(
            {EXPECTED_CALC_VERSION: 2},
            {EXPECTED_CALC_VERSION: 1},
        )
        == "skip-current"
    )
    assert classify_version_profiles({}, {}) == "empty"

    with pytest.raises(
        LpdsHistoryRecalcError,
        match="LPDS_VERSION_PROFILE_MIXED_OR_UNKNOWN",
    ):
        classify_version_profiles(
            {LEGACY_CALC_VERSION: 1, EXPECTED_CALC_VERSION: 1},
            {LEGACY_CALC_VERSION: 1},
        )


def test_commit_requires_explicit_confirmation_and_backup_dir(tmp_path: Path) -> None:
    runner = LpdsHistoryRecalcRunner(lambda: _Session(), app_env=AppEnvironment.TEST)

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_COMMIT_CONFIRMATION_REQUIRED"):
        runner.run(
            source_account_ref=ACCOUNT,
            exact_date=DAY,
            commit=True,
            backup_dir=tmp_path,
        )
    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_BACKUP_DIR_REQUIRED"):
        runner.run(
            source_account_ref=ACCOUNT,
            exact_date=DAY,
            commit=True,
            confirm_token=COMMIT_CONFIRM_TOKEN,
        )


def test_production_even_dry_run_requires_allow_production() -> None:
    runner = LpdsHistoryRecalcRunner(lambda: _Session(), app_env=AppEnvironment.PRODUCTION)

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_PRODUCTION_NOT_AUTHORIZED"):
        runner.run(source_account_ref=ACCOUNT, exact_date=DAY)


def test_current_version_date_is_skipped_without_rebuild() -> None:
    session = _Session()
    repository = _Repository(
        [],
        versions=({EXPECTED_CALC_VERSION: 1}, {EXPECTED_CALC_VERSION: 1}),
    )
    canonical_factory = pytest.fail
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=canonical_factory,
    )

    result = runner.run(source_account_ref=ACCOUNT, exact_date=DAY)

    assert result.completed == ()
    assert result.skipped_current_dates == (DAY,)


def test_daily_refresh_precedes_order_profit_and_dry_run_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    after = _snapshot(version=EXPECTED_CALC_VERSION, surcharge=Decimal("1"))
    session = _Session()
    repository = _Repository([before, after])
    calls: list[str] = []
    canonical = SimpleNamespace(
        client=None,
        _refresh_daily_sales_mart=lambda: calls.append("daily"),
        _refresh_order_profit_mart=lambda: calls.append("order_profit"),
    )
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    result = runner._recalculate_day(ACCOUNT, DAY, mode="dry-run", backup_dir=None)

    assert calls == ["daily", "order_profit"]
    assert session.transaction.rolled_back is True
    assert session.transaction.committed is False
    assert result.after.daily.surcharge_sum - result.before.daily.surcharge_sum == Decimal("1")
    assert "synthetic-item" not in "\n".join(result.safe_lines())
    assert ACCOUNT not in "\n".join(result.safe_lines())


def test_lpds_only_mode_bypasses_canonical_rebuild_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    after = _project_lpds_only_snapshot(before)
    session = _Session()
    repository = _Repository([before, after])
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=pytest.fail,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    result = runner._recalculate_day(
        ACCOUNT,
        DAY,
        mode="dry-run",
        backup_dir=None,
        recalculation_mode="lpds-only",
    )

    assert repository.lpds_only_calls == [before]
    assert session.transaction.rolled_back is True
    assert result.recalculation_mode == "lpds-only"
    output = "\n".join(result.safe_lines())
    assert "recalculation_mode=lpds-only" in output
    assert "comparable_profit_groups=1" in output
    assert "mixed_null_profit_groups=0" in output
    assert "comparable_profit_delta_daily=-1.0000" in output
    assert "comparable_profit_delta_order=-1.0000" in output
    assert "mixed_null_explained_gap_change=0" in output
    assert "unexplained_profit_gap_change=0.0000" in output


def test_lpds_only_projection_changes_only_lpds_and_profit_fields() -> None:
    daily = _daily_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=Decimal("4"),
    )
    daily.update(
        {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "gross_margin": Decimal("0.444444"),
            "roi": Decimal("2.000000"),
            "purchase_cost_total_usd": Decimal("1"),
            "first_leg_cost_total_usd": Decimal("1"),
            "cost_status": "complete",
        }
    )
    order = _order_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=Decimal("4"),
    )
    order.update(
        {
            "id": UUID("00000000-0000-0000-0000-000000000002"),
            "sales_amount": Decimal("9"),
            "gross_margin": Decimal("0.444444"),
            "roi": Decimal("2.000000"),
            "purchase_cost_total_usd": Decimal("1"),
            "first_leg_cost_total_usd": Decimal("1"),
            "cost_status": "complete",
        }
    )
    before = DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, (daily,)),
        _snapshot_from_rows(ORDER_TABLE.name, (order,)),
    )

    after = _project_lpds_only_snapshot(before)

    projected_daily = after.daily.rows[0]
    projected_order = after.order_profit.rows[0]
    assert projected_daily["wfs_low_price_surcharge_amount"] == Decimal("1.0000")
    assert projected_daily["wfs_fee_total_amount"] == Decimal("6.0000")
    assert projected_daily["gross_profit_amount"] == Decimal("3.0000")
    assert projected_daily["purchase_cost_total_usd"] == Decimal("1")
    assert projected_daily["cost_status"] == "complete"
    assert projected_order["wfs_low_price_surcharge_amount"] == Decimal("1.0000")
    assert projected_order["gross_profit_amount"] == Decimal("3.0000")
    assert projected_order["purchase_cost_total_usd"] == Decimal("1")
    _validate_recalculation(
        before,
        after,
        {},
        {},
        recalculation_mode="lpds-only",
    )


def test_lpds_only_preserves_2026_08_10_partial_profit_and_historical_costs() -> None:
    complete = _daily_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=Decimal("5"),
        item_id="complete-item",
    )
    complete.update(
        {
            "id": UUID("00000000-0000-0000-0000-000000000011"),
            "msku": "complete-msku",
            "sales_amount": Decimal("20"),
            "purchase_cost_total_usd": Decimal("3"),
            "first_leg_cost_total_usd": Decimal("2"),
            "cost_status": "complete",
        }
    )
    partial = _daily_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=None,
        item_id="partial-item",
    )
    partial.update(
        {
            "id": UUID("00000000-0000-0000-0000-000000000012"),
            "msku": "partial-msku",
            "sales_amount": Decimal("20"),
            "gross_profit_amount": None,
            "wfs_fee_total_amount": None,
            "purchase_cost_total_usd": None,
            "cost_status": "partial",
        }
    )
    order = _order_row(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        profit=None,
    )
    order.update(
        {
            "id": UUID("00000000-0000-0000-0000-000000000013"),
            "sales_amount": Decimal("40"),
            "gross_profit_amount": None,
            "gross_margin": None,
            "roi": None,
            "cost_status": "partial",
        }
    )
    before = DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, (complete, partial)),
        _snapshot_from_rows(ORDER_TABLE.name, (order,)),
    )

    after = _project_lpds_only_snapshot(before)

    assert after.daily.rows[0]["purchase_cost_total_usd"] == Decimal("3")
    assert after.daily.rows[0]["gross_profit_amount"] == Decimal("5.0000")
    assert after.daily.rows[1]["purchase_cost_total_usd"] is None
    assert after.daily.rows[1]["gross_profit_amount"] is None
    assert after.daily.rows[1]["cost_status"] == "partial"
    assert after.order_profit.rows[0]["gross_profit_amount"] is None
    assert after.order_profit.rows[0]["cost_status"] == "partial"
    assert after.order_profit.profit_sum - after.daily.profit_sum == (
        before.order_profit.profit_sum - before.daily.profit_sum
    )
    _validate_recalculation(
        before,
        after,
        {},
        {},
        recalculation_mode="lpds-only",
    )


def test_lpds_only_rejects_non_lpds_field_drift() -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    projected = _project_lpds_only_snapshot(before)
    drifted_daily = dict(projected.daily.rows[0])
    drifted_daily["purchase_cost_total_usd"] = Decimal("99")
    drifted = DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, (drifted_daily,)),
        projected.order_profit,
    )

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_NON_LPDS_FIELDS_CHANGED"):
        _validate_recalculation(
            before,
            drifted,
            {},
            {},
            recalculation_mode="lpds-only",
        )


def test_lpds_only_keeps_null_profit_null_when_surcharge_is_added() -> None:
    daily = _daily_row(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    daily.update(
        {
            "gross_profit_amount": None,
            "wfs_fee_total_amount": None,
            "cost_status": "partial",
        }
    )
    order = _order_row(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    order.update(
        {
            "sales_amount": Decimal("9"),
            "gross_profit_amount": None,
            "wfs_fee_total_amount": None,
            "cost_status": "partial",
        }
    )
    before = DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, (daily,)),
        _snapshot_from_rows(ORDER_TABLE.name, (order,)),
    )

    after = _project_lpds_only_snapshot(before)

    assert after.daily.rows[0]["wfs_low_price_surcharge_amount"] == Decimal("1.0000")
    assert after.daily.rows[0]["wfs_fee_total_amount"] is None
    assert after.daily.rows[0]["gross_profit_amount"] is None
    assert after.order_profit.rows[0]["wfs_low_price_surcharge_amount"] == Decimal("1.0000")
    assert after.order_profit.rows[0]["wfs_fee_total_amount"] is None
    assert after.order_profit.rows[0]["gross_profit_amount"] is None
    _validate_recalculation(
        before,
        after,
        {},
        {},
        recalculation_mode="lpds-only",
    )
    result = DayRunResult(
        DAY,
        "dry-run",
        before,
        after,
        None,
        recalculation_mode="lpds-only",
    )
    output = "\n".join(result.safe_lines())
    assert "mixed_null_profit_groups=1" in output
    assert "mixed_null_explained_gap_change=0" in output
    assert "unexplained_profit_gap_change=0" in output


def test_lpds_only_allows_explained_mixed_null_profit_gap_change() -> None:
    before = _mixed_null_snapshot()
    after = _project_lpds_only_snapshot(before)

    _validate_recalculation(
        before,
        after,
        {},
        {},
        recalculation_mode="lpds-only",
    )

    assert before.order_profit.rows[0]["gross_profit_amount"] is None
    assert after.order_profit.rows[0]["gross_profit_amount"] is None
    assert after.daily.profit_sum - before.daily.profit_sum == Decimal("-4.0000")
    assert after.order_profit.profit_sum - before.order_profit.profit_sum == 0
    output = "\n".join(
        DayRunResult(
            DAY,
            "dry-run",
            before,
            after,
            None,
            recalculation_mode="lpds-only",
        ).safe_lines()
    )
    assert "comparable_profit_groups=0" in output
    assert "mixed_null_profit_groups=1" in output
    assert "mixed_null_explained_gap_change=4.0000" in output
    assert "unexplained_profit_gap_change=0.0000" in output


def test_lpds_only_rejects_unexplained_mixed_null_profit_gap_change() -> None:
    before = _mixed_null_snapshot()
    projected = _project_lpds_only_snapshot(before)
    daily_rows = [dict(row) for row in projected.daily.rows]
    complete = next(row for row in daily_rows if row["item_id"] == "synthetic-complete-item")
    complete["gross_profit_amount"] = Decimal("5.6984")
    invalid_after = DaySnapshot(
        DAY,
        _snapshot_from_rows(DAILY_TABLE.name, daily_rows),
        projected.order_profit,
    )

    with pytest.raises(
        LpdsHistoryRecalcError,
        match="LPDS_PROFIT_GAP_INVARIANT_FAILED",
    ):
        _validate_recalculation(
            before,
            invalid_after,
            {},
            {},
            recalculation_mode="lpds-only",
        )


def test_lpds_only_rejects_mixed_null_surcharge_rollup_mismatch() -> None:
    before = _mixed_null_snapshot()
    projected = _project_lpds_only_snapshot(before)
    order_row = dict(projected.order_profit.rows[0])
    order_row["wfs_low_price_surcharge_amount"] = Decimal("3.0000")
    invalid_after = DaySnapshot(
        DAY,
        projected.daily,
        _snapshot_from_rows(ORDER_TABLE.name, (order_row,)),
    )

    with pytest.raises(
        LpdsHistoryRecalcError,
        match="LPDS_SURCHARGE_ROLLUP_MISMATCH",
    ):
        _validate_recalculation(
            before,
            invalid_after,
            {},
            {},
            recalculation_mode="lpds-only",
        )


def test_preexisting_profit_gap_is_preserved_and_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        daily_profit=Decimal("691.7949"),
        order_profit=Decimal("694.9721"),
    )
    after = _snapshot(
        version=EXPECTED_CALC_VERSION,
        surcharge=Decimal("1"),
        daily_profit=Decimal("625.7982"),
        order_profit=Decimal("628.9754"),
    )
    session = _Session()
    repository = _Repository([before, after])
    canonical = SimpleNamespace(
        client=None,
        _refresh_daily_sales_mart=lambda: None,
        _refresh_order_profit_mart=lambda: None,
    )
    runner = LpdsHistoryRecalcRunner(
        lambda: session,  # type: ignore[arg-type]
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,  # type: ignore[arg-type,return-value]
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    result = runner._recalculate_day(ACCOUNT, DAY, mode="dry-run", backup_dir=None)

    output = "\n".join(result.safe_lines())
    assert "daily_profit_delta=-65.9967" in output
    assert "order_profit_delta=-65.9967" in output
    assert "pre_profit_gap=3.1772" in output
    assert "post_profit_gap=3.1772" in output
    assert session.transaction.rolled_back is True


def test_profit_gap_change_rolls_back_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(
        version=LEGACY_CALC_VERSION,
        surcharge=Decimal("0"),
        daily_profit=Decimal("691.7949"),
        order_profit=Decimal("694.9721"),
    )
    invalid_after = _snapshot(
        version=EXPECTED_CALC_VERSION,
        surcharge=Decimal("1"),
        daily_profit=Decimal("625.7982"),
        order_profit=Decimal("628.9755"),
    )
    session = _Session()
    repository = _Repository([before, invalid_after])
    canonical = SimpleNamespace(
        client=None,
        _refresh_daily_sales_mart=lambda: None,
        _refresh_order_profit_mart=lambda: None,
    )
    runner = LpdsHistoryRecalcRunner(
        lambda: session,  # type: ignore[arg-type]
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,  # type: ignore[arg-type,return-value]
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    with pytest.raises(
        LpdsHistoryRecalcError,
        match="LPDS_PROFIT_GAP_INVARIANT_FAILED",
    ):
        runner._recalculate_day(ACCOUNT, DAY, mode="commit", backup_dir=tmp_path)

    assert session.transaction.rolled_back is True
    assert session.transaction.committed is False


def test_external_api_client_is_rejected_before_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    session = _Session()
    repository = _Repository([before])
    canonical = SimpleNamespace(client=object())
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_EXTERNAL_CLIENT_FORBIDDEN"):
        runner._recalculate_day(ACCOUNT, DAY, mode="dry-run", backup_dir=None)

    assert session.transaction.rolled_back is True


def test_default_canonical_runner_has_no_external_client() -> None:
    runner = _canonical_runner(_Session(), ACCOUNT, DAY)  # type: ignore[arg-type]

    assert runner.client is None
    assert runner.__class__.__module__.endswith("data_pages_business_rules_v2")


def test_formula_validation_uses_canonical_threshold_logic() -> None:
    validate_lpds_formula(
        (
            {
                "sales_qty": Decimal("0"),
                "sales_amount": Decimal("0"),
                "wfs_low_price_surcharge_amount": Decimal("0"),
            },
            {
                "sales_qty": Decimal("2"),
                "sales_amount": Decimal("19.98"),
                "wfs_low_price_surcharge_amount": Decimal("2"),
            },
            {
                "sales_qty": Decimal("2"),
                "sales_amount": Decimal("20"),
                "wfs_low_price_surcharge_amount": Decimal("0"),
            },
        )
    )

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_FORMULA_MISMATCH"):
        validate_lpds_formula(
            ({"sales_qty": 1, "sales_amount": 9, "wfs_low_price_surcharge_amount": 0},)
        )


def test_validation_failure_rolls_back_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    invalid_after = _snapshot(version=EXPECTED_CALC_VERSION, surcharge=Decimal("0"))
    session = _Session()
    repository = _Repository([before, invalid_after])
    canonical = SimpleNamespace(
        client=None,
        _refresh_daily_sales_mart=lambda: None,
        _refresh_order_profit_mart=lambda: None,
    )
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_FORMULA_MISMATCH"):
        runner._recalculate_day(ACCOUNT, DAY, mode="dry-run", backup_dir=None)

    assert session.transaction.rolled_back is True


def test_backup_round_trip_has_hash_metadata_and_mode_0600(tmp_path: Path) -> None:
    snapshot = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))

    path = write_backup(
        tmp_path,
        ACCOUNT,
        snapshot,
        purpose="before-recalculation",
    )
    backup = read_backup(path)
    restored = _snapshot_from_backup(backup, ACCOUNT)

    assert path.stat().st_mode & 0o777 == 0o600
    assert backup.metadata["schema_version"] == 1
    assert backup.metadata["business_date"] == DAY
    assert restored.daily.content_hash == snapshot.daily.content_hash
    assert restored.order_profit.content_hash == snapshot.order_profit.content_hash
    assert ACCOUNT not in path.name

    document = json.loads(path.read_text(encoding="utf-8"))
    document["metadata"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(LpdsHistoryRecalcError, match="LPDS_BACKUP_HASH_MISMATCH"):
        read_backup(path)


def test_commit_creates_before_image_before_committing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    after = _snapshot(version=EXPECTED_CALC_VERSION, surcharge=Decimal("1"))
    session = _Session()
    repository = _Repository([before, after])
    canonical = SimpleNamespace(
        client=None,
        _refresh_daily_sales_mart=lambda: None,
        _refresh_order_profit_mart=lambda: None,
    )
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
        canonical_runner_factory=lambda *_: canonical,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    result = runner._recalculate_day(
        ACCOUNT,
        DAY,
        mode="commit",
        backup_dir=tmp_path,
    )

    assert session.transaction.committed is True
    assert result.backup_filename is not None
    backup_path = tmp_path / result.backup_filename
    assert backup_path.exists()
    restored = _snapshot_from_backup(read_backup(backup_path), ACCOUNT)
    assert restored.daily.content_hash == before.daily.content_hash


def test_restore_dry_run_only_restores_backup_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _snapshot(version=EXPECTED_CALC_VERSION, surcharge=Decimal("1"))
    backup = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    session = _Session()
    repository = _Repository([current, backup])
    runner = LpdsHistoryRecalcRunner(
        lambda: session,
        app_env=AppEnvironment.TEST,
        repository_factory=lambda _: repository,
    )
    monkeypatch.setattr(runner, "_verify_persisted_state", lambda *_: None)

    result = runner._restore_day(
        ACCOUNT,
        backup,
        mode="dry-run",
        backup_dir=None,
    )

    assert repository.restore_calls == [(ACCOUNT, backup)]
    assert result.business_date == DAY
    assert session.transaction.rolled_back is True


def test_repository_restore_deletes_and_inserts_only_target_scope() -> None:
    session = SimpleNamespace(execute=lambda *args, **kwargs: None)
    repository = LpdsHistoryRepository(session)  # type: ignore[arg-type]
    backup = _snapshot(version=LEGACY_CALC_VERSION, surcharge=Decimal("0"))
    calls: list[tuple[Any, Any]] = []
    session.execute = lambda statement, params=None: calls.append((statement, params))

    repository.restore_snapshot(ACCOUNT, backup)

    assert len(calls) == 4
    assert str(calls[0][0]).startswith("DELETE FROM mart_daily_sales_item_day")
    assert "source_account_ref" in str(calls[0][0])
    assert "business_date_la" in str(calls[0][0])
    assert str(calls[2][0]).startswith("DELETE FROM mart_order_profit_sku_day")


def test_real_postgresql_dry_run_rolls_back_when_isolated_database_is_configured() -> None:
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = get_test_database_url(settings)
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")

    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "create temporary table mart_daily_sales_item_day "
                "(like public.mart_daily_sales_item_day including all)"
            )
            connection.exec_driver_sql(
                "create temporary table mart_order_profit_sku_day "
                "(like public.mart_order_profit_sku_day including all)"
            )
            connection.exec_driver_sql(
                "create temporary table gov_integration_sync_runs "
                "(like public.gov_integration_sync_runs including all)"
            )
            connection.exec_driver_sql("set search_path to pg_temp, public")
            connection.commit()

            with Session(bind=connection) as seed:
                seed.execute(
                    insert(DAILY_TABLE),
                    {
                        "business_date_la": DAY,
                        "source_account_ref": ACCOUNT,
                        "store_id": "synthetic-store",
                        "item_id": "synthetic-item",
                        "msku": "synthetic-msku",
                        "local_sku": "synthetic-sku",
                        "sales_qty": Decimal("1"),
                        "sales_amount": Decimal("9"),
                        "wfs_fee_total_amount": Decimal("5"),
                        "wfs_low_price_surcharge_amount": Decimal("0"),
                        "gross_profit_amount": Decimal("4"),
                        "calc_version": LEGACY_CALC_VERSION,
                        "calculated_at": DAY,
                    },
                )
                seed.execute(
                    insert(ORDER_TABLE),
                    {
                        "business_date_la": DAY,
                        "source_account_ref": ACCOUNT,
                        "local_sku": "synthetic-sku",
                        "wfs_fee_total_amount": Decimal("5"),
                        "wfs_low_price_surcharge_amount": Decimal("0"),
                        "gross_profit_amount": Decimal("4"),
                        "calc_version": LEGACY_CALC_VERSION,
                        "calculated_at": DAY,
                    },
                )
                seed.commit()

            class _DatabaseOnlyCanonical:
                client = None

                def __init__(self, session: Session) -> None:
                    self.session = session

                def _refresh_daily_sales_mart(self) -> None:
                    self.session.execute(
                        update(DAILY_TABLE)
                        .where(
                            DAILY_TABLE.c.source_account_ref == ACCOUNT,
                            DAILY_TABLE.c.business_date_la == DAY,
                        )
                        .values(
                            calc_version=EXPECTED_CALC_VERSION,
                            wfs_low_price_surcharge_amount=Decimal("1"),
                            wfs_fee_total_amount=Decimal("6"),
                            gross_profit_amount=Decimal("3"),
                        )
                    )

                def _refresh_order_profit_mart(self) -> None:
                    self.session.execute(
                        update(ORDER_TABLE)
                        .where(
                            ORDER_TABLE.c.source_account_ref == ACCOUNT,
                            ORDER_TABLE.c.business_date_la == DAY,
                        )
                        .values(
                            calc_version=EXPECTED_CALC_VERSION,
                            wfs_low_price_surcharge_amount=Decimal("1"),
                            wfs_fee_total_amount=Decimal("6"),
                            gross_profit_amount=Decimal("3"),
                        )
                    )

            runner = LpdsHistoryRecalcRunner(
                lambda: Session(bind=connection),
                app_env=AppEnvironment.TEST,
                canonical_runner_factory=lambda session, *_: _DatabaseOnlyCanonical(session),
            )
            result = runner.run(source_account_ref=ACCOUNT, exact_date=DAY)

            assert result.mode == "dry-run"
            assert result.completed[0].after.daily.surcharge_sum == Decimal("1")
            with Session(bind=connection) as verify:
                persisted_version = verify.execute(
                    select(DAILY_TABLE.c.calc_version).where(
                        DAILY_TABLE.c.source_account_ref == ACCOUNT,
                        DAILY_TABLE.c.business_date_la == DAY,
                    )
                ).scalar_one()
                assert persisted_version == LEGACY_CALC_VERSION

            lpds_only_result = LpdsHistoryRecalcRunner(
                lambda: Session(bind=connection),
                app_env=AppEnvironment.TEST,
            ).run(
                source_account_ref=ACCOUNT,
                exact_date=DAY,
                recalculation_mode="lpds-only",
            )

            assert lpds_only_result.completed[0].after.daily.surcharge_sum == Decimal("1.0000")
            with Session(bind=connection) as verify:
                persisted = verify.execute(
                    select(
                        DAILY_TABLE.c.calc_version,
                        DAILY_TABLE.c.wfs_low_price_surcharge_amount,
                    ).where(
                        DAILY_TABLE.c.source_account_ref == ACCOUNT,
                        DAILY_TABLE.c.business_date_la == DAY,
                    )
                ).one()
                assert persisted == (LEGACY_CALC_VERSION, Decimal("0.0000"))
    finally:
        engine.dispose()
