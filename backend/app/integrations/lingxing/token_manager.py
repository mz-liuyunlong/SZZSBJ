from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import sleep
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

from app.core.config import Settings

GET_TOKEN_PATH = "/api/auth-server/oauth/access-token"
REFRESH_TOKEN_PATH = "/api/auth-server/oauth/refresh"
_REFRESH_FALLBACK_CODES = frozenset({2001003, 2001008, 2001009})
_RETRYABLE_PROVIDER_CODES = frozenset({3001008})
_RETRY_BACKOFF_SECONDS = 0.05


class LingxingTokenError(RuntimeError):
    """Stable Token Manager error without provider payload or credentials."""

    def __init__(
        self,
        category: str,
        *,
        provider_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.provider_code = provider_code
        self.retryable = retryable


class _TokenData(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    access_token: SecretStr
    refresh_token: SecretStr
    expires_in: int

    @field_validator("access_token", "refresh_token")
    @classmethod
    def require_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("token is missing")
        return value

    @field_validator("expires_in", mode="before")
    @classmethod
    def parse_expires_in(cls, value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("expires_in must be a positive integer")
        if isinstance(value, str):
            value = value.strip()
            if not value.isdecimal():
                raise ValueError("expires_in must be a positive integer")
            value = int(value)
        if not isinstance(value, int) or value <= 0:
            raise ValueError("expires_in must be a positive integer")
        return value


@dataclass(frozen=True, repr=False)
class _TokenPair:
    access_token: SecretStr
    refresh_token: SecretStr
    expires_in: int


@dataclass(frozen=True, repr=False)
class LingxingTokenSnapshot:
    access_token: SecretStr
    refresh_token: SecretStr
    expires_in: int
    acquired_at: datetime
    expires_at: datetime
    refresh_after: datetime
    generation: int

    def __repr__(self) -> str:
        return (
            "LingxingTokenSnapshot("
            f"expires_in={self.expires_in}, expires_at={self.expires_at!r}, "
            f"refresh_after={self.refresh_after!r}, generation={self.generation})"
        )


def _provider_code(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, str):
        value = value.strip()
        if not value.isdecimal():
            raise ValueError
        value = int(value)
    if not isinstance(value, int):
        raise ValueError
    return value


def _expires_in_duration(expires_in: int) -> timedelta:
    # Official examples imply seconds; controlled validation must confirm the unit.
    return timedelta(seconds=expires_in)


class LingxingTokenClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if settings.lingxing_base_url is None:
            raise LingxingTokenError("TOKEN_CONFIGURATION_ERROR")
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.lingxing_base_url,
            timeout=settings.lingxing_token_request_timeout_ms / 1_000,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get_token(self) -> _TokenPair:
        app_id, app_secret = self._credentials()
        return self._post(
            GET_TOKEN_PATH,
            {
                "appId": (None, app_id),
                "appSecret": (None, app_secret.get_secret_value()),
            },
        )

    def refresh_token(self, refresh_token: SecretStr) -> _TokenPair:
        app_id, _ = self._credentials()
        return self._post(
            REFRESH_TOKEN_PATH,
            {
                "appId": (None, app_id),
                "refreshToken": (None, refresh_token.get_secret_value()),
            },
        )

    def _credentials(self) -> tuple[str, SecretStr]:
        if not self._settings.lingxing_enable_token_requests:
            raise LingxingTokenError("TOKEN_REQUESTS_DISABLED")
        if not self._settings.lingxing_app_id or self._settings.lingxing_app_secret is None:
            raise LingxingTokenError("TOKEN_CONFIGURATION_ERROR")
        return self._settings.lingxing_app_id, self._settings.lingxing_app_secret

    def _post(
        self,
        path: str,
        fields: dict[str, tuple[None, str]],
    ) -> _TokenPair:
        try:
            response = self._client.post(path, files=fields)
        except httpx.HTTPError:
            raise LingxingTokenError("TOKEN_TRANSPORT_ERROR", retryable=True) from None
        if len(response.content) > self._settings.lingxing_max_response_bytes:
            raise LingxingTokenError("TOKEN_RESPONSE_TOO_LARGE")
        if not response.is_success:
            raise LingxingTokenError(
                "TOKEN_HTTP_ERROR",
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        try:
            payload: Any = response.json()
            if not isinstance(payload, dict):
                raise ValueError
        except (TypeError, ValueError):
            raise LingxingTokenError("TOKEN_RESPONSE_INVALID") from None
        try:
            code = _provider_code(payload.get("code"))
        except ValueError:
            raise LingxingTokenError("TOKEN_PROVIDER_ERROR") from None
        if code != 200:
            raise LingxingTokenError(
                "TOKEN_PROVIDER_ERROR",
                provider_code=code,
                retryable=code in _RETRYABLE_PROVIDER_CODES,
            )
        try:
            data = _TokenData.model_validate(payload.get("data"))
        except ValidationError:
            raise LingxingTokenError("TOKEN_RESPONSE_INVALID") from None
        return _TokenPair(
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            expires_in=data.expires_in,
        )


class LingxingTokenManager:
    def __init__(
        self,
        client: LingxingTokenClient,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._client = client
        self._settings = settings
        self._clock = clock
        self._sleeper = sleeper
        self._lock = Lock()
        self._snapshot: LingxingTokenSnapshot | None = None
        self._generation = 0
        self._consumed_refresh_generation: int | None = None

    def get_access_token(self) -> SecretStr:
        current = self._snapshot
        if current is not None and self._now() < current.refresh_after:
            return current.access_token
        with self._lock:
            current = self._snapshot
            if current is not None and self._now() < current.refresh_after:
                return current.access_token
            return self._renew_locked(use_refresh=current is not None).access_token

    def refresh_access_token(self) -> SecretStr:
        observed = self._snapshot
        with self._lock:
            current = self._snapshot
            if current is not None and (
                observed is None or current.generation != observed.generation
            ):
                return current.access_token
            return self._renew_locked(use_refresh=current is not None).access_token

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        try:
            normalized = _provider_code(provider_code)
        except ValueError:
            raise LingxingTokenError("TOKEN_ERROR_NOT_RECOVERABLE") from None
        if normalized != 2001003:
            raise LingxingTokenError(
                "TOKEN_ERROR_NOT_RECOVERABLE",
                provider_code=normalized,
            )
        return self.refresh_access_token()

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None

    def _renew_locked(self, *, use_refresh: bool) -> LingxingTokenSnapshot:
        current = self._snapshot
        if (
            use_refresh
            and current is not None
            and self._consumed_refresh_generation == current.generation
        ):
            use_refresh = False
        for attempt in range(1, self._settings.lingxing_token_max_attempts + 1):
            try:
                if use_refresh and current is not None:
                    # A refresh token is single-use once its request starts, even if the
                    # response is lost or invalid. Never submit this generation again.
                    self._consumed_refresh_generation = current.generation
                    pair = self._client.refresh_token(current.refresh_token)
                else:
                    pair = self._client.get_token()
            except LingxingTokenError as error:
                if attempt >= self._settings.lingxing_token_max_attempts:
                    raise
                if use_refresh and (
                    error.provider_code in _REFRESH_FALLBACK_CODES or error.retryable
                ):
                    use_refresh = False
                elif not use_refresh and error.retryable:
                    pass
                else:
                    raise
                self._sleeper(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            return self._install(pair)
        raise LingxingTokenError("TOKEN_ATTEMPTS_EXHAUSTED")

    def _install(self, pair: _TokenPair) -> LingxingTokenSnapshot:
        acquired_at = self._now()
        try:
            expires_at = acquired_at + _expires_in_duration(pair.expires_in)
        except OverflowError:
            raise LingxingTokenError("TOKEN_RESPONSE_INVALID") from None
        safety_seconds = self._settings.lingxing_token_refresh_safety_seconds
        early_seconds = (
            safety_seconds
            if pair.expires_in >= safety_seconds
            else pair.expires_in * self._settings.lingxing_token_refresh_short_ttl_ratio
        )
        self._generation += 1
        snapshot = LingxingTokenSnapshot(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
            acquired_at=acquired_at,
            expires_at=expires_at,
            refresh_after=expires_at - timedelta(seconds=early_seconds),
            generation=self._generation,
        )
        self._snapshot = snapshot
        return snapshot

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise LingxingTokenError("TOKEN_CLOCK_INVALID")
        return value.astimezone(UTC)
