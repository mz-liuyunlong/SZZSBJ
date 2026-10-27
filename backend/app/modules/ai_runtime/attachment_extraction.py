"""Bounded, read-only extraction of explicitly attached text and Office files.

Never execute attachment content or allow it to override system instructions.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
from pathlib import PurePath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, Field

MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 6 * 1024 * 1024
MAX_ATTACHMENT_CONTEXT = 5000
MAX_TOTAL_CONTEXT = 7200
MAX_FILES = 10
TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".csv",
        ".md",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".html",
        ".sql",
        ".py",
        ".js",
        ".ts",
    }
)
OFFICE_SUFFIXES = frozenset({".docx", ".xlsx", ".pptx"})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | OFFICE_SUFFIXES
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PPT_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class AttachmentError(ValueError):
    pass


class AttachmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(max_length=3_000_000)


def _xlsx_text(archive: ZipFile, paths: list[str]) -> str:
    namespace = XML_NS
    strings = []
    if "xl/sharedStrings.xml" in paths:
        shared = archive.getinfo("xl/sharedStrings.xml")
        if shared.file_size > 3 * 1024 * 1024:
            raise AttachmentError("ATTACHMENT_TOO_LARGE")
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for entry in root.iter(namespace + "si"):
            strings.append("".join(node.text or "" for node in entry.iter(namespace + "t")))
    lines = []
    sheet_paths = [path for path in paths if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", path)][
        :8
    ]
    if not sheet_paths:
        raise AttachmentError("ATTACHMENT_INVALID_OFFICE")
    for path in sheet_paths:
        info = archive.getinfo(path)
        if info.file_size > 3 * 1024 * 1024:
            raise AttachmentError("ATTACHMENT_TOO_LARGE")
        root = ET.fromstring(archive.read(path))
        for row in root.iter(namespace + "row"):
            values = []
            for cell in row.findall(namespace + "c"):
                value_node = cell.find(namespace + "v")
                if cell.get("t") == "s" and value_node is not None:
                    try:
                        value = strings[int(value_node.text or "0")]
                    except (ValueError, IndexError):
                        value = ""
                elif cell.get("t") == "inlineStr":
                    value = "".join(n.text or "" for n in cell.iter(namespace + "t"))
                else:
                    value = value_node.text if value_node is not None else ""
                values.append(value or "")
            if values:
                lines.append(" | ".join(values))
            if sum(len(line) for line in lines) >= MAX_ATTACHMENT_CONTEXT:
                return "\n".join(lines)[:MAX_ATTACHMENT_CONTEXT]
    return "\n".join(lines)[:MAX_ATTACHMENT_CONTEXT]


def _office_text(data: bytes, suffix: str) -> str:
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            paths = archive.namelist()
            if len(paths) > 500:
                raise AttachmentError("ATTACHMENT_COMPLEX_ARCHIVE")
            if suffix == ".xlsx":
                return _xlsx_text(archive, paths)
            if suffix == ".docx":
                selected = ["word/document.xml"]
                tag = DOC_NS + "t"
            elif suffix == ".pptx":
                selected = [p for p in paths if re.fullmatch(r"ppt/slides/slide[0-9]+\.xml", p)][
                    :50
                ]
                tag = PPT_NS + "t"
            else:
                selected = [
                    p
                    for p in paths
                    if p == "xl/sharedStrings.xml"
                    or re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", p)
                ][:20]
                tag = XML_NS + "t"
            if not selected:
                raise AttachmentError("ATTACHMENT_INVALID_OFFICE")
            lines = []
            for name in selected:
                try:
                    info = archive.getinfo(name)
                except KeyError:
                    raise AttachmentError("ATTACHMENT_INVALID_OFFICE") from None
                if info.file_size > 3 * 1024 * 1024:
                    raise AttachmentError("ATTACHMENT_TOO_LARGE")
                tree = ET.fromstring(archive.read(name))
                lines.extend(node.text for node in tree.iter(tag) if node.text)
                if sum(len(line) for line in lines) > MAX_ATTACHMENT_CONTEXT:
                    break
            return "\n".join(lines)[:MAX_ATTACHMENT_CONTEXT]
    except (BadZipFile, ET.ParseError, RuntimeError):
        raise AttachmentError("ATTACHMENT_INVALID_OFFICE") from None


def extract_attachments(items: list[AttachmentBody]) -> str:
    if len(items) > MAX_FILES:
        raise AttachmentError("ATTACHMENT_COUNT_EXCEEDED")
    total_bytes = 0
    text_fragments = []
    for item in items:
        name = PurePath(item.name).name
        suffix = PurePath(name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise AttachmentError("ATTACHMENT_TYPE_UNSUPPORTED")
        try:
            raw = base64.b64decode(item.content_base64, validate=True)
        except binascii.Error:
            raise AttachmentError("ATTACHMENT_BASE64_INVALID") from None
        total_bytes += len(raw)
        if len(raw) > MAX_ATTACHMENT_BYTES or total_bytes > MAX_TOTAL_BYTES:
            raise AttachmentError("ATTACHMENT_TOO_LARGE")
        if suffix in TEXT_SUFFIXES:
            if b"\x00" in raw:
                raise AttachmentError("ATTACHMENT_BINARY_REJECTED")
            extracted = raw.decode("utf-8-sig", errors="replace")[:MAX_ATTACHMENT_CONTEXT]
        else:
            extracted = _office_text(raw, suffix)
        if not extracted.strip():
            raise AttachmentError("ATTACHMENT_EMPTY_CONTENT")
        text_fragments.append(f"File: {name}\n{extracted}")
    return "\n\n".join(text_fragments)[:MAX_TOTAL_CONTEXT]
