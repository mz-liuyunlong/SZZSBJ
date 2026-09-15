from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.modules.media_assets.router as media_router
from app.db.session import get_db_session
from app.main import create_app
from app.modules.media_assets.read_service import MediaDeliveryError, MediaDeliveryFile
from app.modules.media_assets.signing import MediaSignatureError

ASSET_ID = UUID("00000000-0000-0000-0000-000000000123")
SIGNATURE = "a" * 64


class FakeDeliveryService:
    def __init__(self, result: MediaDeliveryFile | Exception) -> None:
        self.result = result

    def resolve(self, *args: object, **kwargs: object) -> MediaDeliveryFile:
        del args, kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _client(
    monkeypatch: pytest.MonkeyPatch,
    result: MediaDeliveryFile | Exception,
) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    monkeypatch.setattr(
        media_router,
        "MediaAssetDeliveryService",
        SimpleNamespace(from_runtime=lambda _session: FakeDeliveryService(result)),
    )
    return TestClient(application)


def test_signed_media_route_is_get_public_and_returns_webp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "thumbnail.webp"
    image.write_bytes(b"synthetic-webp")
    client = _client(
        monkeypatch,
        MediaDeliveryFile(path=image, max_age_seconds=60),
    )

    response = client.get(
        f"/api/media/image-assets/{ASSET_ID}/thumbnail",
        params={"expires": 9999999999, "signature": SIGNATURE},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == b"synthetic-webp"
    assert "private" in response.headers["cache-control"]


def test_signed_media_route_maps_signature_failure_to_safe_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(
        monkeypatch,
        MediaSignatureError("MEDIA_SIGNATURE_INVALID"),
    )

    response = client.get(
        f"/api/media/image-assets/{ASSET_ID}/thumbnail",
        params={"expires": 9999999999, "signature": SIGNATURE},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MEDIA_SIGNATURE_INVALID"


def test_signed_media_route_maps_missing_asset_to_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(
        monkeypatch,
        MediaDeliveryError("MEDIA_NOT_AVAILABLE"),
    )

    response = client.get(
        f"/api/media/image-assets/{ASSET_ID}/preview",
        params={"expires": 9999999999, "signature": SIGNATURE},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEDIA_NOT_AVAILABLE"


def test_media_route_post_is_not_exposed() -> None:
    response = TestClient(create_app()).post(f"/api/media/image-assets/{ASSET_ID}/thumbnail")

    assert response.status_code == 405
