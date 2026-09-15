from uuid import UUID

import pytest
from pydantic import SecretStr

from app.modules.media_assets.signing import MediaSignatureError, MediaUrlSigner

ASSET_ID = UUID("00000000-0000-0000-0000-000000000123")


def test_signer_builds_relative_url_without_source_data() -> None:
    signer = MediaUrlSigner(SecretStr("x" * 32), ttl_seconds=3600)

    url = signer.build_url(ASSET_ID, "thumbnail", now_epoch=1000)

    assert url.startswith(f"/api/media/image-assets/{ASSET_ID}/thumbnail?")
    assert "expires=3600" in url
    assert "signature=" in url
    assert "sku" not in url.casefold()


def test_signer_url_is_stable_within_half_ttl_bucket() -> None:
    signer = MediaUrlSigner(SecretStr("x" * 32), ttl_seconds=3600)

    first = signer.build_url(ASSET_ID, "thumbnail", now_epoch=1000)
    second = signer.build_url(ASSET_ID, "thumbnail", now_epoch=1100)
    next_bucket = signer.build_url(ASSET_ID, "thumbnail", now_epoch=1900)

    assert first == second
    assert first != next_bucket


def test_signer_accepts_valid_signature_and_rejects_tampering() -> None:
    signer = MediaUrlSigner(SecretStr("x" * 32), ttl_seconds=3600)
    expires = 4600
    signature = signer.signature(ASSET_ID, "preview", expires)

    signer.verify(
        ASSET_ID,
        "preview",
        expires=expires,
        signature=signature,
        now_epoch=1000,
    )

    with pytest.raises(MediaSignatureError, match="MEDIA_SIGNATURE_INVALID"):
        signer.verify(
            ASSET_ID,
            "thumbnail",
            expires=expires,
            signature=signature,
            now_epoch=1000,
        )


def test_signer_rejects_expired_url() -> None:
    signer = MediaUrlSigner(SecretStr("x" * 32), ttl_seconds=60)
    signature = signer.signature(ASSET_ID, "thumbnail", 100)

    with pytest.raises(MediaSignatureError, match="MEDIA_SIGNATURE_EXPIRED"):
        signer.verify(
            ASSET_ID,
            "thumbnail",
            expires=100,
            signature=signature,
            now_epoch=101,
        )
