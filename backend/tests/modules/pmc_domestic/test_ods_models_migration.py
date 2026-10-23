"""Guardrails: domestic ODS models, Alembic 0047, and registry agree."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_domestic import models as domestic_models
from app.modules.pmc_domestic.models import PMC_DOMESTIC_ODS_TABLES

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261019_0047_domestic_warehouse_ods"
PREVIOUS = "20261019_0046_operation_logs"
GOVERNANCE_COLUMNS = {
    "id",
    "run_id",
    "raw_request_ref_id",
    "source_account_ref",
    "source_item_ordinal",
    "payload_json",
    "observed_at",
    "created_at",
}


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


def test_metadata_declares_exactly_the_four_ods_tables() -> None:
    register_productlist_sync_models()
    assert set(PMC_DOMESTIC_ODS_TABLES) == {
        "ods_lingxing_domestic_warehouses",
        "ods_lingxing_domestic_inventory",
        "ods_lingxing_domestic_batches",
        "ods_lingxing_domestic_inventory_events",
    }
    for table in PMC_DOMESTIC_ODS_TABLES:
        assert table in Base.metadata.tables, table
        columns = set(Base.metadata.tables[table].columns.keys())
        assert GOVERNANCE_COLUMNS <= columns, table


def test_registry_and_alembic_env_register_the_models() -> None:
    register_productlist_sync_models()
    assert "ods_lingxing_domestic_warehouses" in Base.metadata.tables
    env_source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "import app.modules.pmc_domestic.models" in env_source
    registry_source = (BACKEND_ROOT / "app" / "db" / "model_registry.py").read_text(
        encoding="utf-8"
    )
    assert "import app.modules.pmc_domestic.models" in registry_source


def test_migration_revision_chain_points_at_operation_logs() -> None:
    revision_file = (
        BACKEND_ROOT / "alembic" / "versions" / "20261019_0047_domestic_warehouse_ods.py"
    ).read_text(encoding="utf-8")
    assert f'revision: str = "{REVISION}"' in revision_file
    assert "down_revision" in revision_file and PREVIOUS in revision_file
    assert "adopt_domestic_ods_tables" in revision_file
    assert domestic_models.LingxingDomesticWarehouseOds.__tablename__ in PMC_DOMESTIC_ODS_TABLES
