from enum import StrEnum
from functools import lru_cache
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError


class AppEnvironment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class SettingsError(RuntimeError):
    """Safe configuration error that never includes a connection URL."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    app_env: AppEnvironment = Field(validation_alias="APP_ENV")
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    test_database_url: SecretStr | None = Field(
        default=None,
        validation_alias="TEST_DATABASE_URL",
    )
    lingxing_base_url: str | None = Field(default=None, validation_alias="LINGXING_BASE_URL")
    lingxing_app_id: str | None = Field(default=None, validation_alias="LINGXING_APP_ID")
    lingxing_app_secret: SecretStr | None = Field(
        default=None,
        validation_alias="LINGXING_APP_SECRET",
    )
    lingxing_access_token: SecretStr | None = Field(
        default=None,
        validation_alias="LINGXING_ACCESS_TOKEN",
    )
    lingxing_enable_token_requests: bool = Field(
        default=False,
        validation_alias="LINGXING_ENABLE_TOKEN_REQUESTS",
    )
    lingxing_token_refresh_safety_seconds: int = Field(
        default=600,
        ge=1,
        validation_alias="LINGXING_TOKEN_REFRESH_SAFETY_SECONDS",
    )
    lingxing_token_refresh_short_ttl_ratio: float = Field(
        default=0.2,
        gt=0,
        lt=1,
        validation_alias="LINGXING_TOKEN_REFRESH_SHORT_TTL_RATIO",
    )
    lingxing_token_request_timeout_ms: int = Field(
        default=5_000,
        ge=100,
        validation_alias="LINGXING_TOKEN_REQUEST_TIMEOUT_MS",
    )
    lingxing_token_max_attempts: int = Field(
        default=2,
        ge=1,
        le=2,
        validation_alias="LINGXING_TOKEN_MAX_ATTEMPTS",
    )
    lingxing_timeout_ms: int = Field(
        default=5_000,
        ge=100,
        validation_alias="LINGXING_TIMEOUT_MS",
    )
    lingxing_sample_page_size: int = Field(
        default=3,
        ge=1,
        le=3,
        validation_alias="LINGXING_SAMPLE_PAGE_SIZE",
    )
    lingxing_max_sample_pages: int = Field(
        default=1,
        ge=1,
        le=1,
        validation_alias="LINGXING_MAX_SAMPLE_PAGES",
    )
    lingxing_max_response_bytes: int = Field(
        default=1_048_576,
        ge=1,
        validation_alias="LINGXING_MAX_RESPONSE_BYTES",
    )
    lingxing_enable_real_calls: bool = Field(
        default=False,
        validation_alias="LINGXING_ENABLE_REAL_CALLS",
    )
    lingxing_save_raw: bool = Field(default=True, validation_alias="LINGXING_SAVE_RAW")
    lingxing_dry_run: bool = Field(default=True, validation_alias="LINGXING_DRY_RUN")
    lingxing_allow_raw_write: bool = Field(
        default=False,
        validation_alias="LINGXING_ALLOW_RAW_WRITE",
    )
    lingxing_allow_structured_write: bool = Field(
        default=False,
        validation_alias="LINGXING_ALLOW_STRUCTURED_WRITE",
    )
    lingxing_allow_full_sync: bool = Field(
        default=False,
        validation_alias="LINGXING_ALLOW_FULL_SYNC",
    )

    @field_validator("database_url", "test_database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("database URL must be a valid PostgreSQL psycopg URL") from None
        if url.drivername != "postgresql+psycopg":
            raise ValueError("database URL must use PostgreSQL with the psycopg driver")
        return value

    @field_validator("lingxing_base_url")
    @classmethod
    def validate_lingxing_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError:
            raise ValueError("LINGXING_BASE_URL must be a credential-free HTTPS origin") from None
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LINGXING_BASE_URL must be a credential-free HTTPS origin")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_environment_url(self) -> Self:
        if self.app_env is AppEnvironment.TEST:
            if self.test_database_url is None:
                raise ValueError("TEST_DATABASE_URL is required when APP_ENV=test")
        elif self.database_url is None:
            raise ValueError("DATABASE_URL is required outside APP_ENV=test")
        if self.lingxing_enable_real_calls and self.lingxing_base_url is None:
            raise ValueError("LINGXING_BASE_URL is required when real calls are enabled")
        if self.lingxing_enable_token_requests and (
            self.lingxing_base_url is None
            or not self.lingxing_app_id
            or self.lingxing_app_secret is None
        ):
            raise ValueError("Lingxing token request settings are missing or invalid")
        if self.lingxing_allow_structured_write:
            raise ValueError("Lingxing structured writes are not approved")
        if self.lingxing_allow_full_sync:
            raise ValueError("Lingxing full sync is not approved")
        return self

    def sqlalchemy_url(self) -> URL:
        value = self.test_database_url if self.app_env is AppEnvironment.TEST else self.database_url
        if value is None:
            raise SettingsError("Database settings are missing or invalid")
        return make_url(value.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # Values come from environment sources.
    except ValidationError:
        raise SettingsError("Application settings are missing or invalid") from None


def get_database_url(settings: Settings | None = None) -> URL:
    return (settings or get_settings()).sqlalchemy_url()


def get_test_database_url(settings: Settings) -> URL:
    if settings.app_env is not AppEnvironment.TEST:
        raise SettingsError("Isolated database tests require APP_ENV=test")
    return settings.sqlalchemy_url()
