"""Register source image rows as media assets without network I/O.

Registration is transaction-neutral: callers own commit/rollback. Invalid source
URLs are linked to terminal failed assets so controlled backfills cannot become
stuck re-reading the same unsupported rows forever.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.modules.media_assets.models import MediaImageAsset, MediaImageSourceLink
from app.modules.media_assets.repository import MediaAssetRepository
from app.modules.sku_detail.models import LingxingSkuProductImage


@dataclass(frozen=True, slots=True)
class MediaSourceDescriptor:
    source_url_hash: str
    source_host: str
    dispatchable: bool
    error_code: str | None


@dataclass(frozen=True, slots=True)
class MediaRegistrationPreview:
    link_count: int
    new_asset_count: int
    reused_asset_link_count: int
    invalid_source_count: int


@dataclass(frozen=True, slots=True)
class MediaRegistrationResult:
    dispatchable_asset_ids: tuple[UUID, ...]
    created_asset_count: int
    created_link_count: int
    reused_asset_link_count: int
    invalid_source_count: int


class MediaAssetRegistrationService:
    """Register immutable source-image rows without performing network I/O."""

    def __init__(self, session: Session) -> None:
        self.repository = MediaAssetRepository(session)

    def register_images(
        self,
        images: Sequence[LingxingSkuProductImage],
    ) -> tuple[UUID, ...]:
        return self.register_images_with_stats(images).dispatchable_asset_ids

    def preview_images(
        self,
        images: Sequence[LingxingSkuProductImage],
    ) -> MediaRegistrationPreview:
        pending = self._unlinked_descriptors(images)
        if not pending:
            return MediaRegistrationPreview(
                link_count=0,
                new_asset_count=0,
                reused_asset_link_count=0,
                invalid_source_count=0,
            )

        hashes = {descriptor.source_url_hash for _, descriptor in pending}
        existing = self.repository.assets_by_source_url_hashes(tuple(hashes))
        missing_hashes = hashes.difference(existing)
        link_count = len(pending)
        return MediaRegistrationPreview(
            link_count=link_count,
            new_asset_count=len(missing_hashes),
            reused_asset_link_count=link_count - len(missing_hashes),
            invalid_source_count=sum(not descriptor.dispatchable for _, descriptor in pending),
        )

    def register_images_with_stats(
        self,
        images: Sequence[LingxingSkuProductImage],
    ) -> MediaRegistrationResult:
        pending = self._unlinked_descriptors(images)
        if not pending:
            return MediaRegistrationResult(
                dispatchable_asset_ids=(),
                created_asset_count=0,
                created_link_count=0,
                reused_asset_link_count=0,
                invalid_source_count=0,
            )

        hashes = {descriptor.source_url_hash for _, descriptor in pending}
        assets = self.repository.assets_by_source_url_hashes(tuple(hashes))
        created_asset_count = 0

        for image, descriptor in pending:
            del image
            if descriptor.source_url_hash in assets:
                continue
            asset = self.repository.add_asset(
                MediaImageAsset(
                    id=uuid4(),
                    source_url=self._source_url_for_hash(
                        pending,
                        descriptor.source_url_hash,
                    ),
                    source_url_hash=descriptor.source_url_hash,
                    source_host=descriptor.source_host,
                    status="pending" if descriptor.dispatchable else "failed",
                    error_code=None if descriptor.dispatchable else descriptor.error_code,
                )
            )
            assets[descriptor.source_url_hash] = asset
            created_asset_count += 1

        dispatchable_ids: list[UUID] = []
        seen_dispatchable: set[UUID] = set()
        invalid_source_count = 0
        created_link_count = 0

        for image, descriptor in pending:
            asset = assets[descriptor.source_url_hash]
            self.repository.add_source_link(
                MediaImageSourceLink(
                    id=uuid4(),
                    source_image_id=image.id,
                    asset_id=asset.id,
                )
            )
            created_link_count += 1

            if not descriptor.dispatchable:
                invalid_source_count += 1
                continue
            if asset.status not in {"pending", "failed"}:
                continue
            if asset.id in seen_dispatchable:
                continue
            seen_dispatchable.add(asset.id)
            dispatchable_ids.append(asset.id)

        return MediaRegistrationResult(
            dispatchable_asset_ids=tuple(dispatchable_ids),
            created_asset_count=created_asset_count,
            created_link_count=created_link_count,
            reused_asset_link_count=created_link_count - created_asset_count,
            invalid_source_count=invalid_source_count,
        )

    def _unlinked_descriptors(
        self,
        images: Sequence[LingxingSkuProductImage],
    ) -> list[tuple[LingxingSkuProductImage, MediaSourceDescriptor]]:
        if not images:
            return []
        links = self.repository.source_links_for_images(tuple(image.id for image in images))
        return [
            (image, self.describe_source(image.pic_url))
            for image in images
            if image.id not in links
        ]

    @staticmethod
    def describe_source(source_url: str) -> MediaSourceDescriptor:
        digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        try:
            parsed = urlsplit(source_url)
            port = parsed.port
        except ValueError:
            return MediaSourceDescriptor(
                source_url_hash=digest,
                source_host="invalid",
                dispatchable=False,
                error_code="SOURCE_URL_NOT_ALLOWED",
            )

        host = (parsed.hostname or "").lower().rstrip(".")
        safe_host = host if host and host.isascii() and len(host) <= 255 else "invalid"
        dispatchable = bool(
            parsed.scheme == "https"
            and safe_host != "invalid"
            and parsed.username is None
            and parsed.password is None
            and port in (None, 443)
        )
        return MediaSourceDescriptor(
            source_url_hash=digest,
            source_host=safe_host,
            dispatchable=dispatchable,
            error_code=None if dispatchable else "SOURCE_URL_NOT_ALLOWED",
        )

    @staticmethod
    def _source_url_for_hash(
        pending: Sequence[tuple[LingxingSkuProductImage, MediaSourceDescriptor]],
        source_url_hash: str,
    ) -> str:
        for image, descriptor in pending:
            if descriptor.source_url_hash == source_url_hash:
                return image.pic_url
        raise RuntimeError("MEDIA_REGISTRATION_SOURCE_NOT_FOUND")
