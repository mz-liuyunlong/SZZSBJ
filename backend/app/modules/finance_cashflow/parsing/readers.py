# ruff: noqa: E501, E402, UP031
"""文件 → 行列表。xlsx 用标准库（zipfile + ElementTree，同 operation_plans 做法）；xls 需要 xlrd（可选）。
所有单元格都以**字符串**返回：xlsx 读 <v> 原文；xls 的数值单元格在这里就 repr 成字符串，金额链路不见 float。"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from .model import RejectFile

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 200


def kind_of(content: bytes) -> str:
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:2] == b"PK":
        return "xlsx"
    if content[:4] == b"\xd0\xcf\x11\xe0":
        return "xls"
    return "text"


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(
    content: bytes, max_bytes: int = MAX_UNZIPPED_BYTES, max_entries: int = MAX_ZIP_ENTRIES
):
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise RejectFile("不是有效的 xlsx") from exc
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise RejectFile("文件异常（解压超限）：条目数超过 %d" % max_entries)
    if sum(i.file_size for i in infos) > max_bytes:
        raise RejectFile("文件异常（解压超限）：解压后超过 %d MB" % (max_bytes // 1024 // 1024))
    names = set(zf.namelist())
    if "xl/workbook.xml" not in names:
        raise RejectFile("不是有效的 xlsx（缺 workbook）")
    shared = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")).findall(
            "pr:Relationship", NS
        ):
            tgt = rel.get("Target").lstrip("/")
            rels[rel.get("Id")] = tgt if tgt.startswith("xl/") else "xl/" + tgt
    out = []
    for i, sh in enumerate(wb.findall("m:sheets/m:sheet", NS)):
        path = rels.get(sh.get("{%s}id" % NS["r"]), "xl/worksheets/sheet%d.xml" % (i + 1))
        if path not in names:
            continue
        rows = []
        for row in ET.fromstring(zf.read(path)).iter("{%s}row" % NS["m"]):
            cells: dict = {}
            for c in row.findall("m:c", NS):
                t = c.get("t")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                else:
                    v = c.find("m:v", NS)
                    val = v.text if v is not None else None
                    if t == "s" and val is not None:
                        val = shared[int(val)]
                cells[_col_index(c.get("r"))] = val
            if cells:
                rows.append([cells.get(j) for j in range(max(cells) + 1)])
            else:
                rows.append([])
        out.append((sh.get("name"), rows))
    return out


def read_xls(content: bytes):
    try:
        import xlrd  # type: ignore
    except ImportError as exc:
        raise RejectFile("xls 需要 xlrd 才能读取（或请财务另存为 xlsx 上传）") from exc
    try:
        wb = xlrd.open_workbook(file_contents=content)
    except Exception as exc:  # noqa: BLE001
        raise RejectFile("xls 打不开") from exc
    out = []
    for sh in wb.sheets():
        rows = []
        for i in range(sh.nrows):
            r = []
            for c in sh.row(i):
                if c.ctype == xlrd.XL_CELL_EMPTY:
                    r.append(None)
                elif c.ctype == xlrd.XL_CELL_DATE:
                    y, mo, d, hh, mi, ss = xlrd.xldate_as_tuple(c.value, wb.datemode)
                    r.append("%04d-%02d-%02d %02d:%02d:%02d" % (y, mo, d, hh, mi, ss))
                elif c.ctype == xlrd.XL_CELL_NUMBER:
                    r.append(repr(c.value))  # 数值在这里就成字符串
                else:
                    r.append(str(c.value))
            rows.append(r)
        out.append((sh.name, rows))
    return out


def read_csv(content: bytes):
    text = content.decode("utf-8-sig", errors="strict")
    return list(csv.reader(io.StringIO(text)))


def cell(v) -> str:
    return re.sub(r"\s+", " ", "" if v is None else str(v)).strip()


def norm_head(v) -> str:
    """表头比较：去空白、去 [英文] 部分。"""
    return re.sub(r"\[.*$", "", re.sub(r"\s+", "", cell(v)))


MAX_PDF_PAGES = 300


def read_pdf_lines(content: bytes, max_pages: int = MAX_PDF_PAGES) -> list[list[str]]:
    """PDF → 每页的文本行（pypdf 抽文字，不做 OCR；扫描件读不出字就当认不出）。"""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - pypdf 是后端依赖
        raise RejectFile("PDF 需要 pypdf 才能读取") from exc
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise RejectFile("PDF 有密码，请导出不加密的版本")
        if len(reader.pages) > max_pages:
            raise RejectFile("PDF 超过 %d 页，请按月分开导出" % max_pages)
        return [(page.extract_text() or "").splitlines() for page in reader.pages]
    except RejectFile:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise RejectFile("PDF 打不开") from exc
