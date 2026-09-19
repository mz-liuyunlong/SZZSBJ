from __future__ import annotations

import inspect as python_inspect
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment
from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import (
    PmcPurchaseSyncResult,
)
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncRun
from app.modules.integration_sync.parsers.lingxing_purchase import PurchaseQualityReport
from app.modules.integration_sync.pmc_purchase_catalog import PMC_PURCHASE_SPECS_BY_INTERFACE_KEY
from scripts import run_pmc_purchase_once as command

INTERFACE_ID = UUID("00000000-0000-0000-0000-00000000e001")
POLICY_ID = UUID("00000000-0000-0000-0000-00000000e002")
CONFIG_ID = UUID("00000000-0000-0000-0000-00000000e003")
SOURCE_ACCOUNT_REF = "primary"
SPEC = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY["purchaseOrderList"]
WINDOW = (date(2026, 8, 1), date(2026, 8, 31))
REQUIRED_ENV = {
    "PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED": "true",
    "PMC_PURCHASE_INTERFACE_KEY": "purchaseOrderList",
    "PMC_PURCHASE_SOURCE_ACCOUNT_REF": SOURCE_ACCOUNT_REF,
    "PMC_PURCHASE_WINDOW_START": "2026-08-01",
    "PMC_PURCHASE_WINDOW_END": "2026-08-31",
}


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "app_env": AppEnvironment.PRODUCTION,
        "lingxing_enable_token_requests": True,
        "lingxing_enable_real_calls": True,
        "lingxing_dry_run": False,
        "lingxing_allow_raw_write": True,
        "lingxing_allow_structured_write": False,
        "lingxing_allow_full_sync": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _governance() -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    interface = SimpleNamespace(
        id=INTERFACE_ID,
        provider="lingxing",
        interface_key=SPEC.interface_key,
        method="POST",
        endpoint_path=SPEC.endpoint_path,
        request_kind="offset_page",
        handler_key=SPEC.handler_key,
        contract_version="v1",
        outbound_enabled=True,
    )
    policy = SimpleNamespace(
        id=POLICY_ID,
        policy_key=SPEC.retention_policy_key,
        provider="lingxing",
        interface_key=SPEC.interface_key,
        is_active=True,
    )
    config = SimpleNamespace(
        id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        source_account_ref=SOURCE_ACCOUNT_REF,
        is_enabled=True,
        schedule_enabled=False,
        schedule_cron=None,
        page_size=500,
        max_pages=1000,
        max_attempts=1,
        retention_policy_id=POLICY_ID,
    )
    return interface, policy, config


