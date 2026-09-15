from datetime import UTC, datetime, timedelta

from app.modules.media_assets.retry_policy import (
    RETRYABLE_MEDIA_ERROR_CODES,
    processing_is_stale,
    retry_countdown_seconds,
)


def test_retry_policy_has_only_transient_source_and_storage_errors() -> None:
    assert "SOURCE_RATE_LIMITED" in RETRYABLE_MEDIA_ERROR_CODES
    assert "SOURCE_TIMEOUT" in RETRYABLE_MEDIA_ERROR_CODES
    assert "MEDIA_STORAGE_WRITE_FAILED" in RETRYABLE_MEDIA_ERROR_CODES
    assert "SOURCE_FORBIDDEN" not in RETRYABLE_MEDIA_ERROR_CODES
    assert "SOURCE_NOT_FOUND" not in RETRYABLE_MEDIA_ERROR_CODES
    assert "IMAGE_DECODE_FAILED" not in RETRYABLE_MEDIA_ERROR_CODES


def test_retry_countdown_is_exponential_and_capped() -> None:
    assert retry_countdown_seconds(1) == 30
    assert retry_countdown_seconds(2) == 60
    assert retry_countdown_seconds(3) == 120
    assert retry_countdown_seconds(99) == 900


def test_processing_stale_policy_recovers_missing_or_old_attempts() -> None:
    now = datetime.now(UTC)

    assert processing_is_stale(None, now=now, stale_seconds=900) is True
    assert (
        processing_is_stale(
            now - timedelta(seconds=901),
            now=now,
            stale_seconds=900,
        )
        is True
    )
    assert (
        processing_is_stale(
            now - timedelta(seconds=899),
            now=now,
            stale_seconds=900,
        )
        is False
    )
