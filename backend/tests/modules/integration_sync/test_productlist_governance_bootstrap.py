from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine, create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    RawRetentionPolicy,
)
from scripts import bootstrap_productlist_governance as command


@pytest.fixture
def database() -> Iterator[Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    IntegrationInterface.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[IntegrationInterface.__tablename__],
            Base.metadata.tables[RawRetentionPolicy.__tablename__],
            Base.metadata.tables[IntegrationSyncConfig.__tablename__],
        ],
    )
    yield engine
    engine.dispose()


@pytest.mark.parametrize("bootstrap_auth_value", [None, "false", "yes", "1", "on"])
def test_command_requires_exact_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bootstrap_auth_value: str | None,
) -> None:
    if bootstrap_auth_value is None:
        monkeypatch.delenv("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_AUTHORIZED", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_AUTHORIZED", bootstrap_auth_value)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == (
        "PRODUCTLIST_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION"
    )
    session_factory.assert_not_called()


@pytest.mark.parametrize("source_account_ref", [None, "", " scoped", "scoped ", "x" * 129])
def test_command_rejects_invalid_source_account_ref(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source_account_ref: str | None,
) -> None:
    monkeypatch.setenv("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_AUTHORIZED", "true")
    if source_account_ref is None:
        monkeypatch.delenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", raising=False)
    else:
        monkeypatch.setenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", source_account_ref)
    session_factory = MagicMock()
    monkeypatch.setattr(command, "get_session_factory", session_factory)

    assert command.main() == 2
    assert capsys.readouterr().out.strip() == (
        "PRODUCTLIST_GOVERNANCE_BOOTSTRAP_SOURCE_ACCOUNT_REF_INVALID"
    )
    session_factory.assert_not_called()


def test_bootstrap_creates_three_rows_and_is_idempotent(database: Engine) -> None:
    with Session(database) as session:
        service = IntegrationCatalogService(session)
        first = service.bootstrap_productlist_governance("synthetic-account")
        second = service.bootstrap_productlist_governance("synthetic-account")

        interface = session.scalar(select(IntegrationInterface))
        policy = session.scalar(select(RawRetentionPolicy))
        config = session.scalar(select(IntegrationSyncConfig))

        assert (
            first.interface_status,
            first.retention_policy_status,
            first.sync_config_status,
        ) == ("created", "created", "created")
        assert (
            second.interface_status,
            second.retention_policy_status,
            second.sync_config_status,
        ) == ("unchanged", "unchanged", "unchanged")
        assert session.scalar(select(func.count()).select_from(IntegrationInterface)) == 1
        assert session.scalar(select(func.count()).select_from(RawRetentionPolicy)) == 1
        assert session.scalar(select(func.count()).select_from(IntegrationSyncConfig)) == 1
        assert interface is not None
        assert interface.endpoint_path == "/erp/sc/routing/data/local_inventory/productList"
        assert interface.request_kind == "offset_page"
        assert interface.handler_key == "lingxing.product_list_sync.v1"
        assert policy is not None
        assert policy.hot_retention_days == 365
        assert config is not None
        assert config.interface_id == interface.id
        assert config.retention_policy_id == policy.id
        assert config.schedule_enabled is False
        assert config.schedule_cron is None
        assert config.page_size == 1000
        assert config.max_pages == 10000

    assert set(inspect(database).get_table_names()) == {
        "gov_integration_interfaces",
        "gov_integration_sync_configs",
        "gov_raw_retention_policies",
    }


def test_bootstrap_repairs_only_approved_governance_fields(database: Engine) -> None:
    with Session(database) as session:
        service = IntegrationCatalogService(session)
        service.bootstrap_productlist_governance("synthetic-account")
        interface = session.scalar(select(IntegrationInterface))
        policy = session.scalar(select(RawRetentionPolicy))
        config = session.scalar(select(IntegrationSyncConfig))
        assert interface is not None and policy is not None and config is not None
        interface.handler_key = "disabled"
        interface.outbound_enabled = False
        policy.hot_retention_days = 1
        policy.is_active = False
        config.schedule_enabled = True
        config.schedule_cron = "* * * * *"
        config.page_size = 1
        config.max_pages = 1
        session.commit()

        result = service.bootstrap_productlist_governance("synthetic-account")

        assert result.interface_status == "updated"
        assert result.retention_policy_status == "updated"
        assert result.sync_config_status == "updated"
        assert interface.handler_key == "lingxing.product_list_sync.v1"
        assert interface.outbound_enabled is True
        assert policy.hot_retention_days == 365
        assert policy.is_active is True
        assert config.schedule_enabled is False
        assert config.schedule_cron is None
        assert config.page_size == 1000
        assert config.max_pages == 10000


def test_authorized_command_outputs_only_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SimpleNamespace(
        interface_status="created",
        retention_policy_status="created",
        sync_config_status="created",
    )
    service = MagicMock()
    service.bootstrap_productlist_governance.return_value = result
    monkeypatch.setenv("PRODUCTLIST_GOVERNANCE_BOOTSTRAP_AUTHORIZED", "TRUE")
    monkeypatch.setenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", "synthetic-account")
    monkeypatch.setenv("DATABASE_URL", "synthetic-sensitive-url")
    monkeypatch.setenv("LINGXING_APP_SECRET", "synthetic-sensitive-secret")
    monkeypatch.setattr(command, "get_session_factory", MagicMock())
    monkeypatch.setattr(command, "IntegrationCatalogService", MagicMock(return_value=service))

    assert command.main() == 0
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "interface_status=created",
        "retention_policy_status=created",
        "sync_config_status=created",
        "source_account_ref_present=true",
        "schedule_enabled=false",
        "page_size=1000",
        "max_pages=10000",
    ]
    assert "synthetic-account" not in output
    assert "synthetic-sensitive" not in output
    assert "DATABASE_URL" not in output
