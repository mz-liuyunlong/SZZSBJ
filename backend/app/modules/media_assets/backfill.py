"""Controlled, bounded registration and reconciliation for existing images.

The service never downloads images synchronously. Execute mode commits metadata
before any broker dispatch. Dispatch also reconciles previously linked pending,
retryable-failed, and stale-processing assets so broker/worker interruptions are
recoverable on a later controlled run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.media_assets.backfill_repository import MediaImageBackfillRepository
from app.modules.media_assets.registration import MediaAssetRegistrationService
from app.modules.media_assets.tasks import (
    MediaTaskDispatchError,
    dispatch_media_assets,
)

DEFAULT_LIMIT = 100
MAX_LIMIT = 2_000
DEFAULT_BATCH_SIZE = 50
MAX_BATCH_SIZE = 250
DEFAULT_MAX_DISPATCH = 50
MAX_DISPATCH = 500
DEFAULT_PROCESSING_STALE_SECONDS = 900
DEFAULT_MAX_ATTEMPTS = 3

type MediaDispatcher = Callable[[tuple[UUID, ...]], int]


class MediaImageBackfillError(RuntimeError):
    """Safe backfill error containing only a stable code."""


@dataclass(frozen=True, slots=True)
class MediaImageBackfillResult:
    mode: str
    status: str
    candidate_count: int
    link_count: int
    new_asset_count: int
    reused_asset_link_count: int
    invalid_source_count: int
    recoverable_asset_count: int
    dispatch_requested: bool
    dispatched_count: int
    dispatch_failed: bool
    has_more: bool


class MediaImageBackfillService:
    """Preview/register current images and reconcile recoverable cached assets."""

    def __init__(
        self,
        session: Session,
        *,
        repository: MediaImageBackfillRepository | None = None,
        registration: MediaAssetRegistrationService | None = None,
        dispatcher: MediaDispatcher = dispatch_media_assets,
        processing_stale_seconds: int = DEFAULT_PROCESSING_STALE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.session = session
        self.repository = repository or MediaImageBackfillRepository(session)
        self.registration = registration or MediaAssetRegistrationService(session)
        self.dispatcher = dispatcher
        self.processing_stale_seconds = processing_stale_seconds
        self.max_attempts = max_attempts

    def run(
        self,
        *,
        execute: bool,
        limit: int = DEFAULT_LIMIT,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dispatch: bool = False,
        max_dispatch: int = DEFAULT_MAX_DISPATCH,
    ) -> MediaImageBackfillResult:
        self._validate_bounds(
            execute=execute,
            limit=limit,
            batch_size=batch_size,
            dispatch=dispatch,
            max_dispatch=max_dispatch,
        )

        candidate_count = 0
        link_count = 0
        new_asset_count = 0
        reused_asset_link_count = 0
        invalid_source_count = 0
        after_image_id: UUID | None = None
        remaining = limit

        while remaining > 0:
            images = self.repository.list_unlinked_current_images(
                after_id=after_image_id,
                limit=min(batch_size, remaining),
            )
            if not images:
                break

            after_image_id = images[-1].id
            candidate_count += len(images)
            remaining -= len(images)

            if execute:
                result = self.registration.register_images_with_stats(images)
                self.session.commit()
                link_count += result.created_link_count
                new_asset_count += result.created_asset_count
                reused_asset_link_count += result.reused_asset_link_count
                invalid_source_count += result.invalid_source_count
            else:
                preview = self.registration.preview_images(images)
                link_count += preview.link_count
                new_asset_count += preview.new_asset_count
                reused_asset_link_count += preview.reused_asset_link_count
                invalid_source_count += preview.invalid_source_count

        image_has_more = bool(
            after_image_id is not None
            and remaining == 0
            and self.repository.has_unlinked_current_images_after(after_image_id)
        )

        recovery_limit = max_dispatch if dispatch else DEFAULT_MAX_DISPATCH
        stale_before = datetime.now(UTC) - timedelta(
            seconds=self.processing_stale_seconds
        )
        recoverable_assets = self.repository.list_recoverable_current_assets(
            after_id=None,
            limit=max(1, recovery_limit),
            stale_before=stale_before,
            max_attempts=self.max_attempts,
        )
        recoverable_asset_count = len(recoverable_assets)
        recovery_has_more = bool(
            recoverable_assets
            and len(recoverable_assets) >= max(1, recovery_limit)
            and self.repository.has_recoverable_current_assets_after(
                after_id=recoverable_assets[-1].id,
                stale_before=stale_before,
                max_attempts=self.max_attempts,
            )
        )

        dispatched_count = 0
        dispatch_failed = False
        if execute and dispatch and recoverable_assets:
            selected = tuple(asset.id for asset in recoverable_assets[:max_dispatch])
            try:
                dispatched_count = self.dispatcher(selected)
                if dispatched_count != len(selected):
                    dispatch_failed = True
            except MediaTaskDispatchError:
                dispatch_failed = True

        return MediaImageBackfillResult(
            mode="execute" if execute else "dry_run",
            status="PASS_WITH_DISPATCH_WARNING" if dispatch_failed else "PASS",
            candidate_count=candidate_count,
            link_count=link_count,
            new_asset_count=new_asset_count,
            reused_asset_link_count=reused_asset_link_count,
            invalid_source_count=invalid_source_count,
            recoverable_asset_count=recoverable_asset_count,
            dispatch_requested=dispatch,
            dispatched_count=dispatched_count,
            dispatch_failed=dispatch_failed,
            has_more=image_has_more or recovery_has_more,
        )

    @staticmethod
    def _validate_bounds(
        *,
        execute: bool,
        limit: int,
        batch_size: int,
        dispatch: bool,
        max_dispatch: int,
    ) -> None:
        if not 1 <= limit <= MAX_LIMIT:
            raise MediaImageBackfillError("MEDIA_IMAGE_BACKFILL_LIMIT_INVALID")
        if not 1 <= batch_size <= min(MAX_BATCH_SIZE, limit):
            raise MediaImageBackfillError("MEDIA_IMAGE_BACKFILL_BATCH_SIZE_INVALID")
        if not 0 <= max_dispatch <= MAX_DISPATCH:
            raise MediaImageBackfillError("MEDIA_IMAGE_BACKFILL_MAX_DISPATCH_INVALID")
        if dispatch and not execute:
            raise MediaImageBackfillError("MEDIA_IMAGE_BACKFILL_DISPATCH_REQUIRES_EXECUTE")
        if dispatch and max_dispatch < 1:
            raise MediaImageBackfillError("MEDIA_IMAGE_BACKFILL_MAX_DISPATCH_REQUIRED")
