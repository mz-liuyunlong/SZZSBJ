"""Create and validate short-lived URLs for cached media only.

The signature contains no source URL, SKU, product field, user data, or secret.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode
from uuid import UUID

from pydantic import SecretStr

from app.core.config import SettingsError, get_settings
from app.modules.media_assets.schemas import MediaVariant


class MediaSignatureError(RuntimeError):
    """Safe signing error code suitable for API translation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaUrlSigner:
    def __init__(self, secret: SecretStr, *, ttl_seconds: int) -> None:
        self.secret = secret.get_secret_value().encode("utf-8")
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _message(asset_id: UUID, variant: MediaVariant, expires: int) -> bytes:
        return f"{asset_id}:{variant}:{expires}".encode("ascii")

    def signature(self, asset_id: UUID, variant: MediaVariant, expires: int) -> str:
        return hmac.new(
            self.secret,
            self._message(asset_id, variant, expires),
            hashlib.sha256,
        ).hexdigest()

    def build_url(
        self,
        asset_id: UUID,
        variant: MediaVariant,
        *,
        now_epoch: int | None = None,
    ) -> str:
        now = int(time.time()) if now_epoch is None else now_epoch
        bucket_seconds = max(1, self.ttl_seconds // 2)
        expires = ((now // bucket_seconds) + 2) * bucket_seconds
        signature = self.signature(asset_id, variant, expires)
        query = urlencode({"expires": expires, "signature": signature})
        return f"/api/media/image-assets/{asset_id}/{variant}?{query}"

    def verify(
        self,
        asset_id: UUID,
        variant: MediaVariant,
        *,
        expires: int,
        signature: str,
        now_epoch: int | None = None,
    ) -> None:
        now = int(time.time()) if now_epoch is None else now_epoch
        if expires < now:
            raise MediaSignatureError("MEDIA_SIGNATURE_EXPIRED")
        expected = self.signature(asset_id, variant, expires)
        if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
            raise MediaSignatureError("MEDIA_SIGNATURE_INVALID")


def try_runtime_media_signer() -> MediaUrlSigner | None:
    """Return a signer only when the optional media cache is fully enabled."""
    try:
        settings = get_settings()
    except SettingsError:
        return None
    secret = settings.media_signing_secret
    if not settings.media_cache_enabled or secret is None:
        return None
    return MediaUrlSigner(secret, ttl_seconds=settings.media_signed_url_ttl_seconds)
