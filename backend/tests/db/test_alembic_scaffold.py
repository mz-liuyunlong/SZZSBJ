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
    assert script.get_heads() == ["20260912_0006"]
    revisions = {path.name for path in (BACKEND_ROOT / "alembic" / "versions").glob("*.py")}
    assert {
        "20260912_0003_add_integration_governance.py",
        "20260912_0004_add_integration_ods.py",
        "20260912_0005_add_lingxing_sku_dwd.py",
        "20260912_0006_add_sku_dws.py",
    } <= revisions

    revision = (
        BACKEND_ROOT / "alembic" / "versions" / "20260910_0002_add_raw_lingxing_api.py"
    ).read_text()
    assert revision.count('name=op.f("ck_raw_lingxing_api_api_path")') == 1
    assert '"ix_raw_lingxing_api_raw_hash"' in revision
    assert '"ix_raw_lingxing_api_object_type"' not in revision


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
