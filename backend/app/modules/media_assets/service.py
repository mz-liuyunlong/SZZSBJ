from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.media_assets.downloader import MediaDownloadError, MediaSourceDownloader
from app.modules.media_assets.image_processor import (
    MediaImageProcessingError,
    MediaImageProcessor,
)
from app.modules.media_assets.repository import MediaAssetRepository
from app.modules.media_assets.retry_policy import processing_is_stale
from app.modules.media_assets.storage import FileSystemMediaStorage, MediaStorageError


class MediaAssetProcessingError(RuntimeError):
    """Safe processing error for workers and logs."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class MediaAssetProcessingResult:
    status: str
    asset_id: UUID
    error_code: str | None = None


def media_object_keys(content_hash: str) -> tuple[str, str]:
    prefix = content_hash[:2]
    base = f"images/{prefix}/{content_hash}"
    return (
        f"{base}/thumbnail_128.webp",
        f"{base}/preview_512.webp",
    )


class MediaAssetProcessingService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        downloader: MediaSourceDownloader | None = None,
        processor: MediaImageProcessor | None = None,
        storage: FileSystemMediaStorage | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = MediaAssetRepository(session)

        if not self.settings.media_cache_enabled:
            self.downloader = downloader
            self.processor = processor
            self.storage = storage
            return

        storage_root = self.settings.media_storage_root
        if storage_root is None:
            raise MediaAssetProcessingError("MEDIA_CACHE_NOT_CONFIGURED", retryable=False)
        self.downloader = downloader or MediaSourceDownloader(
            allowed_hosts=self.settings.media_allowed_source_host_set,
            timeout_ms=self.settings.media_download_timeout_ms,
            max_source_bytes=self.settings.media_max_source_bytes,
        )
        self.processor = processor or MediaImageProcessor(
            max_source_pixels=self.settings.media_max_source_pixels,
        )
        self.storage = storage or FileSystemMediaStorage(Path(storage_root))

    def process(self, asset_id: UUID) -> MediaAssetProcessingResult:
        if not self.settings.media_cache_enabled:
            raise MediaAssetProcessingError("MEDIA_CACHE_DISABLED", retryable=False)
        if self.downloader is None or self.processor is None or self.storage is None:
            raise MediaAssetProcessingError("MEDIA_CACHE_NOT_CONFIGURED", retryable=False)

        asset = self.repository.get_asset(asset_id, for_update=True)
        if asset is None:
            raise MediaAssetProcessingError("MEDIA_ASSET_NOT_FOUND", retryable=False)
        if asset.status == "ready":
            self.session.rollback()
            return MediaAssetProcessingResult(status="ready", asset_id=asset.id)
        if asset.status == "processing" and not processing_is_stale(
            asset.last_attempt_at,
            now=datetime.now(UTC),
            stale_seconds=self.settings.media_processing_stale_seconds,
        ):
            self.session.rollback()
            return MediaAssetProcessingResult(status="processing", asset_id=asset.id)
        if asset.retry_count >= self.settings.media_max_attempts:
            self.repository.update_record(
                asset,
                {
                    "status": "failed",
                    "error_code": "MEDIA_MAX_ATTEMPTS_EXCEEDED",
                    "updated_at": datetime.now(UTC),
                },
            )
            self.session.commit()
            raise MediaAssetProcessingError(
                "MEDIA_MAX_ATTEMPTS_EXCEEDED",
                retryable=False,
            )

        source_url = asset.source_url
        now = datetime.now(UTC)
        self.repository.update_record(
            asset,
            {
                "status": "processing",
                "retry_count": asset.retry_count + 1,
                "error_code": None,
                "last_attempt_at": now,
                "updated_at": now,
            },
        )
        self.session.commit()

        try:
            downloaded = self.downloader.download(source_url)
            derivatives = self.processor.process(downloaded.data)
            thumbnail_key, preview_key = media_object_keys(derivatives.content_hash)
            self.storage.write(thumbnail_key, derivatives.thumbnail_128_webp)
            self.storage.write(preview_key, derivatives.preview_512_webp)
        except MediaDownloadError as exc:
            self._mark_failed(asset_id, exc.code)
            raise MediaAssetProcessingError(exc.code, retryable=exc.retryable) from None
        except MediaImageProcessingError as exc:
            self._mark_failed(asset_id, exc.code)
            raise MediaAssetProcessingError(exc.code, retryable=False) from None
        except MediaStorageError as exc:
            self._mark_failed(asset_id, exc.code)
            raise MediaAssetProcessingError(
                exc.code,
                retryable=exc.code == "MEDIA_STORAGE_WRITE_FAILED",
            ) from None

        refreshed = self.repository.get_asset(asset_id, for_update=True)
        if refreshed is None:
            self.session.rollback()
            raise MediaAssetProcessingError("MEDIA_ASSET_NOT_FOUND", retryable=False)

        finished_at = datetime.now(UTC)
        self.repository.update_record(
            refreshed,
            {
                "status": "ready",
                "content_hash": derivatives.content_hash,
                "mime_type": downloaded.mime_type,
                "source_width": derivatives.source_width,
                "source_height": derivatives.source_height,
                "source_bytes": derivatives.source_bytes,
                "thumbnail_128_key": thumbnail_key,
                "preview_512_key": preview_key,
                "error_code": None,
                "cached_at": finished_at,
                "updated_at": finished_at,
            },
        )
        self.session.commit()
        return MediaAssetProcessingResult(status="ready", asset_id=asset_id)

    def _mark_failed(self, asset_id: UUID, error_code: str) -> None:
        failed = self.repository.get_asset(asset_id, for_update=True)
        if failed is None:
            self.session.rollback()
            return
        self.repository.update_record(
            failed,
            {
                "status": "failed",
                "error_code": error_code,
                "updated_at": datetime.now(UTC),
            },
        )
        self.session.commit()
