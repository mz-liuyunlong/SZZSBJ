import runpy
from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

import alembic
from app.core.config import SettingsError, get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DATABASE_URL = (
    "postgresql+psycopg://synthetic_user:synthetic_password@localhost/synthetic_db"
)
WALMART_HEAD_REVISION = "20261020_0047_walmart_order_identity_guard"
DOMESTIC_HEAD_REVISION = "20261022_0053_domestic_packing_production_compat"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run_offline_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    configured: dict[str, Any] = {}
    fake_context = SimpleNamespace(
        config=SimpleNamespace(config_file_name=None),
        configure=lambda **values: configured.update(values),
        begin_transaction=nullcontext,
        run_migrations=lambda: None,
        is_offline_mode=lambda: True,
    )
    monkeypatch.setattr(alembic, "context", fake_context)
    runpy.run_path(str(BACKEND_ROOT / "alembic" / "env.py"))
    return configured


def test_alembic_scaffold_loads_offline_with_current_revision_chain() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("sqlalchemy.url") is None
    assert set(script.get_heads()) == {WALMART_HEAD_REVISION, DOMESTIC_HEAD_REVISION}
    assert (
        script.get_revision("20261015_0036_wfs_cases").down_revision
        == "20261014_0035_add_auth_rbac"
    )
    assert (
        script.get_revision("20261016_0037_approval_workbench").down_revision
        == "20261015_0036_wfs_cases"
    )
    assert (
        script.get_revision("20261016_0038_rbac_v2").down_revision
        == "20261016_0037_approval_workbench"
    )
    assert (
        script.get_revision("20261016_0039_retire_legacy_rbac_permissions").down_revision
        == "20261016_0038_rbac_v2"
    )
    assert (
        script.get_revision("20261016_0040_restrict_default_data_scopes").down_revision
        == "20261016_0039_retire_legacy_rbac_permissions"
    )
    assert (
        script.get_revision("20261016_0041_wfs_rbac_actions").down_revision
        == "20261016_0040_restrict_default_data_scopes"
    )
    assert (
        script.get_revision("20261017_0042_rbac_backfill").down_revision
        == "20261016_0041_wfs_rbac_actions"
    )
    assert (
        script.get_revision("20261017_0043_purchase_board_listing_item_source").down_revision
        == "20261017_0042_rbac_backfill"
    )
    assert (
        script.get_revision("20261019_0044_approval_flow").down_revision
        == "20261017_0043_purchase_board_listing_item_source"
    )
    assert (
        script.get_revision("20261019_0045_approval_scope").down_revision
        == "20261019_0044_approval_flow"
    )
    assert (
        script.get_revision("20261019_0046_operation_logs").down_revision
        == "20261019_0045_approval_scope"
    )
    assert (
        script.get_revision(WALMART_HEAD_REVISION).down_revision
        == "20261019_0046_operation_logs"
    )
    assert (
        script.get_revision("20261019_0047_domestic_warehouse_ods").down_revision
        == "20261019_0046_operation_logs"
    )
    expected_chain = (
        (
            "20261019_0048_domestic_warehouse_dwd_and_permission",
            "20261019_0047_domestic_warehouse_ods",
        ),
        (
            "20261020_0049_domestic_inbound_board",
            "20261019_0048_domestic_warehouse_dwd_and_permission",
        ),
        ("20261020_0050_domestic_packing_approval", "20261020_0049_domestic_inbound_board"),
        ("20261021_0051_domestic_packing_lifecycle", "20261020_0050_domestic_packing_approval"),
        ("20261021_0052_domestic_packing_manual", "20261021_0051_domestic_packing_lifecycle"),
        (DOMESTIC_HEAD_REVISION, "20261021_0052_domestic_packing_manual"),
    )
    for revision, parent in expected_chain:
        assert script.get_revision(revision).down_revision == parent
    assert len(WALMART_HEAD_REVISION) <= 128
    assert len(DOMESTIC_HEAD_REVISION) <= 128
    revisions = {path.name for path in (BACKEND_ROOT / "alembic" / "versions").glob("*.py")}
    assert {
        "20260912_0003_add_integration_governance.py",
        "20260912_0004_add_integration_ods.py",
        "20260912_0005_add_lingxing_sku_dwd.py",
        "20260912_0006_add_sku_dws.py",
        "20260913_0007_add_product_management_bff.py",
        "20260914_0008_fix_data_lineage_uniqueness.py",
        "20260915_0009_add_media_image_assets.py",
        "20260916_0010_add_productinfo_business_hash.py",
        "20260917_0012_add_sample_and_refund_business_amounts.py",
        "20260917_0013_add_order_provider_identifiers.py",
        "20260918_0014_add_daily_sales_truth_fields.py",
        "20260918_0015_add_wfs_fee_actual_and_cases.py",
        "20260919_0016_add_pmc_purchase_ods.py",
        "20260922_0017_add_pmc_purchase_gate3_tables.py",
        "20260922_0014_create_after_sales_refund_items.py",
        "20260922_0015_add_after_sales_refund_loss_date.py",
        "20260922_0016_after_sales_refund_items_schema_repair.py",
        "20260922_0017_add_after_sales_refund_amount.py",
        "20260923_0018_merge_after_sales_pmc_heads.py",
        "20261006_0029_legacy_selected_mirror_tables.py",
        "20261007_0030_daily_sales_sem_ad_spend.py",
        "20261008_0031_order_profit_sem_ad_spend.py",
        "20261008_0032_order_profit_return_qty_refund_loss.py",
        "20261010_0033_add_wfs_low_price_surcharge.py",
        "20261013_0034_listing_wfs_first_stock.py",
        "20261014_0035_add_auth_rbac.py",
        "20261015_0036_wfs_cases.py",
        "20261016_0037_approval_workbench.py",
        "20261016_0038_rbac_v2.py",
        "20261016_0039_retire_legacy_rbac_permissions.py",
        "20261016_0040_restrict_default_data_scopes.py",
        "20261016_0041_wfs_rbac_actions.py",
        "20261017_0042_approval_rbac_backfill.py",
        "20261017_0043_purchase_board_listing_item_source.py",
        "20261019_0044_approval_flow.py",
        "20261019_0045_approval_scope.py",
        "20261019_0046_operation_logs.py",
        "20261020_0047_walmart_order_identity_guard.py",
        "20261019_0047_domestic_warehouse_ods.py",
        "20261019_0048_domestic_warehouse_dwd_and_permission.py",
        "20261020_0049_domestic_inbound_board.py",
        "20261020_0050_domestic_packing_approval.py",
        "20261021_0051_domestic_packing_lifecycle.py",
        "20261021_0052_domestic_packing_manual.py",
        "20261022_0053_domestic_packing_production_compat.py",
    } <= revisions

    rbac_revision = (
        BACKEND_ROOT / "alembic" / "versions" / "20261017_0042_approval_rbac_backfill.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "20261017_0042_rbac_backfill"' in rbac_revision
    assert '"source_account_refs_json"' in rbac_revision
    assert '"field:sales:order-profit:gross-profit"' in rbac_revision
    assert '"field:sales:order-profit:profit-margin"' in rbac_revision

    revision = (
        BACKEND_ROOT / "alembic" / "versions" / "20260910_0002_add_raw_lingxing_api.py"
    ).read_text(encoding="utf-8")
    assert revision.count('name=op.f("ck_raw_lingxing_api_api_path")') == 1
    assert '"ix_raw_lingxing_api_raw_hash"' in revision
    assert '"ix_raw_lingxing_api_object_type"' not in revision

    legacy_revision = (
        BACKEND_ROOT / "alembic" / "versions" / "20261006_0029_legacy_selected_mirror_tables.py"
    ).read_text(encoding="utf-8")
    assert "create schema if not exists legacy_mirror" in legacy_revision
    assert "legacy_mirror.biz_product_operation_log" in legacy_revision
    assert "legacy_mirror.event_wfs_fee_case" in legacy_revision
    assert "legacy_mirror.event_ops_action_log" in legacy_revision
    assert "legacy_mirror.raw_walmart_sem_csv" in legacy_revision
    assert "create table if not exists app_users" in legacy_revision


@pytest.mark.parametrize("migration_auth_value", [None, "false", "yes", "1", "on"])
def test_production_migration_requires_exact_migration_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    migration_auth_value: str | None,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SYNTHETIC_DATABASE_URL)
    if migration_auth_value is None:
        monkeypatch.delenv("PRODUCTION_MIGRATIONS_AUTHORIZED", raising=False)
    else:
        monkeypatch.setenv("PRODUCTION_MIGRATIONS_AUTHORIZED", migration_auth_value)

    with pytest.raises(
        SettingsError,
        match="^Production migrations require separate authorization$",
    ) as error:
        run_offline_env(monkeypatch)

    assert SYNTHETIC_DATABASE_URL not in str(error.value)
    captured = capsys.readouterr()
    assert SYNTHETIC_DATABASE_URL not in captured.out
    assert SYNTHETIC_DATABASE_URL not in captured.err


@pytest.mark.parametrize("migration_auth_value", ["true", "TRUE", "True"])
def test_production_migration_accepts_explicit_migration_gate(
    monkeypatch: pytest.MonkeyPatch,
    migration_auth_value: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("PRODUCTION_MIGRATIONS_AUTHORIZED", migration_auth_value)

    configured = run_offline_env(monkeypatch)

    assert configured["url"].render_as_string(hide_password=False) == SYNTHETIC_DATABASE_URL


@pytest.mark.parametrize(
    ("app_env", "url_variable"),
    [("dev", "DATABASE_URL"), ("staging", "DATABASE_URL"), ("test", "TEST_DATABASE_URL")],
)
def test_nonproduction_migration_behavior_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    url_variable: str,
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv(url_variable, SYNTHETIC_DATABASE_URL)
    monkeypatch.delenv("PRODUCTION_MIGRATIONS_AUTHORIZED", raising=False)

    configured = run_offline_env(monkeypatch)

    assert configured["url"].render_as_string(hide_password=False) == SYNTHETIC_DATABASE_URL
