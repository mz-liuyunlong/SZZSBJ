from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    RawRetentionPolicy,
)
from scripts import bootstrap_wfs_governance as command


@pytest.fixture
def governance_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(
            engine,
            tables=(
                cast(Table, IntegrationInterface.__table__),
                cast(Table, RawRetentionPolicy.__table__),
                cast(Table, IntegrationSyncConfig.__table__),
            ),
        )
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_wfs_governance_bootstrap_is_idempotent_and_default_off(
    governance_session: Session,
) -> None:
    service = IntegrationCatalogService(governance_session)

    first = service.bootstrap_wfs_governance("primary")
    second = service.bootstrap_wfs_governance("primary")

    assert first.interface_statuses == ("created",)
    assert first.retention_policy_statuses == ("created",)
    assert first.sync_config_statuses == ("created",)
    assert second.interface_statuses == ("unchanged",)
    assert second.retention_policy_statuses == ("unchanged",)
    assert second.sync_config_statuses == ("unchanged",)

    interface = governance_session.scalars(select(IntegrationInterface)).one()
    policy = governance_session.scalars(select(RawRetentionPolicy)).one()
    config = governance_session.scalars(select(IntegrationSyncConfig)).one()
    assert interface.interface_key == "wfsProfitOrder"
    assert interface.outbound_enabled is False
    assert policy.interface_key == "wfsProfitOrder"
    assert config.is_enabled is False
    assert config.schedule_enabled is False
    assert config.schedule_cron is None
    assert config.page_size == 20
    assert config.max_pages == 500


def test_wfs_governance_command_requires_explicit_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(command.AUTHORIZATION_ENV, raising=False)

    assert command.main() == 2
    assert capsys.readouterr().out == "WFS_GOVERNANCE_BOOTSTRAP_REQUIRES_AUTHORIZATION\n"


def test_wfs_governance_command_outputs_only_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SimpleNamespace(
        interface_statuses=("created",),
        retention_policy_statuses=("created",),
        sync_config_statuses=("created",),
    )
    service = MagicMock()
    service.bootstrap_wfs_governance.return_value = result
    monkeypatch.setenv(command.AUTHORIZATION_ENV, "TRUE")
    monkeypatch.setenv(command.SOURCE_ACCOUNT_ENV, "synthetic-account")
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
        "outbound_enabled=false",
        "is_enabled=false",
        "schedule_enabled=false",
        "page_size=20",
        "max_pages=500",
    ]
    assert "synthetic-account" not in output
    assert "synthetic-sensitive" not in output
