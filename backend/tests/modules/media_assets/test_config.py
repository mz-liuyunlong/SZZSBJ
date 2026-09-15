from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import AppEnvironment, Settings


def base_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": AppEnvironment.LOCAL,
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/app",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_media_cache_is_disabled_by_default() -> None:
    settings = base_settings()

    assert settings.media_cache_enabled is False
    assert settings.media_allowed_source_host_set == frozenset()
    assert settings.media_processing_stale_seconds == 900


def test_enabled_media_cache_requires_complete_safe_configuration() -> None:
    with pytest.raises(ValidationError):
        base_settings(MEDIA_CACHE_ENABLED=True)


def test_enabled_media_cache_accepts_absolute_storage_and_host_allowlist(tmp_path: Path) -> None:
    settings = base_settings(
        MEDIA_CACHE_ENABLED=True,
        MEDIA_STORAGE_ROOT=tmp_path.resolve(),
        MEDIA_SIGNING_SECRET=SecretStr("x" * 32),
        MEDIA_ALLOWED_SOURCE_HOSTS="images.example.com,cdn.example.com",
    )

    assert settings.media_storage_root == tmp_path.resolve()
    assert settings.media_allowed_source_host_set == frozenset(
        {"images.example.com", "cdn.example.com"}
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://images.example.com",
        "images.example.com/path",
        "images.example.com:443",
        ".example.com",
    ],
)
def test_media_host_allowlist_rejects_non_hostname_values(tmp_path: Path, value: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        base_settings(
            MEDIA_CACHE_ENABLED=True,
            MEDIA_STORAGE_ROOT=tmp_path.resolve(),
            MEDIA_SIGNING_SECRET=SecretStr("x" * 32),
            MEDIA_ALLOWED_SOURCE_HOSTS=value,
        )
