from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.integration_sync.catalog import (
    DataPagesGovernanceBootstrapError,
    IntegrationCatalogService,
)
from app.modules.integration_sync.data_pages_catalog import DATA_PAGES_SYNC_INTERFACE_SPECS
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    RawRetentionPolicy,
)


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
                IntegrationInterface.__table__,
                RawRetentionPolicy.__table__,
                IntegrationSyncConfig.__table__,
            ),
        )
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_data_pages_governance_bootstrap_creates_disabled_catalog_records(
    governance_session: Session,
) -> None:
    result = IntegrationCatalogService(governance_session).bootstrap_data_pages_governance(
        "default"
    )

    assert result.interfaces_created == 7
    assert result.retention_policies_created == 7
    assert result.sync_configs_created == 7

    interfaces = governance_session.scalars(select(IntegrationInterface)).all()
    policies = governance_session.scalars(select(RawRetentionPolicy)).all()
    configs = governance_session.scalars(select(IntegrationSyncConfig)).all()

    assert len(interfaces) == len(DATA_PAGES_SYNC_INTERFACE_SPECS)
    assert len(policies) == len(DATA_PAGES_SYNC_INTERFACE_SPECS)
    assert len(configs) == len(DATA_PAGES_SYNC_INTERFACE_SPECS)
    assert {interface.interface_key for interface in interfaces} == {
        spec.interface_key for spec in DATA_PAGES_SYNC_INTERFACE_SPECS
    }
    assert all(interface.outbound_enabled is False for interface in interfaces)
    assert all(policy.hot_retention_days == 365 for policy in policies)
    assert all(policy.is_active is True for policy in policies)
    assert all(config.is_enabled is False for config in configs)
    assert all(config.schedule_enabled is False for config in configs)
    assert all(config.source_account_ref == "default" for config in configs)


def test_data_pages_governance_bootstrap_is_idempotent(
    governance_session: Session,
) -> None:
    service = IntegrationCatalogService(governance_session)
    service.bootstrap_data_pages_governance("default")

    result = service.bootstrap_data_pages_governance("default")

    assert set(result.interface_statuses) == {"unchanged"}
    assert set(result.retention_policy_statuses) == {"unchanged"}
    assert set(result.sync_config_statuses) == {"unchanged"}


def test_data_pages_governance_bootstrap_rejects_unsafe_account_ref(
    governance_session: Session,
) -> None:
    with pytest.raises(DataPagesGovernanceBootstrapError) as exc_info:
        IntegrationCatalogService(governance_session).bootstrap_data_pages_governance(" default")

    assert str(exc_info.value) == "DATA_PAGES_GOVERNANCE_BOOTSTRAP_SOURCE_ACCOUNT_REF_INVALID"
