from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.media_assets.models import MediaImageAsset, MediaImageSourceLink


class MediaAssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset(
        self,
        asset_id: UUID,
        *,
        for_update: bool = False,
    ) -> MediaImageAsset | None:
        statement = select(MediaImageAsset).where(MediaImageAsset.id == asset_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def ready_assets_for_source_images(
        self,
        source_image_ids: Sequence[UUID],
    ) -> dict[UUID, MediaImageAsset]:
        if not source_image_ids:
            return {}
        rows = self.session.execute(
            select(MediaImageSourceLink.source_image_id, MediaImageAsset)
            .join(MediaImageAsset, MediaImageAsset.id == MediaImageSourceLink.asset_id)
            .where(
                MediaImageSourceLink.source_image_id.in_(source_image_ids),
                MediaImageAsset.status == "ready",
            )
        ).all()
        return {source_image_id: asset for source_image_id, asset in rows}

    def source_links_for_images(
        self,
        source_image_ids: Sequence[UUID],
    ) -> dict[UUID, MediaImageSourceLink]:
        if not source_image_ids:
            return {}
        links = self.session.scalars(
            select(MediaImageSourceLink).where(
                MediaImageSourceLink.source_image_id.in_(source_image_ids)
            )
        ).all()
        return {link.source_image_id: link for link in links}

    def assets_by_source_url_hashes(
        self,
        source_url_hashes: Sequence[str],
    ) -> dict[str, MediaImageAsset]:
        if not source_url_hashes:
            return {}
        assets = self.session.scalars(
            select(MediaImageAsset).where(MediaImageAsset.source_url_hash.in_(source_url_hashes))
        ).all()
        return {asset.source_url_hash: asset for asset in assets}

    def get_by_source_url_hash(self, source_url_hash: str) -> MediaImageAsset | None:
        return self.session.scalar(
            select(MediaImageAsset).where(MediaImageAsset.source_url_hash == source_url_hash)
        )

    def add_asset(self, asset: MediaImageAsset) -> MediaImageAsset:
        self.session.add(asset)
        self.session.flush()
        return asset

    def get_source_link(self, source_image_id: UUID) -> MediaImageSourceLink | None:
        return self.session.scalar(
            select(MediaImageSourceLink).where(
                MediaImageSourceLink.source_image_id == source_image_id
            )
        )

    def add_source_link(self, link: MediaImageSourceLink) -> MediaImageSourceLink:
        self.session.add(link)
        self.session.flush()
        return link

    @staticmethod
    def update_record(
        record: MediaImageAsset,
        values: Mapping[str, Any],
    ) -> None:
        for key, value in values.items():
            setattr(record, key, value)
