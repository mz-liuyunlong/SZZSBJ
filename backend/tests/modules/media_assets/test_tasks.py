import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.modules.media_assets.tasks import (
    MediaTaskDispatchError,
    dispatch_media_assets,
    process_image_asset,
    schedule_media_asset_retry,
)


def test_media_task_contract_accepts_only_asset_id_and_no_source_url() -> None:
    assert list(inspect.signature(process_image_asset.run).parameters) == ["asset_id"]
    source = inspect.getsource(process_image_asset.run).casefold()
    assert "source_url" not in source
    assert "token" not in source


def test_dispatch_deduplicates_asset_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    delay = MagicMock()
    monkeypatch.setattr(process_image_asset, "delay", delay)
    monkeypatch.setattr(
        "app.modules.media_assets.tasks.get_settings",
        lambda: SimpleNamespace(media_cache_enabled=True),
    )
    asset_id = UUID(int=1)

    dispatched = dispatch_media_assets([asset_id, asset_id])

    assert dispatched == 1
    delay.assert_called_once_with(str(asset_id))


def test_dispatch_is_noop_when_settings_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = MagicMock()
    monkeypatch.setattr(process_image_asset, "delay", delay)

    def unavailable_settings() -> object:
        from app.core.config import SettingsError

        raise SettingsError("missing")

    monkeypatch.setattr(
        "app.modules.media_assets.tasks.get_settings",
        unavailable_settings,
    )

    assert dispatch_media_assets([UUID(int=1)]) == 0
    delay.assert_not_called()


def test_dispatch_is_noop_while_media_cache_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = MagicMock()
    monkeypatch.setattr(process_image_asset, "delay", delay)
    monkeypatch.setattr(
        "app.modules.media_assets.tasks.get_settings",
        lambda: SimpleNamespace(media_cache_enabled=False),
    )

    assert dispatch_media_assets([UUID(int=1)]) == 0
    delay.assert_not_called()


def test_dispatch_failure_raises_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_: str) -> None:
        raise RuntimeError("broker details must not escape")

    monkeypatch.setattr(process_image_asset, "delay", unavailable)
    monkeypatch.setattr(
        "app.modules.media_assets.tasks.get_settings",
        lambda: SimpleNamespace(media_cache_enabled=True),
    )

    with pytest.raises(MediaTaskDispatchError, match="media task dispatch is unavailable"):
        dispatch_media_assets([UUID(int=1)])


def test_retry_scheduler_uses_db_attempt_count_and_hard_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_async = MagicMock()
    monkeypatch.setattr(process_image_asset, "apply_async", apply_async)
    asset_id = UUID(int=9)

    assert (
        schedule_media_asset_retry(
            asset_id,
            retry_count=2,
            max_attempts=3,
        )
        is True
    )
    apply_async.assert_called_once_with(
        args=(str(asset_id),),
        countdown=60,
    )

    apply_async.reset_mock()
    assert (
        schedule_media_asset_retry(
            asset_id,
            retry_count=3,
            max_attempts=3,
        )
        is False
    )
    apply_async.assert_not_called()
