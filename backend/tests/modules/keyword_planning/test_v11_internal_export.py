"""Pure stdlib checks; backend does not depend on openpyxl."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace as NS
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from app.modules.keyword_planning.internal_export import (
    HEADERS_01,
    HEADERS_04,
    SHEET_NAMES,
    _safe,
    generate_internal_workbook,
)

X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _run(status="blocked"):
    return NS(id=uuid4(), status=status, source_account_ref="tenant-A")


def _keyword(run, **overrides):
    data = dict(
        source_account_ref=run.source_account_ref,
        run_id=run.id,
        decision_status="review",
        risk_reasons_json=[],
        exact_reason=None,
        broad_reason=None,
        keyword_primary_type="人工确认词",
        core_root=None,
        page_coverage=None,
        score=None,
        quality_note=None,
        allocation_grade="候选复查",
        suggested_optimization_bid=None,
        exact_selected=False,
        broad_selected=False,
        broad_role=None,
        hard_risk=False,
    )
    data.update(overrides)
    return NS(**data)


def _unpack(blob):
    with ZipFile(BytesIO(blob)) as z:
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in workbook.iter(f"{X}sheet")]
        sheets = [
            ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")) for i in range(1, len(names) + 1)
        ]
        props = z.read("docProps/core.xml").decode("utf-8")
    return names, sheets, props


def _value(sheet, location):
    cell = next((c for c in sheet.iter(f"{X}c") if c.get("r") == location), None)
    if cell is None:
        return None
    v = cell.find(f"{X}v")
    if v is not None:
        return int(v.text) if v.text.isdigit() else float(v.text)
    texts = [e.text or "" for e in cell.iter(f"{X}t")]
    return "".join(texts)


def test_five_sheets_exact_fixed_headers_and_internal_warning():
    run = _run()
    sheets, workbooks, metadata = _unpack(
        generate_internal_workbook(run=run, keyword_rows=[(_keyword(run), "desk pads")])
    )
    assert sheets == list(SHEET_NAMES)
    assert tuple(_value(workbooks[0], f"{chr(65 + i)}1") for i in range(14)) == HEADERS_01
    assert len(HEADERS_01) == 14
    assert _value(workbooks[0], "A2") == "desk pads"
    assert _value(workbooks[0], "N2") == "否"
    assert _value(workbooks[3], "A2") == "禁止上传"
    assert str(run.id) in _value(workbooks[3], "B2")
    assert len(HEADERS_04) == 25
    assert _value(workbooks[3], "C2") == "desk pads"
    assert _value(workbooks[3], "Y2") == "内部分析投影；不是 Walmart 官方 Bulk 模板"
    assert "INTERNAL ANALYSIS" in metadata


def test_risk_and_root_are_persisted_decisions_not_rescored():
    run = _run("succeeded")
    row = _keyword(
        run,
        score=80,
        core_root="drawer organizer",
        broad_role="root",
        broad_selected=True,
        exact_selected=False,
        allocation_grade="P1",
        risk_reasons_json=["REVIEW"],
    )
    _, sheet, _ = _unpack(
        generate_internal_workbook(run=run, keyword_rows=[(row, "drawer organizer")])
    )
    assert _value(sheet[0], "F2") == 80
    assert _value(sheet[0], "N2") == "是"
    assert _value(sheet[1], "D2") == "是"
    assert _value(sheet[2], "D2") == "REVIEW"


def test_formula_injection_sanitized_in_all_sheets():
    run = _run()
    _, sheet, _ = _unpack(
        generate_internal_workbook(
            run=run, keyword_rows=[(_keyword(run, core_root='=HYPERLINK("evil")'), "=1+2")]
        )
    )
    assert _value(sheet[0], "A2") == "'=1+2"
    assert _value(sheet[0], "D2").startswith("'=")
    assert not list(sheet[0].iter(f"{X}f"))
    assert _safe(" @SUM(A1)") == "' @SUM(A1)"


def test_wrong_account_cannot_export():
    run = _run()
    with pytest.raises(ValueError, match="CROSS_ACCOUNT"):
        generate_internal_workbook(
            run=run, keyword_rows=[(_keyword(run, source_account_ref="other"), "test")]
        )


def test_unfinished_run_cannot_export():
    run = _run("running")
    with pytest.raises(ValueError, match="NOT_FINALIZED"):
        generate_internal_workbook(run=run, keyword_rows=[])
