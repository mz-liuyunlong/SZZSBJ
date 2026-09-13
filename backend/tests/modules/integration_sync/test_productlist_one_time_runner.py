from __future__ import annotations

import inspect as python_inspect
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment
from app.db.base import Base
from app.modules.integration_sync.handlers.lingxing_product_list_sync import (
    ProductListSyncResult,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
)
from scripts import run_productlist_once as command

INTERFACE_ID = UUID("00000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000002")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000003")
SOURCE_ACCOUNT_REF = "synthetic-account"


@pytest.fixture
def database() -> Iterator[Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    IntegrationInterface.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[IntegrationInterface.__tablename__],
            Base.metadata.tables[RawRetentionPolicy.__tablename__],
            Base.metadata.tables[IntegrationSyncConfig.__tablename__],
            Base.metadata.tables[IntegrationSyncRun.__tablename__],
        ],
    )
    yield engine
    engine.dispose()


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
        interface_key="productList",
        method="POST",
        endpoint_path="/erp/sc/routing/data/local_inventory/productList",
        request_kind="offset_page",
        handler_key="lingxing.product_list_sync.v1",
        contract_version="v1",
        outbound_enabled=True,
    )
    policy = SimpleNamespace(
        id=POLICY_ID,
        policy_key="lingxing-productlist-v1",
        provider="lingxing",
        interface_key="productList",
        is_active=True,
    )
    config = SimpleNamespace(
        id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        source_account_ref=SOURCE_ACCOUNT_REF,
        is_enabled=True,
        schedule_enabled=False,
        schedule_cron=None,
        page_size=1000,
        max_pages=10000,
        max_attempts=1,
        retention_policy_id=POLICY_ID,
    )
    return interface, policy, config


def _mock_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[command.ProductListOneTimeRunner, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    runner = command.ProductListOneTimeRunner(session)
    repository = MagicMock()
    runner.repository = repository
    interface, policy, config = _governance()
    repository.get_interface_by_key.return_value = interface
    repository.get_retention_policy.return_value = policy
    repository.get_config_by_scope.return_value = config
    repository.has_running_run.return_value = False
    repository.find_run_by_idempotency.return_value = None
    repository.add_run.side_effect = lambda run: run
    repository.productlist_run_aggregate_counts.return_value = (2, 2, 3, 3)
    execution = ProductListSyncResult(
        run_id=UUID("00000000-0000-0000-0000-000000000004"),
        status="succeeded",
        total_captured=3,
        work_items_count=2,
        duplicate_ids_detected=0,
        inactive_ids_count=1,
    )
    handler = MagicMock()

    def execute(run: IntegrationSyncRun, _: IntegrationInterface) -> ProductListSyncResult:
        run.status = execution.status
        run.work_items_total = execution.work_items_count
        run.work_items_succeeded = execution.work_items_count
        run.records_seen = execution.total_captured
        run.records_written = execution.total_captured
        return execution

    handler.execute.side_effect = execute
    monkeypatch.setattr(
        command,
        "LingxingProductListSyncHandler",
        MagicMock(return_value=handler),
    )
    return runner, repository, handler


def _execute(runner: command.ProductListOneTimeRunner) -> command.ProductListOneTimeRunResult:
    return runner.execute(
        source_account_ref=SOURCE_ACCOUNT_REF,
        idempotency_key="productlist-onetime:synthetic",
        reason="Owner authorized validation",
    )


@pytest.mark.parametrize("gate_value", [None, "false", "yes", "1", "on"])
def test_command_requires_exact_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate_value: str | None,
) -> None:
    if gate_value is None:
        monkeypatch.delenv("PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED", gate_value)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == ("PRODUCTLIST_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
    session_factory.assert_not_called()


@pytest.mark.parametrize("source_value", [None, "", " spaced", "contains-token"])
def test_command_accepts_case_insensitive_true_without_opening_database_on_bad_source(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source_value: str | None,
) -> None:
    monkeypatch.setenv("PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED", "TRUE")
    if source_value is None:
        monkeypatch.delenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", source_value)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == (
        "PRODUCTLIST_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID"
    )
    session_factory.assert_not_called()


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("app_env", AppEnvironment.STAGING),
        ("lingxing_enable_token_requests", False),
        ("lingxing_enable_real_calls", False),
        ("lingxing_dry_run", True),
        ("lingxing_allow_raw_write", False),
        ("lingxing_allow_structured_write", True),
        ("lingxing_allow_full_sync", True),
    ],
)
def test_runtime_environment_must_match_every_gate(override: str, value: object) -> None:
    with pytest.raises(
        command.ProductListOneTimeRunError,
        match="PRODUCTLIST_ONE_TIME_RUN_ENV_NOT_AUTHORIZED",
    ):
        command._validate_runtime_settings(_settings(**{override: value}))  # type: ignore[arg-type]


