"""Opt-in Celery Feishu reconciliation must be safe by default."""

from contextlib import nullcontext
from unittest.mock import MagicMock

from app.modules.iam.feishu_directory_service import FeishuDirectoryUser
from app.modules.iam.organization_tasks import organization_sync_tick


def _directory():
    return (
        ({"department_id": "od-a", "parent_department_id": "0", "name": "Operations"},),
        (FeishuDirectoryUser(name="Synthetic", open_id="ou-a", department_ids=("od-a",)),),
    )


def test_auto_sync_disabled_never_calls_feishu_or_database(monkeypatch) -> None:
    monkeypatch.delenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED", raising=False)
    external = MagicMock()
    factory = MagicMock()
    monkeypatch.setattr("app.modules.iam.organization_tasks._read_feishu", external)
    monkeypatch.setattr("app.modules.iam.organization_tasks.get_session_factory", factory)
    organization_sync_tick()
    external.assert_not_called()
    factory.assert_not_called()


def test_auto_sync_reconciles_safe_snapshots_only(monkeypatch) -> None:
    monkeypatch.setenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED", "1")
    session = MagicMock()
    apply = MagicMock(return_value="run-synthetic")
    monkeypatch.setattr("app.modules.iam.organization_tasks._read_feishu", _directory)
    monkeypatch.setattr(
        "app.modules.iam.organization_tasks.get_session_factory",
        lambda: lambda: nullcontext(session),
    )
    monkeypatch.setattr("app.modules.iam.organization_tasks.apply_snapshot", apply)
    organization_sync_tick()
    assert apply.call_args.kwargs["allow_large_reduction"] is False
    assert apply.call_args.kwargs["allow_identity_replacement"] is False
    assert apply.call_args.kwargs["requested_by"] == "system:feishu-org-auto"
    session.commit.assert_called_once()


def test_auto_sync_never_commits_identity_replacement(monkeypatch) -> None:
    monkeypatch.setenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED", "1")
    session = MagicMock()
    apply = MagicMock(side_effect=ValueError("identity set changed"))
    monkeypatch.setattr("app.modules.iam.organization_tasks._read_feishu", _directory)
    monkeypatch.setattr(
        "app.modules.iam.organization_tasks.get_session_factory",
        lambda: lambda: nullcontext(session),
    )
    monkeypatch.setattr("app.modules.iam.organization_tasks.apply_snapshot", apply)
    organization_sync_tick()
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
