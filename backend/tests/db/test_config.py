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
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "LINGXING_ENABLE_REAL_CALLS",
        "LINGXING_ALLOW_STRUCTURED_WRITE",
        "LINGXING_ALLOW_FULL_SYNC",
    ):
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


def test_lingxing_settings_default_to_dry_run_and_deny_dangerous_actions() -> None:
    settings = _settings("test", test_database_url=SYNTHETIC_DATABASE_URL)

    assert settings.lingxing_enable_real_calls is False
    assert settings.lingxing_dry_run is True
    assert settings.lingxing_allow_raw_write is False
    assert settings.lingxing_allow_structured_write is False
    assert settings.lingxing_allow_full_sync is False
    assert settings.lingxing_sample_page_size == 3
    assert settings.lingxing_max_sample_pages == 1
    assert settings.lingxing_max_response_bytes == 1_048_576


@pytest.mark.parametrize(
    "name",
    ["LINGXING_ALLOW_STRUCTURED_WRITE", "LINGXING_ALLOW_FULL_SYNC"],
)
def test_lingxing_settings_reject_unapproved_write_modes(name: str) -> None:
    values = {
        "APP_ENV": "test",
        "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
        name: True,
    }

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_lingxing_base_url_rejects_credentials_and_masks_secret_fields() -> None:
    marker = "credential-fixture"
    values = {
        "APP_ENV": "test",
        "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
        "LINGXING_BASE_URL": f"https://user:{marker}@provider.invalid",
        "LINGXING_APP_SECRET": marker,
        "LINGXING_ACCESS_TOKEN": marker,
    }

    with pytest.raises(ValidationError) as error:
        Settings.model_validate(values)

    assert marker not in str(error.value)