def test_runtime_environment_accepts_only_the_approved_combination() -> None:
    command._validate_runtime_settings(_settings())  # type: ignore[arg-type]


@pytest.mark.parametrize("missing", ["interface", "policy", "config"])
def test_missing_governance_rows_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    if missing == "interface":
        repository.get_interface_by_key.return_value = None
    elif missing == "policy":
        repository.get_retention_policy.return_value = None
    else:
        repository.get_config_by_scope.return_value = None

    with pytest.raises(
        command.ProductListOneTimeRunError,
        match="PRODUCTLIST_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED",
    ):
        _execute(runner)

    repository.add_run.assert_not_called()
    handler.execute.assert_not_called()


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("interface", "endpoint_path", "/not-approved"),
        ("interface", "outbound_enabled", False),
        ("config", "schedule_enabled", True),
        ("config", "page_size", 1001),
        ("config", "max_pages", None),
        ("config", "max_attempts", 2),
        ("policy", "is_active", False),
    ],
)
def test_mismatched_governance_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    field: str,
    value: object,
) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    record = {
        "interface": repository.get_interface_by_key.return_value,
        "policy": repository.get_retention_policy.return_value,
        "config": repository.get_config_by_scope.return_value,
    }[target]
    setattr(record, field, value)

    with pytest.raises(
        command.ProductListOneTimeRunError,
        match="PRODUCTLIST_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED",
    ):
        _execute(runner)

    repository.add_run.assert_not_called()
    handler.execute.assert_not_called()


def test_running_productlist_run_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    repository.has_running_run.return_value = True

    with pytest.raises(
        command.ProductListOneTimeRunError,
        match="PRODUCTLIST_ONE_TIME_RUN_ALREADY_RUNNING",
    ):
        _execute(runner)

    repository.add_run.assert_not_called()
    handler.execute.assert_not_called()


def test_duplicate_idempotency_key_is_not_replayed(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)
    repository.find_run_by_idempotency.return_value = SimpleNamespace(id="existing")

    with pytest.raises(
        command.ProductListOneTimeRunError,
        match="PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT",
    ):
        _execute(runner)

    repository.add_run.assert_not_called()
    handler.execute.assert_not_called()


