"""Retry/recovery policy shared by media workers and reconciliation."""

from __future__ import annotations

from datetime import datetime

RETRYABLE_MEDIA_ERROR_CODES = frozenset(
    {
        "SOURCE_DNS_FAILED",
        "SOURCE_TIMEOUT",
        "SOURCE_NETWORK_ERROR",
        "SOURCE_RATE_LIMITED",
        "SOURCE_UNAVAILABLE",
        "MEDIA_STORAGE_WRITE_FAILED",
    }
)

DEFAULT_RETRY_BASE_SECONDS = 30
MAX_RETRY_DELAY_SECONDS = 900


def retry_countdown_seconds(retry_count: int) -> int:
    """Return capped exponential delay after an already-recorded failed attempt."""
    normalized = max(1, retry_count)
    delay = DEFAULT_RETRY_BASE_SECONDS * (1 << (normalized - 1))
    return min(delay, MAX_RETRY_DELAY_SECONDS)


def processing_is_stale(
    last_attempt_at: datetime | None,
    *,
    now: datetime,
    stale_seconds: int,
) -> bool:
    """Treat missing/old processing timestamps as recoverable worker abandonment."""
    if last_attempt_at is None:
        return True
    return (now - last_attempt_at).total_seconds() >= stale_seconds
