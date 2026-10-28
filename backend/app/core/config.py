from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final, Self
from urllib.parse import urlsplit

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError

PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN_MIN_LENGTH: Final = 32
WALMART_MONITOR_INGEST_TOKEN_MIN_LENGTH: Final = 32
WALMART_MONITOR_TARGETS_TOKEN_MIN_LENGTH: Final = 32


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
    listing_evaluation_preview_enabled: bool = Field(
        default=False, validation_alias="LISTING_EVALUATION_PREVIEW_ENABLED"
    )
    listing_evaluation_scheduler_enabled: bool = Field(
        default=False, validation_alias="LISTING_EVALUATION_SCHEDULER_ENABLED"
    )
    listing_evaluation_publish_enabled: bool = Field(
        default=False, validation_alias="LISTING_EVALUATION_PUBLISH_ENABLED"
    )
    product_management_preview_auth_enabled: bool = Field(
        default=False,
        validation_alias="PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED",
    )
    product_management_preview_auth_token: SecretStr | None = Field(
        default=None,
        validation_alias="PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN",
    )
    product_management_preview_source_account_refs: str | None = Field(
        default=None,
        repr=False,
        validation_alias="PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS",
    )
    walmart_monitor_ingest_token: SecretStr | None = Field(
        default=None,
        validation_alias="WALMART_MONITOR_INGEST_TOKEN",
    )
    walmart_monitor_targets_token: SecretStr | None = Field(
        default=None,
        validation_alias="WALMART_MONITOR_TARGETS_TOKEN",
    )
    lingxing_base_url: str | None = Field(default=None, validation_alias="LINGXING_BASE_URL")
    lingxing_app_id: str | None = Field(default=None, validation_alias="LINGXING_APP_ID")
    lingxing_app_secret: SecretStr | None = Field(
        default=None,
        validation_alias="LINGXING_APP_SECRET",
    )
    pmc_domestic_passcode_sha256: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias="PMC_DOMESTIC_PASSCODE_SHA256",
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
        default=10_000,
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
    lingxing_enable_batch_product_info_requests: bool = Field(
        default=False,
        validation_alias="LINGXING_ENABLE_BATCH_PRODUCT_INFO_REQUESTS",
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
    data_pages_real_sync_authorized: bool = Field(
        default=False,
        validation_alias="DATA_PAGES_REAL_SYNC_AUTHORIZED",
    )
    productlist_real_sync_authorized: bool = Field(
        default=False,
        validation_alias="PRODUCTLIST_REAL_SYNC_AUTHORIZED",
    )
    wfs_auto_detect_enabled: bool = Field(
        default=False,
        validation_alias="WFS_AUTO_DETECT_ENABLED",
    )
    wfs_auto_case_create_enabled: bool = Field(
        default=False,
        validation_alias="WFS_AUTO_CASE_CREATE_ENABLED",
    )
    wfs_settlement_scope_verified: bool = Field(
        default=False,
        validation_alias="WFS_SETTLEMENT_SCOPE_VERIFIED",
    )
    wfs_detect_lookback_days: int = Field(
        default=60,
        ge=1,
        le=366,
        validation_alias="WFS_DETECT_LOOKBACK_DAYS",
    )
    wfs_detect_settlement_lag_days: int = Field(
        default=2,
        ge=0,
        le=31,
        validation_alias="WFS_DETECT_SETTLEMENT_LAG_DAYS",
    )
    wfs_detect_min_sample_units: int = Field(
        default=10,
        ge=1,
        le=10000,
        validation_alias="WFS_DETECT_MIN_SAMPLE_UNITS",
    )
    wfs_detect_max_stale_days: int = Field(
        default=14,
        ge=1,
        le=366,
        validation_alias="WFS_DETECT_MAX_STALE_DAYS",
    )
    lingxing_allow_full_sync: bool = Field(
        default=False,
        validation_alias="LINGXING_ALLOW_FULL_SYNC",
    )
    lingxing_productlist_raw_run_dir: Path | None = Field(
        default=None,
        validation_alias="LINGXING_PRODUCTLIST_RAW_RUN_DIR",
    )
    media_cache_enabled: bool = Field(
        default=False,
        validation_alias="MEDIA_CACHE_ENABLED",
    )
    media_storage_root: Path | None = Field(
        default=None,
        validation_alias="MEDIA_STORAGE_ROOT",
    )
    media_signing_secret: SecretStr | None = Field(
        default=None,
        validation_alias="MEDIA_SIGNING_SECRET",
    )
    media_allowed_source_hosts: str | None = Field(
        default=None,
        validation_alias="MEDIA_ALLOWED_SOURCE_HOSTS",
    )
    media_download_timeout_ms: int = Field(
        default=8_000,
        ge=500,
        le=30_000,
        validation_alias="MEDIA_DOWNLOAD_TIMEOUT_MS",
    )
    media_max_source_bytes: int = Field(
        default=10_485_760,
        ge=65_536,
        le=52_428_800,
        validation_alias="MEDIA_MAX_SOURCE_BYTES",
    )
    media_max_source_pixels: int = Field(
        default=40_000_000,
        ge=1_000_000,
        le=100_000_000,
        validation_alias="MEDIA_MAX_SOURCE_PIXELS",
    )
    media_signed_url_ttl_seconds: int = Field(
        default=3_600,
        ge=60,
        le=86_400,
        validation_alias="MEDIA_SIGNED_URL_TTL_SECONDS",
    )
    media_processing_stale_seconds: int = Field(
        default=900,
        ge=60,
        le=86_400,
        validation_alias="MEDIA_PROCESSING_STALE_SECONDS",
    )
    media_max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        validation_alias="MEDIA_MAX_ATTEMPTS",
    )
    feishu_bot_enabled: bool = Field(
        default=False,
        validation_alias="FEISHU_BOT_ENABLED",
    )
    feishu_app_id: str | None = Field(default=None, validation_alias="FEISHU_APP_ID")
    feishu_app_secret: SecretStr | None = Field(
        default=None,
        validation_alias="FEISHU_APP_SECRET",
    )
    feishu_base_url: str = Field(
        default="https://open.feishu.cn",
        validation_alias="FEISHU_BASE_URL",
    )
    feishu_request_timeout_ms: int = Field(
        default=5_000,
        ge=100,
        le=30_000,
        validation_alias="FEISHU_REQUEST_TIMEOUT_MS",
    )
    feishu_password_setup_base_url: str = Field(
        default="http://localhost:5173/#/password/setup",
        validation_alias="FEISHU_PASSWORD_SETUP_BASE_URL",
    )
    feishu_offboarding_notice_open_id: str | None = Field(
        default=None, validation_alias="FEISHU_OFFBOARDING_NOTICE_OPEN_ID"
    )
    feishu_offboarding_notice_user_id: str | None = Field(
        default=None, validation_alias="FEISHU_OFFBOARDING_NOTICE_USER_ID"
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

    @field_validator("walmart_monitor_targets_token", mode="before")
    @classmethod
    def validate_walmart_monitor_targets_token(cls, value: object) -> object:
        if value in (None, ""):
            return None
        if (
            not isinstance(value, str)
            or len(value) < WALMART_MONITOR_TARGETS_TOKEN_MIN_LENGTH
            or not value.isascii()
        ):
            raise SettingsError("Walmart monitor target source settings are invalid")
        return value

    @field_validator("product_management_preview_auth_token", mode="before")
    @classmethod
    def validate_product_management_preview_auth_token(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        if not info.data.get("product_management_preview_auth_enabled") or value in (None, ""):
            return value
        if (
            not isinstance(value, str)
            or len(value) < PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN_MIN_LENGTH
            or not value.isascii()
        ):
            raise SettingsError("Product Management preview auth settings are invalid")
        return value

    @field_validator("walmart_monitor_ingest_token", mode="before")
    @classmethod
    def validate_walmart_monitor_ingest_token(cls, value: object) -> object:
        if value in (None, ""):
            return None
        if (
            not isinstance(value, str)
            or len(value) < WALMART_MONITOR_INGEST_TOKEN_MIN_LENGTH
            or not value.isascii()
        ):
            raise SettingsError("Walmart monitor ingestion settings are invalid")
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

    @field_validator("feishu_base_url")
    @classmethod
    def validate_feishu_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError:
            raise ValueError("FEISHU_BASE_URL must be a credential-free HTTPS origin") from None
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FEISHU_BASE_URL must be a credential-free HTTPS origin")
        return value.rstrip("/")

    @field_validator("feishu_password_setup_base_url")
    @classmethod
    def validate_feishu_password_setup_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError:
            raise ValueError(
                "FEISHU_PASSWORD_SETUP_BASE_URL must be a valid frontend URL"
            ) from None
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("FEISHU_PASSWORD_SETUP_BASE_URL must be a valid frontend URL")
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
        product_info_execute_mode = (
            self.app_env is AppEnvironment.PRODUCTION
            and self.lingxing_enable_token_requests
            and self.lingxing_enable_real_calls
            and self.lingxing_enable_batch_product_info_requests
            and not self.lingxing_dry_run
            and self.lingxing_allow_raw_write
            and self.lingxing_allow_structured_write
            and not self.lingxing_allow_full_sync
        )
        data_pages_execute_mode = (
            self.app_env is not AppEnvironment.TEST
            and self.data_pages_real_sync_authorized
            and self.lingxing_enable_token_requests
            and self.lingxing_enable_real_calls
            and not self.lingxing_dry_run
            and self.lingxing_allow_raw_write
            and self.lingxing_allow_structured_write
            and not self.lingxing_allow_full_sync
        )
        productlist_execute_mode = (
            self.app_env is not AppEnvironment.TEST
            and self.productlist_real_sync_authorized
            and self.lingxing_enable_token_requests
            and self.lingxing_enable_real_calls
            and not self.lingxing_dry_run
            and self.lingxing_allow_raw_write
            and self.lingxing_allow_structured_write
            and not self.lingxing_allow_full_sync
        )
        if self.lingxing_enable_batch_product_info_requests and not product_info_execute_mode:
            raise ValueError("Lingxing ProductInfo execution settings are not authorized")
        if self.lingxing_allow_structured_write and not (
            product_info_execute_mode or data_pages_execute_mode or productlist_execute_mode
        ):
            raise ValueError("Lingxing structured write execution settings are not authorized")
        if self.productlist_real_sync_authorized and not productlist_execute_mode:
            raise ValueError("Lingxing ProductList execution settings are not authorized")
        if self.lingxing_enable_token_requests and (
            self.lingxing_base_url is None
            or not self.lingxing_app_id
            or self.lingxing_app_secret is None
        ):
            raise ValueError("Lingxing token request settings are missing or invalid")
        if self.lingxing_allow_full_sync:
            raise ValueError("Lingxing full sync is not approved")
        if self.feishu_bot_enabled and (
            not self.feishu_app_id
            or self.feishu_app_secret is None
            or not self.feishu_password_setup_base_url
        ):
            raise ValueError("Feishu bot settings are missing or invalid")
        if (
            self.app_env is AppEnvironment.PRODUCTION
            and self.feishu_bot_enabled
            and "localhost" in self.feishu_password_setup_base_url
        ):
            raise ValueError("FEISHU_PASSWORD_SETUP_BASE_URL must be configured for production")
        if self.media_cache_enabled:
            secret = self.media_signing_secret
            hosts = self.media_allowed_source_host_set
            if (
                self.media_storage_root is None
                or not self.media_storage_root.is_absolute()
                or secret is None
                or len(secret.get_secret_value()) < 32
                or not hosts
            ):
                raise ValueError("Media cache settings are missing or invalid")
        return self

    @property
    def media_allowed_source_host_set(self) -> frozenset[str]:
        value = self.media_allowed_source_hosts
        if value is None:
            return frozenset()
        hosts = {part.strip().lower().rstrip(".") for part in value.split(",") if part.strip()}
        if any(
            "://" in host or "/" in host or ":" in host or host.startswith(".") for host in hosts
        ):
            raise ValueError("MEDIA_ALLOWED_SOURCE_HOSTS must contain hostnames only")
        return frozenset(hosts)

    @property
    def product_management_preview_auth_configured(self) -> bool:
        token = self.product_management_preview_auth_token
        return (
            self.product_management_preview_auth_enabled
            and token is not None
            and len(token.get_secret_value()) >= PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN_MIN_LENGTH
        )

    @property
    def product_management_preview_source_account_ref_set(self) -> frozenset[str]:
        value = self.product_management_preview_source_account_refs
        if value is None:
            return frozenset()
        return frozenset(part.strip() for part in value.split(",") if part.strip())

    @property
    def walmart_monitor_ingest_configured(self) -> bool:
        token = self.walmart_monitor_ingest_token
        return token is not None and len(token.get_secret_value()) >= (
            WALMART_MONITOR_INGEST_TOKEN_MIN_LENGTH
        )

    @property
    def walmart_monitor_targets_configured(self) -> bool:
        token = self.walmart_monitor_targets_token
        return token is not None and len(token.get_secret_value()) >= (
            WALMART_MONITOR_TARGETS_TOKEN_MIN_LENGTH
        )

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