def _mock_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[command.PmcPurchaseOneTimeRunner, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    runner = command.PmcPurchaseOneTimeRunner(session)
    repository = MagicMock()
    runner.repository = repository
    interface, policy, config = _governance()
    repository.get_interface_by_key.return_value = interface
    repository.get_retention_policy.return_value = policy
    repository.get_config_by_scope.return_value = config
    repository.has_running_run.return_value = False
    repository.find_run_by_idempotency.return_value = None
    repository.add_run.side_effect = lambda run: run
    handler = MagicMock()

    def execute(run: IntegrationSyncRun, _: IntegrationInterface) -> PmcPurchaseSyncResult:
        run.status = "succeeded"
        run.work_items_total = 2
        run.work_items_succeeded = 2
        run.records_seen = 3
        run.records_written = 5
        return PmcPurchaseSyncResult(
            run_id=run.id,
            interface_key=SPEC.interface_key,
            status="succeeded",
            total_captured=3,
            headers_written=3,
            lines_written=2,
            work_items_count=2,
            duplicates_skipped=0,
            quality=PurchaseQualityReport(header_line_mismatches=1),
        )

    handler.execute.side_effect = execute
    monkeypatch.setitem(
        command.PMC_PURCHASE_HANDLERS, SPEC.interface_key, MagicMock(return_value=handler)
    )
    return runner, repository, handler


def _execute(runner: command.PmcPurchaseOneTimeRunner) -> command.PmcPurchaseOneTimeRunResult:
    return runner.execute(
        spec=SPEC,
        source_account_ref=SOURCE_ACCOUNT_REF,
        window_start=WINDOW[0],
        window_end=WINDOW[1],
        idempotency_key="pmc-purchase-onetime:test",
        reason="synthetic",
    )


def _set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    for key, value in {**REQUIRED_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


# --- gates -----------------------------------------------------------------------------


@pytest.mark.parametrize("gate_value", [None, "false", "yes", "1", "on", " true"])
def test_command_requires_exact_authorization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], gate_value: str | None
) -> None:
    _set_env(monkeypatch, PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED=gate_value)
    monkeypatch.setattr(command, "get_session_factory", MagicMock(side_effect=AssertionError))
    assert command.main() == 2
    assert capsys.readouterr().out.strip() == "PMC_PURCHASE_ONE_TIME_RUN_REQUIRES_AUTHORIZATION"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"PMC_PURCHASE_INTERFACE_KEY": "productList"},
            "PMC_PURCHASE_ONE_TIME_RUN_INTERFACE_KEY_INVALID",
        ),
        ({"PMC_PURCHASE_INTERFACE_KEY": None}, "PMC_PURCHASE_ONE_TIME_RUN_INTERFACE_KEY_INVALID"),
        (
            {"PMC_PURCHASE_SOURCE_ACCOUNT_REF": " primary"},
            "PMC_PURCHASE_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID",
        ),
        (
            {"PMC_PURCHASE_WINDOW_START": "2026-07-31"},
            "PMC_PURCHASE_ONE_TIME_RUN_WINDOW_BEFORE_GO_LIVE",
        ),
        ({"PMC_PURCHASE_WINDOW_END": "2026-11-30"}, "PMC_PURCHASE_ONE_TIME_RUN_WINDOW_INVALID"),
        ({"PMC_PURCHASE_WINDOW_END": "2026-07-31"}, "PMC_PURCHASE_ONE_TIME_RUN_WINDOW_INVALID"),
        ({"PMC_PURCHASE_WINDOW_START": "08/01/2026"}, "PMC_PURCHASE_ONE_TIME_RUN_WINDOW_INVALID"),
        (
            {"PMC_PURCHASE_ONE_TIME_RUN_REASON": "see https://x"},
            "PMC_PURCHASE_ONE_TIME_RUN_REASON_INVALID",
        ),
        (
            {"PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY": "token=abc"},
            "PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID",
        ),
    ],
)
def test_input_validation_fails_before_database_or_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, str | None],
    expected: str,
) -> None:
    _set_env(monkeypatch, **overrides)
    monkeypatch.setattr(command, "get_settings", MagicMock(side_effect=AssertionError))
    monkeypatch.setattr(command, "get_session_factory", MagicMock(side_effect=AssertionError))
    assert command.main() == 2
    assert capsys.readouterr().out.strip() == expected


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("app_env", AppEnvironment.TEST),
        ("lingxing_enable_token_requests", False),
        ("lingxing_enable_real_calls", False),
        ("lingxing_dry_run", True),
        ("lingxing_allow_raw_write", False),
        ("lingxing_allow_structured_write", True),
        ("lingxing_allow_full_sync", True),
    ],
)
def test_runtime_environment_must_match_every_gate(override: str, value: object) -> None:
    with pytest.raises(command.PmcPurchaseOneTimeRunError):
        command._validate_runtime_settings(_settings(**{override: value}))  # type: ignore[arg-type]
    command._validate_runtime_settings(_settings())  # type: ignore[arg-type]


