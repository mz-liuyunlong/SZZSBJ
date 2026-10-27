"""Bounded image/PDF inputs for OpenAI Responses, without local OCR or paid calls.

PDF text and pages are parsed by the provider at invocation time. The signed-in
user supplies files explicitly. Neither image metadata nor original bytes are saved
to chats, tasks, or logs. The server never fetches a user-supplied URL.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import PurePath

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_VISUAL_FILES = 4
MAX_PDF_PAGES = 6
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_EDGE = 1280

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
VISUAL_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}


class VisualAttachmentError(ValueError):
    pass


def prepare_visual_input(name: str, raw: bytes) -> tuple[dict[str, str], int]:
    """Return one validated Responses content part and conservative token budget.

    A model with vision capability is required; compatibility is checked by the
    provider, not guessed from filenames. PDF page count uses a fail-closed
    conventional-page check; unsupported compressed page trees must be rejected.
    """
    suffix = PurePath(name).suffix.lower()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise VisualAttachmentError("ATTACHMENT_INVALID_PDF")
        if re.search(rb"/Encrypt\b", raw):
            raise VisualAttachmentError("ATTACHMENT_ENCRYPTED_PDF")
        pages = len(re.findall(rb"/Type\s*/Page\b", raw))
        if not 1 <= pages <= MAX_PDF_PAGES:
            raise VisualAttachmentError("ATTACHMENT_PDF_PAGE_LIMIT_OR_UNSUPPORTED")
        return (
            {
                "type": "input_file",
                "filename": PurePath(name).name,
                "file_data": "data:application/pdf;base64," + base64.b64encode(raw).decode("ascii"),
            },
            pages * 10000,
        )
    if suffix not in IMAGE_SUFFIXES:
        raise VisualAttachmentError("ATTACHMENT_TYPE_UNSUPPORTED")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise VisualAttachmentError("ATTACHMENT_IMAGE_TOO_LARGE")
            image.seek(0)  # first frame only; do not silently imply full GIF analysis
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            rgb.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=80, optimize=True)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise VisualAttachmentError("ATTACHMENT_INVALID_IMAGE") from None
    return (
        {
            "type": "input_image",
            "image_url": "data:image/jpeg;base64,"
            + base64.b64encode(output.getvalue()).decode("ascii"),
            "detail": "low",
        },
        8000,
    )
