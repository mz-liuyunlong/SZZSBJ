"""Only Lingxing transport/auth settings: CSV export has no DATABASE_URL dependency."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LingxingFileSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )
    lingxing_base_url: str = Field(
        default="https://openapi.lingxing.com", validation_alias="LINGXING_BASE_URL"
    )
    lingxing_app_id: str = Field(validation_alias="LINGXING_APP_ID")
    lingxing_app_secret: SecretStr = Field(validation_alias="LINGXING_APP_SECRET")
    lingxing_enable_real_calls: bool = Field(
        default=False, validation_alias="LINGXING_ENABLE_REAL_CALLS"
    )
    lingxing_enable_token_requests: bool = Field(
        default=False, validation_alias="LINGXING_ENABLE_TOKEN_REQUESTS"
    )
    lingxing_timeout_ms: int = Field(default=60000, ge=100, validation_alias="LINGXING_TIMEOUT_MS")
    lingxing_max_response_bytes: int = Field(
        default=8000000, ge=1, validation_alias="LINGXING_MAX_RESPONSE_BYTES"
    )
    lingxing_token_request_timeout_ms: int = Field(
        default=10000, ge=100, validation_alias="LINGXING_TOKEN_REQUEST_TIMEOUT_MS"
    )
    lingxing_token_max_attempts: int = Field(
        default=2, ge=1, le=2, validation_alias="LINGXING_TOKEN_MAX_ATTEMPTS"
    )
    lingxing_token_refresh_safety_seconds: int = Field(
        default=600, ge=1, validation_alias="LINGXING_TOKEN_REFRESH_SAFETY_SECONDS"
    )
    lingxing_token_refresh_short_ttl_ratio: float = Field(
        default=0.2, gt=0, lt=1, validation_alias="LINGXING_TOKEN_REFRESH_SHORT_TTL_RATIO"
    )

    @field_validator("lingxing_base_url")
    @classmethod
    def official_origin_only(cls, value: str) -> str:
        if value.rstrip("/") != "https://openapi.lingxing.com":
            raise ValueError("CSV collection requires the official Lingxing origin")
        return value.rstrip("/")

    @field_validator("lingxing_app_id", "lingxing_app_secret")
    @classmethod
    def nonempty(cls, value):
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw or raw != raw.strip():
            raise ValueError("Lingxing credential missing")
        return value
