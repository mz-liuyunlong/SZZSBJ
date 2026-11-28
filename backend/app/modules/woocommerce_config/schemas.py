from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, SecretStr, field_validator

_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".test", ".invalid")


def normalize_store_url(value: str) -> str:
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("store_url_invalid") from None

    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or port not in (None, 443)
    ):
        raise ValueError("store_url_must_be_https_origin")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("store_url_ip_literal_not_allowed")

    try:
        ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("store_url_host_invalid") from None

    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if (
        not ascii_host
        or "." not in ascii_host
        or re.fullmatch(rf"{label}(?:\.{label})+", ascii_host) is None
    ):
        raise ValueError("store_url_host_invalid")
    if any(ascii_host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES):
        raise ValueError("store_url_host_not_public")

    return urlunsplit(("https", ascii_host, "", "", ""))


class WooCommerceStoreCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    store_url: str = Field(min_length=9, max_length=255)
    consumer_key: SecretStr = Field(repr=False)
    consumer_secret: SecretStr = Field(repr=False)
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name_required")
        return normalized

    @field_validator("store_url")
    @classmethod
    def validate_store_url(cls, value: str) -> str:
        return normalize_store_url(value)

    @field_validator("consumer_key", "consumer_secret")
    @classmethod
    def normalize_secret(cls, value: SecretStr) -> SecretStr:
        normalized = value.get_secret_value().strip()
        if not normalized or len(normalized) > 256:
            raise ValueError("credential_invalid")
        return SecretStr(normalized)


class WooCommerceStoreUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    store_url: str = Field(min_length=9, max_length=255)
    consumer_key: SecretStr | None = Field(default=None, repr=False)
    consumer_secret: SecretStr | None = Field(default=None, repr=False)
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name_required")
        return normalized

    @field_validator("store_url")
    @classmethod
    def validate_store_url(cls, value: str) -> str:
        return normalize_store_url(value)

    @field_validator("consumer_key", "consumer_secret", mode="before")
    @classmethod
    def normalize_optional_secret(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        normalized = raw.strip()
        return SecretStr(normalized) if normalized else None

    @field_validator("consumer_key", "consumer_secret")
    @classmethod
    def validate_optional_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) > 256:
            raise ValueError("credential_invalid")
        return value


class WooCommerceStoreRead(BaseModel):
    id: str
    name: str
    store_url: str
    enabled: bool
    consumer_key_configured: bool
    consumer_secret_configured: bool
    last_test_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_code: str | None = None
    updated_at: datetime


class WooCommerceTestResult(BaseModel):
    ok: bool
    code: str
