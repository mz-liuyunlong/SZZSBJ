"""Read cached media metadata and resolve signed derivative files.

This module never downloads third-party images. Downloading and transformation
remain asynchronous worker responsibilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import SettingsError, get_settings
from app.modules.media_assets.repository import MediaAssetRepository
from app.modules.media_assets.schemas import MediaVariant
from app.modules.media_assets.signing import MediaUrlSigner, try_runtime_media_signer
from app.modules.media_assets.storage import FileSystemMediaStorage, MediaStorageError


@dataclass(frozen=True, slots=True)
class MediaImageUrls:
    thumbnail_url: str
    preview_url: str


@dataclass(frozen=True, slots=True)
class MediaDeliveryFile:
    path: Path
    max_age_seconds: int


class MediaDeliveryError(RuntimeError):
    """Safe delivery error code without path or source URL details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaAssetReadService:
    """Batch-resolve ready media assets to short-lived same-origin URLs."""

    def __init__(
        self,
        session: Session,
        *,
        signer: MediaUrlSigner | None,
    ) -> None:
        self.repository = MediaAssetRepository(session)
        self.signer = signer

    @classmethod
    def from_runtime(cls, session: Session) -> MediaAssetReadService:
        return cls(session, signer=try_runtime_media_signer())

    def urls_for_source_images(
        self,
        source_image_ids: list[UUID],
    ) -> dict[UUID, MediaImageUrls]:
        if self.signer is None or not source_image_ids:
            return {}

        assets = self.repository.ready_assets_for_source_images(source_image_ids)
        now = int(time.time())
        return {
            source_image_id: MediaImageUrls(
                thumbnail_url=self.signer.build_url(
                    asset.id,
                    "thumbnail",
                    now_epoch=now,
                ),
                preview_url=self.signer.build_url(
                    asset.id,
                    "preview",
                    now_epoch=now,
                ),
            )
            for source_image_id, asset in assets.items()
        }


class MediaAssetDeliveryService:
    """Verify a signed request and return only a ready cached derivative."""

    def __init__(
        self,
        session: Session,
        *,
        signer: MediaUrlSigner,
        storage: FileSystemMediaStorage,
    ) -> None:
        self.repository = MediaAssetRepository(session)
        self.signer = signer
        self.storage = storage

    @classmethod
    def from_runtime(cls, session: Session) -> MediaAssetDeliveryService:
        try:
            settings = get_settings()
        except SettingsError:
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE") from None

        signer = try_runtime_media_signer()
        storage_root = settings.media_storage_root
        if signer is None or not settings.media_cache_enabled or storage_root is None:
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE")

        return cls(
            session,
            signer=signer,
            storage=FileSystemMediaStorage(storage_root),
        )

    def resolve(
        self,
        asset_id: UUID,
        variant: MediaVariant,
        *,
        expires: int,
        signature: str,
        now_epoch: int | None = None,
    ) -> MediaDeliveryFile:
        self.signer.verify(
            asset_id,
            variant,
            expires=expires,
            signature=signature,
            now_epoch=now_epoch,
        )

        asset = self.repository.get_asset(asset_id)
        if asset is None or asset.status != "ready":
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE")

        object_key = asset.thumbnail_128_key if variant == "thumbnail" else asset.preview_512_key
        if not object_key:
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE")

        try:
            path = self.storage.path_for(object_key)
        except MediaStorageError:
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE") from None
        if not path.is_file():
            raise MediaDeliveryError("MEDIA_NOT_AVAILABLE")

        now = int(time.time()) if now_epoch is None else now_epoch
        return MediaDeliveryFile(
            path=path,
            max_age_seconds=max(0, expires - now),
        )
