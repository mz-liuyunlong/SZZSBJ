"""Database access used only by controlled current-image media reconciliation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.modules.media_assets.models import MediaImageAsset, MediaImageSourceLink
from app.modules.media_assets.retry_policy import RETRYABLE_MEDIA_ERROR_CODES
from app.modules.sku_detail.models import (
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
)


class MediaImageBackfillRepository:
    """Scan only images/assets reachable from current ProductInfo snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_unlinked_current_images(
        self,
        *,
        after_id: UUID | None,
        limit: int,
    ) -> list[LingxingSkuProductImage]:
        statement = (
            select(LingxingSkuProductImage)
            .join(
                LingxingSkuProductInfoCurrent,
                and_(
                    LingxingSkuProductInfoCurrent.identity_id
                    == LingxingSkuProductImage.identity_id,
                    LingxingSkuProductInfoCurrent.source_snapshot_id
                    == LingxingSkuProductImage.source_snapshot_id,
                ),
            )
            .outerjoin(
                MediaImageSourceLink,
                MediaImageSourceLink.source_image_id == LingxingSkuProductImage.id,
            )
            .where(MediaImageSourceLink.id.is_(None))
        )
        if after_id is not None:
            statement = statement.where(LingxingSkuProductImage.id > after_id)

        return list(
            self.session.scalars(
                statement.order_by(LingxingSkuProductImage.id).limit(limit)
            ).all()
        )

    def has_unlinked_current_images_after(self, after_id: UUID) -> bool:
        statement = (
            select(LingxingSkuProductImage.id)
            .join(
                LingxingSkuProductInfoCurrent,
                and_(
                    LingxingSkuProductInfoCurrent.identity_id
                    == LingxingSkuProductImage.identity_id,
                    LingxingSkuProductInfoCurrent.source_snapshot_id
                    == LingxingSkuProductImage.source_snapshot_id,
                ),
            )
            .outerjoin(
                MediaImageSourceLink,
                MediaImageSourceLink.source_image_id == LingxingSkuProductImage.id,
            )
            .where(
                MediaImageSourceLink.id.is_(None),
                LingxingSkuProductImage.id > after_id,
            )
            .limit(1)
        )
        return self.session.scalar(statement) is not None

    def list_recoverable_current_assets(
        self,
        *,
        after_id: UUID | None,
        limit: int,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[MediaImageAsset]:
        current_asset_ids = (
            select(MediaImageSourceLink.asset_id)
            .join(
                LingxingSkuProductImage,
                LingxingSkuProductImage.id == MediaImageSourceLink.source_image_id,
            )
            .join(
                LingxingSkuProductInfoCurrent,
                and_(
                    LingxingSkuProductInfoCurrent.identity_id
                    == LingxingSkuProductImage.identity_id,
                    LingxingSkuProductInfoCurrent.source_snapshot_id
                    == LingxingSkuProductImage.source_snapshot_id,
                ),
            )
            .distinct()
        )
        statement = (
            select(MediaImageAsset)
            .where(
                MediaImageAsset.id.in_(current_asset_ids),
                MediaImageAsset.retry_count < max_attempts,
                or_(
                    MediaImageAsset.status == "pending",
                    and_(
                        MediaImageAsset.status == "failed",
                        MediaImageAsset.error_code.in_(RETRYABLE_MEDIA_ERROR_CODES),
                    ),
                    and_(
                        MediaImageAsset.status == "processing",
                        or_(
                            MediaImageAsset.last_attempt_at.is_(None),
                            MediaImageAsset.last_attempt_at <= stale_before,
                        ),
                    ),
                ),
            )
        )
        if after_id is not None:
            statement = statement.where(MediaImageAsset.id > after_id)
        return list(
            self.session.scalars(
                statement.order_by(MediaImageAsset.id).limit(limit)
            ).all()
        )

    def has_recoverable_current_assets_after(
        self,
        *,
        after_id: UUID,
        stale_before: datetime,
        max_attempts: int,
    ) -> bool:
        return bool(
            self.list_recoverable_current_assets(
                after_id=after_id,
                limit=1,
                stale_before=stale_before,
                max_attempts=max_attempts,
            )
        )
