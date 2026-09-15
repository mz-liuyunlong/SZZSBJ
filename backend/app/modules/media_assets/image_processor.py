from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


class MediaImageProcessingError(RuntimeError):
    """Safe image decode/transform error carrying only a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImageDerivatives:
    content_hash: str
    source_width: int
    source_height: int
    source_bytes: int
    thumbnail_128_webp: bytes
    preview_512_webp: bytes


class MediaImageProcessor:
    def __init__(self, *, max_source_pixels: int) -> None:
        self.max_source_pixels = max_source_pixels

    def process(self, data: bytes) -> ImageDerivatives:
        if not data:
            raise MediaImageProcessingError("IMAGE_EMPTY")
        try:
            with Image.open(BytesIO(data)) as source:
                width, height = source.size
                if width <= 0 or height <= 0:
                    raise MediaImageProcessingError("IMAGE_DIMENSIONS_INVALID")
                if width * height > self.max_source_pixels:
                    raise MediaImageProcessingError("IMAGE_PIXEL_LIMIT_EXCEEDED")

                source.seek(0)
                normalized = ImageOps.exif_transpose(source)
                normalized.load()
                if "A" in normalized.getbands():
                    normalized = normalized.convert("RGBA")
                else:
                    normalized = normalized.convert("RGB")

                thumbnail = self._to_webp(normalized, 128)
                preview = self._to_webp(normalized, 512)
        except MediaImageProcessingError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
            raise MediaImageProcessingError("IMAGE_DECODE_FAILED") from None

        return ImageDerivatives(
            content_hash=hashlib.sha256(data).hexdigest(),
            source_width=width,
            source_height=height,
            source_bytes=len(data),
            thumbnail_128_webp=thumbnail,
            preview_512_webp=preview,
        )

    @staticmethod
    def _to_webp(image: Image.Image, max_size: int) -> bytes:
        rendered = image.copy()
        rendered.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        output = BytesIO()
        rendered.save(
            output,
            format="WEBP",
            quality=82,
            method=6,
        )
        return output.getvalue()
