"""No real OpenAI calls: validate bounded PDF and raster conversion contract."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.modules.ai_runtime.visual_attachments import (
    VisualAttachmentError,
    prepare_visual_input,
)


def test_png_produces_small_jpeg_image_part() -> None:
    image = Image.new("RGB", (240, 120), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    part, reserve = prepare_visual_input("photo.png", output.getvalue())
    assert part["type"] == "input_image"
    assert part["detail"] == "low"
    assert part["image_url"].startswith("data:image/jpeg;base64,")
    assert reserve > 0


def test_one_page_pdf_is_sent_as_file_not_raw_instruction_text() -> None:
    fake_pdf = b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n%%EOF"
    part, reserve = prepare_visual_input("check.pdf", fake_pdf)
    assert part["type"] == "input_file"
    assert part["filename"] == "check.pdf"
    assert part["file_data"].startswith("data:application/pdf;base64,")
    assert "detail" not in part
    assert reserve > 0


@pytest.mark.parametrize(
    ("name", "raw", "code"),
    [
        ("bad.pdf", b"not a PDF", "ATTACHMENT_INVALID_PDF"),
        ("encrypted.pdf", b"%PDF-1.7 /Encrypt /Type /Page", "ATTACHMENT_ENCRYPTED_PDF"),
        ("empty.png", b"not image bytes", "ATTACHMENT_INVALID_IMAGE"),
        ("script.svg", b"<svg/>", "ATTACHMENT_TYPE_UNSUPPORTED"),
    ],
)
def test_invalid_visual_content_fails_closed(name: str, raw: bytes, code: str) -> None:
    with pytest.raises(VisualAttachmentError, match=code):
        prepare_visual_input(name, raw)


def test_pdf_page_limit() -> None:
    pages = b"\n".join([b"/Type /Page"] * 7)
    with pytest.raises(VisualAttachmentError, match="ATTACHMENT_PDF_PAGE_LIMIT"):
        prepare_visual_input("too-many.pdf", b"%PDF-1.4\n" + pages)
