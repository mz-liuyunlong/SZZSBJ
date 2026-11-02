"""Pure, offline intake and route registration tests (never use production data)."""

import base64
import io
from zipfile import ZipFile

import pytest
from fastapi import FastAPI

from app.core.api import ApiError
from app.modules.ai_runtime.skill_library_routes import (
    UploadBody,
    _decode_file,
    _extract_document,
    _extract_zip,
    router,
)


def _zip(content: str) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("walmart-ads/SKILL.md", content)
    return output.getvalue()


def test_import_one_standard_skill_without_executing_scripts():
    name, desc, content = _extract_zip(
        _zip(
            "---\nname: walmart-ads\ndescription: Optimize Walmart ads\n---\n\n# Steps\nVerify ACOS"
        )
    )
    assert name == "walmart-ads"
    assert desc == "Optimize Walmart ads"
    assert "Verify ACOS" in content


def test_zip_without_skill_is_rejected():
    with pytest.raises(ApiError):
        _extract_zip(_zip("No YAML"))


def test_document_upload_is_bounded_and_decodable():
    encoded = base64.b64encode(b"# Rules\nNever invent profits").decode("ascii")
    filename, suffix, raw = _decode_file(UploadBody(name="rules.md", content_base64=encoded))
    assert filename == "rules.md"
    assert "Never invent profits" in _extract_document(filename, suffix, raw)


def test_skill_library_routes_exist_and_require_main_auth():
    app = FastAPI()
    app.include_router(router)
    paths = set(app.openapi()["paths"])
    assert "/api/ai-runtime/skill-library" in paths
    assert "/api/ai-runtime/skill-library/published" in paths
    assert "/api/ai-runtime/skill-library/bindings/{connector_id}" in paths
    assert "/api/ai-runtime/skill-library/{skill_id}/versions/{revision_id}/documents" in paths
