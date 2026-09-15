"""Run a bounded media-image backfill.

Default invocation is dry-run. Execute mode requires explicit authorization.
Output is intentionally limited to counts/status and never includes URLs, SKUs,
image IDs, product fields, credentials, or broker details.
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.media_assets.backfill import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_LIMIT,
    DEFAULT_MAX_DISPATCH,
    MAX_BATCH_SIZE,
    MAX_DISPATCH,
    MAX_LIMIT,
    MediaImageBackfillError,
    MediaImageBackfillService,
)


def main() -> int:
    execute = _exact_true("MEDIA_IMAGE_BACKFILL_EXECUTE")
    dispatch = _exact_true("MEDIA_IMAGE_BACKFILL_DISPATCH")

    if execute and not _exact_true("MEDIA_IMAGE_BACKFILL_AUTHORIZED"):
        print("MEDIA_IMAGE_BACKFILL_REQUIRES_AUTHORIZATION")
        return 2
    if dispatch and not execute:
        print("MEDIA_IMAGE_BACKFILL_DISPATCH_REQUIRES_EXECUTE")
        return 2

    try:
        limit = _bounded_int(
            "MEDIA_IMAGE_BACKFILL_LIMIT",
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )
        batch_size = _bounded_int(
            "MEDIA_IMAGE_BACKFILL_BATCH_SIZE",
            default=DEFAULT_BATCH_SIZE,
            minimum=1,
            maximum=min(MAX_BATCH_SIZE, limit),
        )
        max_dispatch = _bounded_int(
            "MEDIA_IMAGE_BACKFILL_MAX_DISPATCH",
            default=DEFAULT_MAX_DISPATCH,
            minimum=0,
            maximum=MAX_DISPATCH,
        )
        settings = get_settings()
        with get_session_factory()() as session:
            result = MediaImageBackfillService(
                session,
                processing_stale_seconds=settings.media_processing_stale_seconds,
                max_attempts=settings.media_max_attempts,
            ).run(
                execute=execute,
                limit=limit,
                batch_size=batch_size,
                dispatch=dispatch,
                max_dispatch=max_dispatch,
            )
    except MediaImageBackfillError as error:
        print(str(error))
        return 2
    except ValueError as error:
        print(str(error))
        return 2
    except Exception:
        print("MEDIA_IMAGE_BACKFILL_FAILED")
        return 1

    for name, value in asdict(result).items():
        print(f"{name}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


def _bounded_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name}_INVALID") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name}_INVALID")
    return value


def _exact_true(name: str) -> bool:
    return os.getenv(name, "").casefold() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