# --- governance ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i, p, c: setattr(i, "outbound_enabled", False),
        lambda i, p, c: setattr(i, "handler_key", "lingxing.product_list_sync.v1"),
        lambda i, p, c: setattr(
            i, "endpoint_path", "/erp/sc/routing/data/local_inventory/productList"
        ),
        lambda i, p, c: setattr(p, "is_active", False),
        lambda i, p, c: setattr(p, "policy_key", "lingxing-productlist-v1"),
        lambda i, p, c: setattr(c, "is_enabled", False),
        lambda i, p, c: setattr(c, "schedule_enabled", True),
        lambda i, p, c: setattr(c, "page_size", 501),
        lambda i, p, c: setattr(c, "max_attempts", 3),
        lambda i, p, c: setattr(c, "source_account_ref", "other"),
    ],
)
def test_mismatched_governance_is_rejected(monkeypatch: pytest.MonkeyPatch, mutate) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    interface = repository.get_interface_by_key.return_value
    policy = repository.get_retention_policy.return_value
    config = repository.get_config_by_scope.return_value
    mutate(interface, policy, config)
    with pytest.raises(command.PmcPurchaseOneTimeRunError) as error:
        _execute(runner)
    assert str(error.value) == "PMC_PURCHASE_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED"
    repository.add_run.assert_not_called()
    handler.execute.assert_not_called()


def test_missing_governance_rows_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, repository, _ = _mock_runner(monkeypatch)
    repository.get_interface_by_key.return_value = None
    with pytest.raises(command.PmcPurchaseOneTimeRunError):
        _execute(runner)
    repository.add_run.assert_not_called()


def test_any_running_purchase_run_blocks_a_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, repository, _ = _mock_runner(monkeypatch)
    repository.has_running_run.side_effect = lambda provider, key: key == "purchasePlanList"
    with pytest.raises(command.PmcPurchaseOneTimeRunError) as error:
        _execute(runner)
    assert str(error.value) == "PMC_PURCHASE_ONE_TIME_RUN_ALREADY_RUNNING"
    repository.add_run.assert_not_called()


def test_duplicate_idempotency_key_is_not_replayed(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, repository, _ = _mock_runner(monkeypatch)
    repository.find_run_by_idempotency.return_value = SimpleNamespace(id=UUID(int=9))
    with pytest.raises(command.PmcPurchaseOneTimeRunError) as error:
        _execute(runner)
    assert str(error.value) == "PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT"
    repository.add_run.assert_not_called()


# --- success ---------------------------------------------------------------------------


def test_success_creates_one_manual_windowed_run_and_calls_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    result = _execute(runner)

    run = repository.add_run.call_args.args[0]
    assert isinstance(run, IntegrationSyncRun)
    assert run.trigger_type == "manual"
    assert run.interface_key == "purchaseOrderList"
    assert run.window_start == datetime(2026, 8, 1, tzinfo=UTC)
    assert run.window_end == datetime(2026, 8, 31, tzinfo=UTC)
    assert run.requested_by == "owner-authorized-cli"
    handler.execute.assert_called_once()
    assert result.run_status == "succeeded"
    assert result.headers_written == 3 and result.lines_written == 2
    assert result.window_start == WINDOW[0] and result.window_end == WINDOW[1]
    assert "header_line_mismatches=1" in result.quality_summary


def test_authorized_command_outputs_safe_summary_without_environment_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "synthetic-sensitive-database")
    monkeypatch.setenv("LINGXING_APP_ID", "synthetic-sensitive-app")
    monkeypatch.setenv("LINGXING_APP_SECRET", "synthetic-sensitive-secret")
    monkeypatch.setattr(command, "get_settings", MagicMock(return_value=_settings()))
    runner, _, _ = _mock_runner(monkeypatch)
    factory = MagicMock()
    factory.return_value.__enter__.return_value = MagicMock(spec=Session)
    monkeypatch.setattr(command, "get_session_factory", MagicMock(return_value=factory))
    monkeypatch.setattr(command, "PmcPurchaseOneTimeRunner", MagicMock(return_value=runner))

    assert command.main() == 0
    out = capsys.readouterr().out
    assert "preflight_status=PASS" in out
    assert "interface_key=purchaseOrderList" in out
    assert "window_start=2026-08-01" in out
    assert "schedule_enabled=false" in out
    assert "quality=header_line_mismatches=1" in out
    for sensitive in ("synthetic-sensitive", SOURCE_ACCOUNT_REF, "postgresql"):
        assert sensitive not in out


def test_runner_has_no_api_celery_or_scheduler_path() -> None:
    source = python_inspect.getsource(command)
    for forbidden in ("celery", "scheduler_tick", "fastapi", "schedule_enabled=True", "delay("):
        assert forbidden not in source
