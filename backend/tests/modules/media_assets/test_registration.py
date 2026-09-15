from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.media_assets.models import MediaImageAsset
from app.modules.media_assets.registration import MediaAssetRegistrationService


def _image(image_id: int, url: str) -> SimpleNamespace:
    return SimpleNamespace(id=UUID(int=image_id), pic_url=url)


def test_registration_deduplicates_assets_and_links_each_source_image() -> None:
    session = MagicMock(spec=Session)
    service = MediaAssetRegistrationService(session)
    repository = MagicMock()
    service.repository = repository
    repository.source_links_for_images.return_value = {}
    repository.assets_by_source_url_hashes.return_value = {}
    repository.add_asset.side_effect = lambda asset: asset
    repository.add_source_link.side_effect = lambda link: link

    result = service.register_images_with_stats(
        [
            _image(1, "https://images.example.com/a.jpg"),
            _image(2, "https://images.example.com/a.jpg"),
        ]
    )

    assert result.created_asset_count == 1
    assert result.created_link_count == 2
    assert result.reused_asset_link_count == 1
    assert result.invalid_source_count == 0
    assert len(result.dispatchable_asset_ids) == 1
    assert repository.add_asset.call_count == 1
    assert repository.add_source_link.call_count == 2


def test_registration_reuses_existing_asset() -> None:
    session = MagicMock(spec=Session)
    service = MediaAssetRegistrationService(session)
    repository = MagicMock()
    service.repository = repository
    descriptor = service.describe_source("https://images.example.com/a.jpg")
    existing = MediaImageAsset(
        id=UUID(int=100),
        source_url="https://images.example.com/a.jpg",
        source_url_hash=descriptor.source_url_hash,
        source_host="images.example.com",
        status="pending",
    )
    repository.source_links_for_images.return_value = {}
    repository.assets_by_source_url_hashes.return_value = {descriptor.source_url_hash: existing}

    result = service.register_images_with_stats([_image(1, "https://images.example.com/a.jpg")])

    assert result.created_asset_count == 0
    assert result.created_link_count == 1
    assert result.reused_asset_link_count == 1
    assert result.dispatchable_asset_ids == (UUID(int=100),)
    repository.add_asset.assert_not_called()


def test_registration_terminally_links_unsupported_source_without_dispatch() -> None:
    session = MagicMock(spec=Session)
    service = MediaAssetRegistrationService(session)
    repository = MagicMock()
    service.repository = repository
    repository.source_links_for_images.return_value = {}
    repository.assets_by_source_url_hashes.return_value = {}
    repository.add_asset.side_effect = lambda asset: asset

    result = service.register_images_with_stats([_image(1, "http://images.example.com/a.jpg")])

    assert result.created_asset_count == 1
    assert result.created_link_count == 1
    assert result.invalid_source_count == 1
    assert result.dispatchable_asset_ids == ()
    asset = repository.add_asset.call_args.args[0]
    assert asset.status == "failed"
    assert asset.error_code == "SOURCE_URL_NOT_ALLOWED"
    repository.add_source_link.assert_called_once()


def test_preview_is_read_only_and_reports_counts() -> None:
    session = MagicMock(spec=Session)
    service = MediaAssetRegistrationService(session)
    repository = MagicMock()
    service.repository = repository
    repository.source_links_for_images.return_value = {}
    repository.assets_by_source_url_hashes.return_value = {}

    preview = service.preview_images(
        [
            _image(1, "https://images.example.com/a.jpg"),
            _image(2, "https://images.example.com/a.jpg"),
            _image(3, "http://images.example.com/b.jpg"),
        ]
    )

    assert preview.link_count == 3
    assert preview.new_asset_count == 2
    assert preview.reused_asset_link_count == 1
    assert preview.invalid_source_count == 1
    repository.add_asset.assert_not_called()
    repository.add_source_link.assert_not_called()
