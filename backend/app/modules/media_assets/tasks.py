from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from celery import shared_task

from app.core.config import SettingsError, get_settings
from app.db.session import get_session_factory
from app.modules.media_assets.repository import MediaAssetRepository
from app.modules.media_assets.retry_policy import retry_countdown_seconds
from app.modules.media_assets.service import (
    MediaAssetProcessingError,
    MediaAssetProcessingService,
)


class MediaTaskDispatchError(RuntimeError):
    """Safe queue-dispatch failure without broker or asset details."""


@shared_task(name="media_assets.process_image_asset", ignore_result=True)  # type: ignore[untyped-decorator]
def process_image_asset(asset_id: str) -> None:
    parsed_asset_id = UUID(asset_id)
    try:
        settings = get_settings()
    except SettingsError:
        return

    with get_session_factory()() as session:
        try:
            MediaAssetProcessingService(session, settings=settings).process(parsed_asset_id)
        except MediaAssetProcessingError as exc:
            if not exc.retryable:
                return
            asset = MediaAssetRepository(session).get_asset(parsed_asset_id)
            if asset is None:
                return
            schedule_media_asset_retry(
                parsed_asset_id,
                retry_count=asset.retry_count,
                max_attempts=settings.media_max_attempts,
            )


def schedule_media_asset_retry(
    asset_id: UUID,
    *,
    retry_count: int,
    max_attempts: int,
) -> bool:
    """Schedule one bounded retry; reconciliation covers broker failures."""
    if retry_count >= max_attempts:
        return False
    try:
        process_image_asset.apply_async(
            args=(str(asset_id),),
            countdown=retry_countdown_seconds(retry_count),
        )
    except Exception:
        raise MediaTaskDispatchError("media retry dispatch is unavailable") from None
    return True


def _media_cache_dispatch_enabled() -> bool:
    try:
        return get_settings().media_cache_enabled
    except SettingsError:
        # Media caching is optional and must never break ProductInfo publication.
        return False


def dispatch_media_assets(asset_ids: Iterable[UUID]) -> int:
    if not _media_cache_dispatch_enabled():
        return 0

    dispatched = 0
    seen: set[UUID] = set()
    for asset_id in asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        try:
            process_image_asset.delay(str(asset_id))
        except Exception:
            raise MediaTaskDispatchError("media task dispatch is unavailable") from None
        dispatched += 1
    return dispatched
