from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from app.modules.keyword_planning.internal_export import _make_xlsx
from app.modules.keyword_planning.upload_persistence import (
    PrivateLocalKeywordStore,
    market_observation_from_row,
)
from app.modules.keyword_planning.workbook_ingestion import WorkbookRejected, parse_keyword_xlsx


def fixture_bytes():
    return _make_xlsx(
        [
            (
                "Keyword Source",
                ("关键词", "搜索量"),
                [
                    ("Pantry Organizers", 100),
                    ("pantry organizers", 150),
                    ("drawer trays", 55),
                ],
            ),
            ("Notes", ("其他资料", "备注"), [("说明", "来自上传文件")]),
        ]
    )


def test_raw_lines_preserved_without_deduplication():
    result = parse_keyword_xlsx(fixture_bytes())
    assert len(result.rows) == 6
    primary = [r for r in result.rows if r.keyword_raw]
    assert [r.keyword_normalized for r in primary] == [
        "pantry organizers",
        "pantry organizers",
        "drawer trays",
    ]
    assert result.rows[0].parse_errors == ("HEADER_ROW",)
    assert result.rows[4].parse_errors == ("NON_KEYWORD_SHEET",)
    assert result.file_size_bytes == len(fixture_bytes())


def test_synthetic_market_observations_keep_each_row_and_do_not_guess_metrics():
    parsed = parse_keyword_xlsx(fixture_bytes())
    header = parsed.rows[0].source_cells
    first, first_quality = market_observation_from_row(header, parsed.rows[1].source_cells)
    second, _ = market_observation_from_row(header, parsed.rows[2].source_cells)
    assert first["monthly_searches"] == 100
    assert second["monthly_searches"] == 150
    assert first_quality["source_columns"]["monthly_searches"] == "B"
    invalid, quality = market_observation_from_row(
        {"A": "关键词", "B": "搜索量", "C": "PPC"},
        {"A": "test", "B": "1.5", "C": "unknown"},
    )
    assert invalid == {"monthly_searches": None, "ppc_usd": None}
    assert set(quality["parse_errors"]) == {"MONTHLY_SEARCHES_INVALID", "PPC_USD_INVALID"}


def test_synthetic_extended_market_columns_keep_value_and_quality_separate():
    values, quality = market_observation_from_row(
        {"B": "购买率", "C": "广告竞品数", "D": "商品数", "E": "PPC竞价", "F": "建议竞价范围"},
        {"B": "2.5%", "C": "7", "D": "40", "E": "$0.55", "F": "$0.40-$0.60"},
    )
    assert quality["normalized_metrics"] == {
        "purchase_rate": "0.025",
        "sponsored_competitors": 7,
        "listing_count": 40,
        "suggested_bid_range": "$0.40-$0.60",
    }
    assert str(values["ppc_usd"]) == "0.55"
    assert quality["parse_errors"] == []


def test_no_keyword_header_refused():
    raw = _make_xlsx([("Notes", ("Column A", "Column B"), [("x", "y")])])
    with pytest.raises(WorkbookRejected, match="KEYWORD_COLUMN_MISSING"):
        parse_keyword_xlsx(raw)


def test_formula_is_not_executed_but_flagged():
    raw = fixture_bytes()
    with ZipFile(BytesIO(raw)) as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell = next(c for c in sheet.iter(f"{ns}c") if c.get("r") == "A2")
    ET.SubElement(cell, f"{ns}f").text = 'HYPERLINK("https://evil.example")'
    entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
    out = BytesIO()
    with ZipFile(out, "w") as zout:
        for name, content in entries.items():
            zout.writestr(name, content)
    parsed = parse_keyword_xlsx(out.getvalue())
    assert "FORMULA_OR_CELL_ERROR" in parsed.rows[1].parse_errors


def test_excel_error_cell_is_flagged_even_without_a_formula():
    raw = fixture_bytes()
    with ZipFile(BytesIO(raw)) as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
    cell = next(c for c in sheet.iter(f"{ns}c") if c.get("r") == "B2")
    cell.set("t", "e")
    cell.find(f"{ns}v").text = "#VALUE!"
    entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
    out = BytesIO()
    with ZipFile(out, "w") as zout:
        for name, content in entries.items():
            zout.writestr(name, content)
    parsed = parse_keyword_xlsx(out.getvalue())
    assert parsed.rows[1].source_cells["B"] == "#VALUE!"
    assert "FORMULA_OR_CELL_ERROR" in parsed.rows[1].parse_errors


def test_oversized_cell_is_rejected_instead_of_truncating_raw_evidence():
    raw = _make_xlsx([("Source", ("关键词",), [("x" * 16001,)])])
    with pytest.raises(WorkbookRejected, match="CELL_TEXT_LIMIT_EXCEEDED"):
        parse_keyword_xlsx(raw)


@pytest.mark.parametrize("bad_ref", ("B2ignored", "B3", "B0"))
def test_malformed_cell_references_are_rejected(bad_ref):
    raw = fixture_bytes()
    with ZipFile(BytesIO(raw)) as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
    cell = next(c for c in sheet.iter(f"{ns}c") if c.get("r") == "B2")
    cell.set("r", bad_ref)
    entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
    out = BytesIO()
    with ZipFile(out, "w") as zout:
        for name, content in entries.items():
            zout.writestr(name, content)
    with pytest.raises(WorkbookRejected, match="CELL_REFERENCE_INVALID"):
        parse_keyword_xlsx(out.getvalue())


def test_macro_archive_refused():
    raw = fixture_bytes()
    with ZipFile(BytesIO(raw)) as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    entries["xl/vbaProject.bin"] = b"not a macro"
    out = BytesIO()
    with ZipFile(out, "w") as zout:
        for name, content in entries.items():
            zout.writestr(name, content)
    with pytest.raises(WorkbookRejected, match="UNSUPPORTED_OR_MACRO"):
        parse_keyword_xlsx(out.getvalue())


def test_private_store_preserves_bytes_and_rejects_overwrite(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    store = PrivateLocalKeywordStore(tmp_path)
    content = fixture_bytes()
    import hashlib

    sha = hashlib.sha256(content).hexdigest()
    uid = uuid4()
    key = store.put_immutable(account="tenant", upload_id=uid, blob=content, sha256=sha)
    assert key.startswith("private-keyword://")
    saved = list(tmp_path.glob("*.xlsx"))
    assert len(saved) == 1 and saved[0].read_bytes() == content
    assert saved[0].stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        store.put_immutable(account="tenant", upload_id=uid, blob=content, sha256=sha)


def test_private_store_denies_group_readable_directory(tmp_path: Path):
    os.chmod(tmp_path, 0o755)
    with pytest.raises(ValueError, match="PERMISSIONS_UNSAFE"):
        PrivateLocalKeywordStore(tmp_path)
