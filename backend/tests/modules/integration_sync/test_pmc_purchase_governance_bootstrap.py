import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.integration_sync.catalog import (
    IntegrationCatalogService,
    PmcPurchaseGovernanceBootstrapError,
    validate_pmc_purchase_source_account_ref,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    RawRetentionPolicy,
)
from app.modules.integration_sync.pmc_purchase_catalog import (
    PMC_PURCHASE_HANDLER_PREFIX,
    PMC_PURCHASE_PAGE_SIZE,
    PMC_PURCHASE_POLICY_PREFIX,
    PMC_PURCHASE_SPECS_BY_INTERFACE_KEY,
    PMC_PURCHASE_SYNC_INTERFACE_SPECS,
    pmc_purchase_interface_keys,
)

REGISTRY_CSV = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "integrations"
    / "lingxing"
    / "data"
    / "official_verified_interfaces.csv"
)
EXPECTED_KEYS = {"purchasePlanList", "purchaseOrderList", "purchaseReceiptOrderList"}


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


def test_catalog_has_three_stable_specs_matching_registry() -> None:
    assert pmc_purchase_interface_keys() == EXPECTED_KEYS
    assert set(PMC_PURCHASE_SPECS_BY_INTERFACE_KEY) == EXPECTED_KEYS
    assert len({spec.handler_key for spec in PMC_PURCHASE_SYNC_INTERFACE_SPECS}) == 3
    assert len({spec.retention_policy_key for spec in PMC_PURCHASE_SYNC_INTERFACE_SPECS}) == 3
    assert len({spec.endpoint_path for spec in PMC_PURCHASE_SYNC_INTERFACE_SPECS}) == 3

    with REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["interface_id"]: row for row in csv.DictReader(handle)}
    for spec in PMC_PURCHASE_SYNC_INTERFACE_SPECS:
        row = rows[spec.registry_interface_id]
        assert row["api_path"] == spec.endpoint_path
        assert row["is_read"] == "是" and row["is_write"] == "否"
        assert (
            int(row["max_page_size_or_length"]) == spec.default_page_size == PMC_PURCHASE_PAGE_SIZE
        )
        assert (row["returns_total"] == "是") is spec.returns_total
        assert spec.request_kind == "offset_page"
        assert spec.handler_key.startswith(PMC_PURCHASE_HANDLER_PREFIX)
        assert spec.handler_key.endswith(".v1")
        assert spec.retention_policy_key.startswith(PMC_PURCHASE_POLICY_PREFIX)
        assert spec.retention_policy_key.endswith("-v1")
        assert spec.initial_outbound_enabled is False
        assert spec.schedule_enabled is False
        assert all(table.startswith("ods_lingxing_") for table in spec.target_tables)


def test_bootstrap_creates_disabled_catalog_records(governance_session: Session) -> None:
    result = IntegrationCatalogService(governance_session).bootstrap_pmc_purchase_governance(
        "primary"
    )
    assert result.interfaces_created == 3
    assert result.retention_policies_created == 3
    assert result.sync_configs_created == 3

    interfaces = governance_session.scalars(select(IntegrationInterface)).all()
    policies = governance_session.scalars(select(RawRetentionPolicy)).all()
    configs = governance_session.scalars(select(IntegrationSyncConfig)).all()
    assert {interface.interface_key for interface in interfaces} == EXPECTED_KEYS
    assert all(interface.provider == "lingxing" for interface in interfaces)
    assert all(interface.method == "POST" for interface in interfaces)
    assert all(interface.request_kind == "offset_page" for interface in interfaces)
    assert all(interface.outbound_enabled is False for interface in interfaces)
    assert {policy.interface_key for policy in policies} == EXPECTED_KEYS
    assert all(policy.hot_retention_days == 365 and policy.is_active for policy in policies)
    assert len(configs) == 3
    assert all(config.is_enabled is False for config in configs)
    assert all(config.schedule_enabled is False for config in configs)
    assert all(config.schedule_cron is None and config.next_run_at is None for config in configs)
    assert all(config.page_size == PMC_PURCHASE_PAGE_SIZE for config in configs)
    assert all(config.max_attempts == 1 for config in configs)
    assert all(config.source_account_ref == "primary" for config in configs)


def test_bootstrap_is_idempotent_and_restores_approved_values(
    governance_session: Session,
) -> None:
    service = IntegrationCatalogService(governance_session)
    service.bootstrap_pmc_purchase_governance("primary")

    second = service.bootstrap_pmc_purchase_governance("primary")
    assert set(second.interface_statuses) == {"unchanged"}
    assert set(second.retention_policy_statuses) == {"unchanged"}
    assert set(second.sync_config_statuses) == {"unchanged"}

    # Drift toward "enabled" must be reverted to the approved disabled defaults.
    interface = governance_session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == "purchaseReceiptOrderList"
        )
    ).one()
    interface.outbound_enabled = True
    config = governance_session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    config.is_enabled = True
    governance_session.commit()

    third = service.bootstrap_pmc_purchase_governance("primary")
    assert third.interface_statuses.count("updated") == 1
    assert third.sync_config_statuses.count("updated") == 1
    governance_session.refresh(interface)
    governance_session.refresh(config)
    assert interface.outbound_enabled is False
    assert config.is_enabled is False


def test_bootstrap_does_not_touch_other_interfaces(governance_session: Session) -> None:
    service = IntegrationCatalogService(governance_session)
    service.bootstrap_productlist_governance("primary")
    before = governance_session.scalars(
        select(IntegrationInterface).where(IntegrationInterface.interface_key == "productList")
    ).one()
    before_outbound = before.outbound_enabled

    service.bootstrap_pmc_purchase_governance("primary")

    governance_session.refresh(before)
    assert before.outbound_enabled is before_outbound
    assert (
        governance_session.scalar(
            select(IntegrationInterface.id).where(
                IntegrationInterface.interface_key == "productList"
            )
        )
        == before.id
    )
    assert len(governance_session.scalars(select(IntegrationInterface)).all()) == 4


@pytest.mark.parametrize("value", ["", " primary", "primary ", "x" * 129])
def test_source_account_ref_validation(value: str) -> None:
    with pytest.raises(PmcPurchaseGovernanceBootstrapError):
        validate_pmc_purchase_source_account_ref(value)
    assert validate_pmc_purchase_source_account_ref("primary") == "primary"
