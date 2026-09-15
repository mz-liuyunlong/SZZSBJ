from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.modules.media_assets.read_service import MediaAssetReadService
from app.modules.media_assets.signing import MediaUrlSigner

SOURCE_IMAGE_ID = UUID("00000000-0000-0000-0000-000000000001")
ASSET_ID = UUID("00000000-0000-0000-0000-000000000002")


def test_read_service_batch_maps_ready_asset_to_two_signed_variants() -> None:
    session = MagicMock(spec=Session)
    signer = MediaUrlSigner(SecretStr("x" * 32), ttl_seconds=3600)
    service = MediaAssetReadService(session, signer=signer)
    repository = MagicMock()
    service.repository = repository
    repository.ready_assets_for_source_images.return_value = {
        SOURCE_IMAGE_ID: SimpleNamespace(id=ASSET_ID)
    }

    urls = service.urls_for_source_images([SOURCE_IMAGE_ID])

    assert SOURCE_IMAGE_ID in urls
    assert f"/{ASSET_ID}/thumbnail?" in urls[SOURCE_IMAGE_ID].thumbnail_url
    assert f"/{ASSET_ID}/preview?" in urls[SOURCE_IMAGE_ID].preview_url
    repository.ready_assets_for_source_images.assert_called_once_with([SOURCE_IMAGE_ID])


def test_read_service_is_noop_without_runtime_signer() -> None:
    session = MagicMock(spec=Session)
    service = MediaAssetReadService(session, signer=None)
    repository = MagicMock()
    service.repository = repository

    assert service.urls_for_source_images([SOURCE_IMAGE_ID]) == {}
    repository.ready_assets_for_source_images.assert_not_called()
