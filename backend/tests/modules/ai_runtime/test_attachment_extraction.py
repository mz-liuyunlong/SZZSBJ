"""Local attachment extraction only: no secrets, network, or provider calls."""

from __future__ import annotations

import base64
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.modules.ai_runtime.attachment_extraction import (
    AttachmentBody,
    AttachmentError,
    extract_attachments,
)


def _attachment(name: str, data: bytes) -> AttachmentBody:
    return AttachmentBody(name=name, content_base64=base64.b64encode(data).decode("ascii"))


def test_text_attachment_is_available_as_untrusted_context() -> None:
    result = extract_attachments([_attachment("notes.csv", b"keyword,sales\ncoasters,100")])
    assert "File: notes.csv" in result
    assert "coasters,100" in result


def test_unsupported_binary_is_rejected_without_upload() -> None:
    with pytest.raises(AttachmentError, match="ATTACHMENT_TYPE_UNSUPPORTED"):
        extract_attachments([_attachment("report.pdf", b"%PDF-1.7")])


def test_docx_text_is_extracted_without_external_service() -> None:
    buf = BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Hello Word</w:t></w:r></w:p></w:body></w:document>",
        )
    assert "Hello Word" in extract_attachments([_attachment("report.docx", buf.getvalue())])


def test_xlsx_text_is_extracted_without_external_service() -> None:
    buf = BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row><c t="inlineStr"><is><t>coasters</t></is></c></row></sheetData>'
            "</worksheet>",
        )
    assert "coasters" in extract_attachments([_attachment("keywords.xlsx", buf.getvalue())])


def test_xlsx_numeric_and_shared_string_cells_preserved() -> None:
    buf = BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>coasters</t></si></sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row><c t="s"><v>0</v></c><c><v>9916</v></c></row></sheetData>'
            "</worksheet>",
        )
    output = extract_attachments([_attachment("market.xlsx", buf.getvalue())])
    assert "coasters | 9916" in output


def test_empty_attachment_rejected() -> None:
    with pytest.raises(AttachmentError, match="ATTACHMENT_EMPTY_CONTENT"):
        extract_attachments([_attachment("empty.txt", b"")])
