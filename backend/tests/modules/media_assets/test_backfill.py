from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.media_assets.backfill import (
    MediaImageBackfillError,
    MediaImageBackfillService,
)
from app.modules.media_assets.registration import (
    MediaRegistrationPreview,
    MediaRegistrationResult,
)
from app.modules.media_assets.tasks import MediaTaskDispatchError


def _image(value: int) -> SimpleNamespace:
    return SimpleNamespace(id=UUID(int=value))


def _asset(value: int) -> SimpleNamespace:
    return SimpleNamespace(id=UUID(int=value))


def test_dry_run_never_commits_or_dispatches() -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.list_unlinked_current_images.side_effect = [
        [_image(1), _image(2)],
        [],
    ]
    repository.list_recoverable_current_assets.return_value = []
    registration = MagicMock()
    registration.preview_images.return_value = MediaRegistrationPreview(
        link_count=2,
        new_asset_count=1,
        reused_asset_link_count=1,
        invalid_source_count=0,
    )
    dispatcher = MagicMock()
    service = MediaImageBackfillService(
        session,
        repository=repository,
        registration=registration,
        dispatcher=dispatcher,
    )

    result = service.run(execute=False, limit=10, batch_size=2)

    assert result.mode == "dry_run"
    assert result.candidate_count == 2
    assert result.link_count == 2
    assert result.new_asset_count == 1
    assert result.reused_asset_link_count == 1
    assert result.recoverable_asset_count == 0
    session.commit.assert_not_called()
    registration.register_images_with_stats.assert_not_called()
    dispatcher.assert_not_called()


def test_execute_dispatches_recoverable_assets_after_registration_commit() -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.list_unlinked_current_images.side_effect = [
        [_image(1), _image(2)],
        [],
    ]
    repository.list_recoverable_current_assets.return_value = [
        _asset(100),
        _asset(101),
    ]
    repository.has_recoverable_current_assets_after.return_value = False
    registration = MagicMock()
    registration.register_images_with_stats.return_value = MediaRegistrationResult(
        dispatchable_asset_ids=(UUID(int=100), UUID(int=101)),
        created_asset_count=2,
        created_link_count=2,
        reused_asset_link_count=0,
        invalid_source_count=0,
    )
    dispatcher = MagicMock(return_value=1)
    service = MediaImageBackfillService(
        session,
        repository=repository,
        registration=registration,
        dispatcher=dispatcher,
    )

    result = service.run(
        execute=True,
        limit=10,
        batch_size=2,
        dispatch=True,
        max_dispatch=1,
    )

    assert result.mode == "execute"
    assert result.link_count == 2
    assert result.recoverable_asset_count == 2
    assert result.dispatched_count == 1
    assert result.dispatch_failed is False
    session.commit.assert_called_once()
    dispatcher.assert_called_once_with((UUID(int=100),))


def test_execute_can_redispatch_already_linked_pending_asset() -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.list_unlinked_current_images.return_value = []
    repository.list_recoverable_current_assets.return_value = [_asset(200)]
    repository.has_recoverable_current_assets_after.return_value = False
    registration = MagicMock()
    dispatcher = MagicMock(return_value=1)
    service = MediaImageBackfillService(
        session,
        repository=repository,
        registration=registration,
        dispatcher=dispatcher,
    )

    result = service.run(
        execute=True,
        limit=10,
        batch_size=2,
        dispatch=True,
        max_dispatch=10,
    )

    assert result.candidate_count == 0
    assert result.recoverable_asset_count == 1
    assert result.dispatched_count == 1
    registration.register_images_with_stats.assert_not_called()
    dispatcher.assert_called_once_with((UUID(int=200),))


def test_dispatch_failure_does_not_rollback_registered_metadata() -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.list_unlinked_current_images.side_effect = [[_image(1)], []]
    repository.list_recoverable_current_assets.return_value = [_asset(100)]
    repository.has_recoverable_current_assets_after.return_value = False
    registration = MagicMock()
    registration.register_images_with_stats.return_value = MediaRegistrationResult(
        dispatchable_asset_ids=(UUID(int=100),),
        created_asset_count=1,
        created_link_count=1,
        reused_asset_link_count=0,
        invalid_source_count=0,
    )

    def unavailable(_: tuple[UUID, ...]) -> int:
        raise MediaTaskDispatchError("safe")

    service = MediaImageBackfillService(
        session,
        repository=repository,
        registration=registration,
        dispatcher=unavailable,
    )

    result = service.run(
        execute=True,
        limit=10,
        batch_size=1,
        dispatch=True,
        max_dispatch=10,
    )

    assert result.status == "PASS_WITH_DISPATCH_WARNING"
    assert result.link_count == 1
    assert result.dispatch_failed is True
    assert result.dispatched_count == 0
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_partial_dispatch_is_reported_as_warning() -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.list_unlinked_current_images.return_value = []
    repository.list_recoverable_current_assets.return_value = [_asset(100)]
    repository.has_recoverable_current_assets_after.return_value = False
    service = MediaImageBackfillService(
        session,
        repository=repository,
        dispatcher=MagicMock(return_value=0),
    )

    result = service.run(
        execute=True,
        limit=10,
        batch_size=1,
        dispatch=True,
        max_dispatch=10,
    )

    assert result.dispatch_failed is True
    assert result.status == "PASS_WITH_DISPATCH_WARNING"


def test_backfill_rejects_unbounded_or_unsafe_options() -> None:
    service = MediaImageBackfillService(MagicMock(spec=Session))

    with pytest.raises(MediaImageBackfillError, match="MEDIA_IMAGE_BACKFILL_LIMIT_INVALID"):
        service.run(execute=False, limit=0)

    with pytest.raises(
        MediaImageBackfillError,
        match="MEDIA_IMAGE_BACKFILL_DISPATCH_REQUIRES_EXECUTE",
    ):
        service.run(execute=False, dispatch=True)
