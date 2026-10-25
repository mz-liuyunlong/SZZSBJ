"""Pure bounded XLSX reader + immutable source-row preparation.

Parsing has no DB or object-store side effects. Raw bytes must be stored by a
configured private object store before any repository records can be committed.
The workbook is untrusted; formulas are never evaluated and become row errors.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from .rule_gates import normalize_keyword

X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"
COLUMNS = re.compile(r"([A-Z]{1,3})([1-9][0-9]*)")
KEYWORD_HEADERS = frozenset(
    {"keyword", "keywords", "search term", "search_term", "关键词", "搜索词"}
)
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 65 * 1024 * 1024
MAX_SHEETS = 12
MAX_ROWS = 5000
MAX_COLUMNS = 100
MAX_TEXT = 16000


class WorkbookRejected(ValueError):
    """Stable rejection code for data-source and parser failures."""


@dataclass(frozen=True)
class ParsedSourceRow:
    sheet_name: str
    row_number: int
    source_cells: dict[str, object]
    keyword_raw: str | None
    keyword_normalized: str | None
    parse_errors: tuple[str, ...]


@dataclass(frozen=True)
class ParsedWorkbook:
    sha256: str
    file_size_bytes: int
    rows: tuple[ParsedSourceRow, ...]
    parser_version: str = "xlsx_stdlib_v1"


def _text(value: ET.Element | None) -> str:
    if value is None:
        return ""
    return "".join(value.itertext())


def _read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    result = []
    for item in root.findall(f"{X}si"):
        result.append("".join(t.text or "" for t in item.iter(f"{X}t")))
    return result


def _read_cell(cell: ET.Element, strings: list[str]) -> tuple[object, bool]:
    formula = cell.find(f"{X}f") is not None
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        content = "".join(t.text or "" for t in cell.iter(f"{X}t"))
    else:
        content = _text(cell.find(f"{X}v"))
    if cell_type == "s":
        try:
            content = strings[int(content)]
        except (ValueError, IndexError):
            return "", True
    if len(str(content)) > MAX_TEXT:
        raise WorkbookRejected("CELL_TEXT_LIMIT_EXCEEDED")
    return content, formula or cell_type == "e"


def parse_keyword_xlsx(content: bytes) -> ParsedWorkbook:
    if not isinstance(content, bytes) or not content or len(content) > MAX_FILE_BYTES:
        raise WorkbookRejected("FILE_SIZE_OUT_OF_RANGE")
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise WorkbookRejected("XLSX_INVALID_ZIP") from exc
    with archive as zf:
        files = zf.infolist()
        if (
            len(files) > 500
            or sum(e.file_size for e in files) > MAX_UNCOMPRESSED_BYTES
            or any(e.flag_bits & 1 for e in files)
        ):
            raise WorkbookRejected("XLSX_ARCHIVE_LIMIT_EXCEEDED")
        names = zf.namelist()
        if (
            any("vbaProject.bin" in name or name.endswith(".exe") for name in names)
            or "xl/workbook.xml" not in names
            or "xl/_rels/workbook.xml.rels" not in names
        ):
            raise WorkbookRejected("XLSX_UNSUPPORTED_OR_MACRO")
        strings = _read_shared_strings(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        links = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        paths = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in links
            if r.get("Type", "").endswith("/worksheet")
        }
        sheets = workbook.find(f"{X}sheets")
        if sheets is None or not 1 <= len(sheets) <= MAX_SHEETS:
            raise WorkbookRejected("SHEET_COUNT_OUT_OF_RANGE")
        parsed: list[ParsedSourceRow] = []
        keyword_sheets = 0
        for sheet in sheets:
            sheet_name = sheet.attrib.get("name", "")
            if not sheet_name or len(sheet_name) > 255:
                raise WorkbookRejected("SHEET_NAME_INVALID")
            rel = sheet.get(f"{R}id")
            target = paths.get(rel)
            if not target:
                raise WorkbookRejected("XLSX_WORKSHEET_MISSING")
            path = (
                posixpath.normpath("xl/" + target.lstrip("/"))
                if not target.startswith("/")
                else target.lstrip("/")
            )
            if not path.startswith("xl/worksheets/") or path not in names:
                raise WorkbookRejected("XLSX_WORKSHEET_PATH_UNSAFE")
            root = ET.fromstring(zf.read(path))
            data = root.find(f"{X}sheetData")
            if data is None:
                continue
            header_column = None
            first_row = True
            for row in data.findall(f"{X}row"):
                line = int(row.get("r", "0"))
                if line < 1:
                    raise WorkbookRejected("ROW_NUMBER_INVALID")
                cells: dict[str, object] = {}
                invalid = False
                for cell in row.findall(f"{X}c"):
                    key_match = COLUMNS.fullmatch(cell.get("r", ""))
                    if key_match is None or int(key_match.group(2)) != line:
                        raise WorkbookRejected("CELL_REFERENCE_INVALID")
                    column = key_match.group(1)
                    if column in cells:
                        raise WorkbookRejected("CELL_REFERENCE_DUPLICATE")
                    if len(cells) >= MAX_COLUMNS:
                        raise WorkbookRejected("COLUMN_LIMIT_EXCEEDED")
                    value, error = _read_cell(cell, strings)
                    cells[column] = value
                    invalid = invalid or error
                if first_row:
                    first_row = False
                    for col, value in cells.items():
                        if normalize_keyword(str(value)) in KEYWORD_HEADERS:
                            header_column = col
                            break
                    if header_column is not None:
                        keyword_sheets += 1
                    parsed.append(
                        ParsedSourceRow(
                            sheet_name=sheet_name,
                            row_number=line,
                            source_cells=cells,
                            keyword_raw=None,
                            keyword_normalized=None,
                            parse_errors=(
                                ("HEADER_ROW",)
                                if header_column is not None
                                else ("NON_KEYWORD_SHEET",)
                            ),
                        )
                    )
                    continue
                keyword = str(cells.get(header_column, "")).strip() if header_column else ""
                errors = ["NON_KEYWORD_SHEET"] if header_column is None else []
                if invalid:
                    errors.append("FORMULA_OR_CELL_ERROR")
                if not keyword:
                    errors.append("EMPTY_KEYWORD")
                if len(keyword) > 500:
                    errors.append("KEYWORD_TOO_LONG")
                parsed.append(
                    ParsedSourceRow(
                        sheet_name=sheet_name,
                        row_number=line,
                        source_cells=cells,
                        keyword_raw=keyword or None,
                        keyword_normalized=normalize_keyword(keyword) if keyword else None,
                        parse_errors=tuple(errors),
                    )
                )
                if len(parsed) > MAX_ROWS:
                    raise WorkbookRejected("ROW_LIMIT_EXCEEDED")
        if not parsed or keyword_sheets == 0:
            raise WorkbookRejected("KEYWORD_COLUMN_MISSING")
    return ParsedWorkbook(hashlib.sha256(content).hexdigest(), len(content), tuple(parsed))
