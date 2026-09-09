from enum import StrEnum
from functools import lru_cache
from typing import Self

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

    @model_validator(mode="after")
    def require_environment_url(self) -> Self:
        if self.app_env is AppEnvironment.TEST:
            if self.test_database_url is None:
                raise ValueError("TEST_DATABASE_URL is required when APP_ENV=test")
        elif self.database_url is None:
            raise ValueError("DATABASE_URL is required outside APP_ENV=test")
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
        raise SettingsError("Database settings are missing or invalid") from None


def get_database_url(settings: Settings | None = None) -> URL:
    return (settings or get_settings()).sqlalchemy_url()


def get_test_database_url(settings: Settings) -> URL:
    if settings.app_env is not AppEnvironment.TEST:
        raise SettingsError("Isolated database tests require APP_ENV=test")
    return settings.sqlalchemy_url()
