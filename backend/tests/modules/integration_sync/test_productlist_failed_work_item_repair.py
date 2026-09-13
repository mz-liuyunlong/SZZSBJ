from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from scripts import repair_productlist_failed_work_items as command

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def _eligible_run() -> SimpleNamespace:
    return SimpleNamespace(
        id=RUN_ID,
        provider="lingxing",
        interface_key="productList",
        status="failed",
        error_code="SYNC_PRODUCTLIST_PUBLISH_FAILED",
        work_items_failed=0,
    )


def _repair() -> tuple[command.ProductListFailedWorkItemRepair, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    service = command.ProductListFailedWorkItemRepair(session)
    repository = MagicMock()
    service.repository = repository
    repository.get_run_for_update.return_value = _eligible_run()
    return service, repository, session


@pytest.mark.parametrize("gate_value", [None, "false", "yes", "1", "on"])
def test_command_requires_exact_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate_value: str | None,
) -> None:
    if gate_value is None:
        monkeypatch.delenv("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_AUTHORIZED", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_AUTHORIZED", gate_value)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == (
        "PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_REQUIRES_AUTHORIZATION"
    )
    session_factory.assert_not_called()


@pytest.mark.parametrize("run_id_value", [None, "", "not-a-uuid"])
def test_command_rejects_missing_or_invalid_run_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_id_value: str | None,
) -> None:
    monkeypatch.setenv("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_AUTHORIZED", "true")
    if run_id_value is None:
        monkeypatch.delenv("PRODUCTLIST_REPAIR_RUN_ID", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_REPAIR_RUN_ID", run_id_value)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == (
        "PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_RUN_ID_INVALID"
    )
    session_factory.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other"),
        ("interface_key", "other"),
        ("status", "running"),
        ("error_code", None),
        ("error_code", "unsafe value"),
    ],
)
def test_repair_rejects_ineligible_run(field: str, value: object) -> None:
    service, repository, session = _repair()
    setattr(repository.get_run_for_update.return_value, field, value)

    with pytest.raises(
        command.ProductListRepairError,
        match="PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_RUN_NOT_ELIGIBLE",
    ):
        service.repair(RUN_ID)

    repository.list_running_work_items_for_update.assert_not_called()
    session.commit.assert_not_called()


def test_repair_updates_only_running_work_state() -> None:
    service, repository, session = _repair()
    run = repository.get_run_for_update.return_value
    work = SimpleNamespace(
        status="running",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    repository.list_running_work_items_for_update.return_value = [work]

    result = service.repair(RUN_ID)

    assert result.repair_status == "PASS"
    assert result.repaired_work_items_count == 1
    assert work.status == "failed"
    assert work.error_code == "SYNC_PRODUCTLIST_PUBLISH_FAILED"
    assert work.error_message == "ProductList work item repaired after failed run"
    assert work.finished_at is not None
    assert run.work_items_failed == 1
    session.commit.assert_called_once_with()
    assert [call[0] for call in repository.mock_calls] == [
        "get_run_for_update",
        "list_running_work_items_for_update",
    ]


def test_repair_is_noop_without_running_work_item() -> None:
    service, repository, session = _repair()
    run = repository.get_run_for_update.return_value
    repository.list_running_work_items_for_update.return_value = []

    result = service.repair(RUN_ID)

    assert result.repair_status == "NOOP"
    assert result.repaired_work_items_count == 0
    assert run.work_items_failed == 0
    session.commit.assert_not_called()


def test_command_outputs_only_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = command.ProductListRepairResult(
        repair_status="PASS",
        run_id=RUN_ID,
        repaired_work_items_count=1,
        run_error_code_present=True,
    )
    service = MagicMock()
    service.repair.return_value = result
    monkeypatch.setenv("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_AUTHORIZED", "TRUE")
    monkeypatch.setenv("PRODUCTLIST_REPAIR_RUN_ID", str(RUN_ID))
    monkeypatch.setenv("DATABASE_URL", "synthetic-sensitive-database")
    monkeypatch.setenv("LINGXING_APP_ID", "synthetic-sensitive-app")
    monkeypatch.setenv("LINGXING_APP_SECRET", "synthetic-sensitive-secret")
    monkeypatch.setattr(command, "get_session_factory", MagicMock())
    monkeypatch.setattr(command, "ProductListFailedWorkItemRepair", MagicMock(return_value=service))

    assert command.main() == 0
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "repair_status=PASS",
        f"run_id={RUN_ID}",
        "repaired_work_items_count=1",
        "run_error_code_present=true",
    ]
    assert "synthetic-sensitive" not in output
    for forbidden in (
        "DATABASE_URL",
        "Token",
        "App ID",
        "App Secret",
        "access_token",
        "Authorization",
        "sign",
        "payload_json",
        "RAW",
        "SKU",
        "product_name",
    ):
        assert forbidden not in output