@pytest.mark.parametrize(
    ("variable", "value", "error_code"),
    [
        (
            "PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_KEY",
            "contains secret material",
            "PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID",
        ),
        (
            "PRODUCTLIST_ONE_TIME_RUN_REASON",
            "inspect raw payload_json",
            "PRODUCTLIST_ONE_TIME_RUN_REASON_INVALID",
        ),
    ],
)
def test_optional_text_rejects_credential_or_payload_like_content(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    error_code: str,
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(command.ProductListOneTimeRunError, match=error_code):
        command._idempotency_key() if "IDEMPOTENCY" in variable else command._reason()


def test_success_creates_one_manual_run_and_calls_handler_directly(
    database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(database) as session:
        interface = IntegrationInterface(
            id=INTERFACE_ID,
            provider="lingxing",
            interface_key="productList",
            display_name="ProductList",
            method="POST",
            endpoint_path="/erp/sc/routing/data/local_inventory/productList",
            request_kind="offset_page",
            handler_key="lingxing.product_list_sync.v1",
            contract_version="v1",
            outbound_enabled=True,
        )
        policy = RawRetentionPolicy(
            id=POLICY_ID,
            policy_key="lingxing-productlist-v1",
            provider="lingxing",
            interface_key="productList",
            hot_retention_days=365,
            archive_required=False,
            legal_hold=False,
            is_active=True,
        )
        config = IntegrationSyncConfig(
            id=CONFIG_ID,
            interface_id=INTERFACE_ID,
            source_account_ref=SOURCE_ACCOUNT_REF,
            is_enabled=True,
            schedule_enabled=False,
            schedule_cron=None,
            schedule_timezone="UTC",
            page_size=1000,
            max_pages=10000,
            max_attempts=1,
            retention_policy_id=POLICY_ID,
        )
        session.add_all([interface, policy, config])
        session.commit()
        runner = command.ProductListOneTimeRunner(session)
        monkeypatch.setattr(
            runner.repository,
            "productlist_run_aggregate_counts",
            lambda _run_id, _source_ref: (2, 2, 3, 3),
        )
        handler_calls: list[tuple[IntegrationSyncRun, IntegrationInterface]] = []

        class FakeHandler:
            def __init__(self, handler_session: Session) -> None:
                assert handler_session is session

            def execute(
                self,
                run: IntegrationSyncRun,
                selected_interface: IntegrationInterface,
            ) -> ProductListSyncResult:
                handler_calls.append((run, selected_interface))
                run.status = "succeeded"
                run.work_items_total = 2
                run.work_items_succeeded = 2
                run.records_seen = 3
                run.records_written = 3
                session.commit()
                return ProductListSyncResult(
                    run_id=run.id,
                    status="succeeded",
                    total_captured=3,
                    work_items_count=2,
                    duplicate_ids_detected=0,
                    inactive_ids_count=1,
                )

        monkeypatch.setattr(command, "LingxingProductListSyncHandler", FakeHandler)

        result = runner.execute(
            source_account_ref=SOURCE_ACCOUNT_REF,
            idempotency_key="productlist-onetime:isolated",
            reason="Owner authorized validation",
        )

        stored = session.scalar(select(IntegrationSyncRun))
        assert session.scalar(select(func.count()).select_from(IntegrationSyncRun)) == 1
        assert stored is not None
        assert stored.trigger_type == "manual"
        assert stored.requested_by == "owner-authorized-cli"
        assert stored.source_account_ref == SOURCE_ACCOUNT_REF
        assert stored.config_id == CONFIG_ID
        assert stored.interface_id == INTERFACE_ID
        assert stored.work_items_total == 2
        assert result.run_status == "succeeded"
        assert result.raw_blobs_count == 2
        assert handler_calls == [(stored, interface)]
        assert config.is_enabled is True
        assert config.schedule_enabled is False
        assert interface.outbound_enabled is True
        assert policy.is_active is True


def test_runner_has_no_api_celery_batch_or_unapproved_table_path() -> None:
    source = python_inspect.getsource(command)
    for forbidden in (
        "dispatch_sync_run",
        "execute_sync_run",
        "scheduler_tick",
        "batchGetProductInfo",
        "dws_",
        "old-system",
    ):
        assert forbidden not in source


def test_authorized_command_outputs_safe_summary_without_environment_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = command.ProductListOneTimeRunResult(
        run_id=UUID("00000000-0000-0000-0000-000000000004"),
        run_status="succeeded",
        error_code=None,
        reason_present=True,
        page_size=1000,
        max_pages=10000,
        work_items_total=2,
        work_items_succeeded=2,
        work_items_failed=0,
        records_seen=3,
        records_written=3,
        raw_blobs_count=2,
        request_refs_count=2,
        productlist_refs_count=3,
        sku_identity_active_count=3,
        duplicate_ids_detected=0,
        inactive_ids_count=1,
    )

    runner = MagicMock()
    runner.execute.return_value = result
    session_factory = MagicMock()
    monkeypatch.setenv("PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED", "true")
    monkeypatch.setenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", SOURCE_ACCOUNT_REF)
    monkeypatch.setenv("DATABASE_URL", "synthetic-sensitive-database")
    monkeypatch.setenv("LINGXING_APP_ID", "synthetic-sensitive-app")
    monkeypatch.setenv("LINGXING_APP_SECRET", "synthetic-sensitive-secret")
    monkeypatch.delenv("PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_KEY", raising=False)
    monkeypatch.delenv("PRODUCTLIST_ONE_TIME_RUN_REASON", raising=False)
    monkeypatch.setattr(command, "get_settings", lambda: _settings())
    monkeypatch.setattr(command, "get_session_factory", session_factory)
    monkeypatch.setattr(command, "ProductListOneTimeRunner", MagicMock(return_value=runner))

    assert command.main() == 0
    output = capsys.readouterr().out

    assert SOURCE_ACCOUNT_REF not in output
    assert "synthetic-sensitive" not in output
    assert "DATABASE_URL" not in output
    assert "payload_json" not in output
    assert "Authorization" not in output
    assert output.splitlines()[0] == "preflight_status=PASS"
    runner.execute.assert_called_once()


def test_failed_handler_result_outputs_only_safe_code_and_aggregates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner, repository, handler = _mock_runner(monkeypatch)

    def fail(run: IntegrationSyncRun, _: IntegrationInterface) -> ProductListSyncResult:
        run.status = "failed"
        run.error_code = "SYNC_PRODUCTLIST_TRANSPORT_FAILED"
        run.work_items_total = 1
        run.work_items_failed = 1
        return ProductListSyncResult(
            run_id=run.id,
            status="failed",
            total_captured=0,
            work_items_count=1,
            duplicate_ids_detected=0,
            inactive_ids_count=0,
        )

    handler.execute.side_effect = fail
    result = _execute(runner)

    command._print_result(result)
    output = capsys.readouterr().out
    assert "run_status=failed" in output
    assert "error_code=SYNC_PRODUCTLIST_TRANSPORT_FAILED" in output
    assert "work_items_total=1" in output
    assert "records_seen=0" in output
    assert SOURCE_ACCOUNT_REF not in output
    repository.update_config.assert_not_called()
    repository.add_catalog_record.assert_not_called()
