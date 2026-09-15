from io import BytesIO

import pytest
from PIL import Image

from app.modules.media_assets.image_processor import (
    MediaImageProcessingError,
    MediaImageProcessor,
)


def png_bytes(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def test_processor_creates_bounded_webp_derivatives() -> None:
    processor = MediaImageProcessor(max_source_pixels=10_000_000)

    result = processor.process(png_bytes(1600, 1600))

    assert result.source_width == 1600
    assert result.source_height == 1600
    assert len(result.content_hash) == 64
    with Image.open(BytesIO(result.thumbnail_128_webp)) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert thumbnail.width <= 128
        assert thumbnail.height <= 128
    with Image.open(BytesIO(result.preview_512_webp)) as preview:
        assert preview.format == "WEBP"
        assert preview.width <= 512
        assert preview.height <= 512


def test_processor_rejects_pixel_limit() -> None:
    processor = MediaImageProcessor(max_source_pixels=100)

    with pytest.raises(MediaImageProcessingError) as exc:
        processor.process(png_bytes(20, 20))

    assert exc.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_processor_rejects_non_image_bytes() -> None:
    processor = MediaImageProcessor(max_source_pixels=1_000_000)

    with pytest.raises(MediaImageProcessingError) as exc:
        processor.process(b"not-an-image")

    assert exc.value.code == "IMAGE_DECODE_FAILED"
