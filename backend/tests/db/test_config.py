import pytest
from pydantic import ValidationError

from app.core.config import (
    AppEnvironment,
    Settings,
    SettingsError,
    get_database_url,
    get_settings,
    get_test_database_url,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"


def _settings(
    app_env: str,
    *,
    database_url: str | None = None,
    test_database_url: str | None = None,
) -> Settings:
    values: dict[str, str] = {"APP_ENV": app_env}
    if database_url is not None:
        values["DATABASE_URL"] = database_url
    if test_database_url is not None:
        values["TEST_DATABASE_URL"] = test_database_url
    return Settings.model_validate(values)


def test_local_settings_use_postgresql_psycopg_and_mask_url() -> None:
    settings = _settings("local", database_url=SYNTHETIC_DATABASE_URL)

    assert settings.app_env is AppEnvironment.LOCAL
    assert get_database_url(settings).drivername == "postgresql+psycopg"
    assert SYNTHETIC_DATABASE_URL not in repr(settings)


def test_test_settings_never_fall_back_to_database_url() -> None:
    with pytest.raises(ValidationError) as error:
        _settings("test", database_url=SYNTHETIC_DATABASE_URL)

    assert "TEST_DATABASE_URL is required" in str(error.value)
    assert SYNTHETIC_DATABASE_URL not in str(error.value)

    settings = _settings("test", test_database_url=SYNTHETIC_DATABASE_URL)
    assert get_database_url(settings) == get_test_database_url(settings)


def test_test_database_url_rejects_non_test_environment() -> None:
    settings = _settings("production", database_url=SYNTHETIC_DATABASE_URL)

    with pytest.raises(SettingsError, match="APP_ENV=test"):
        get_test_database_url(settings)


def test_environment_loading_fails_closed_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("APP_ENV", "DATABASE_URL", "TEST_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    with pytest.raises(SettingsError, match="missing or invalid"):
        get_settings()

    get_settings.cache_clear()


def test_environment_loading_rejects_non_postgresql_url_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_url = "sqlite:///synthetic.db"
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", invalid_url)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(SettingsError, match="missing or invalid") as error:
        get_settings()

    assert invalid_url not in str(error.value)
    get_settings.cache_clear()
