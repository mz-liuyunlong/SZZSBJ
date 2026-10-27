"""Four-sheet analysis stays read-only and retains the immutable keyword view."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest

from app.modules.ai_runtime.four_sheet_export import SHEET_NAMES, generate_four_sheet_review


def test_four_sheet_workbook_contains_only_requested_review_sheets() -> None:
    run = SimpleNamespace(id=uuid4(), status="succeeded", source_account_ref="synthetic-account")
    content = generate_four_sheet_review(run=run, keyword_rows=[])
    with ZipFile(BytesIO(content)) as workbook:
        xml = workbook.read("xl/workbook.xml").decode("utf-8")
        assert all(name in xml for name in SHEET_NAMES)
        assert "04_广告结构_内部预览" not in xml
        assert len([p for p in workbook.namelist() if p.startswith("xl/worksheets/sheet")]) == 4
        styles = workbook.read("xl/styles.xml").decode("utf-8")
        assert 'patternType="solid"' not in styles or 'fillId="2"' not in styles


def test_four_sheet_rejects_unfinished_runs() -> None:
    run = SimpleNamespace(id=uuid4(), status="running", source_account_ref="synthetic")
    with pytest.raises(ValueError, match="ANALYSIS_NOT_FINALIZED"):
        generate_four_sheet_review(run=run, keyword_rows=[])


def test_ai_annotations_do_not_change_scoring_or_export_structure() -> None:
    run = SimpleNamespace(id=uuid4(), status="succeeded", source_account_ref="synthetic")
    content = generate_four_sheet_review(
        run=run,
        keyword_rows=[],
        ai_items=[
            {"keyword": "unmatched", "relevance": "low", "reason": "Review evidence"},
            {"keyword": "unmatched", "relevance": "high", "reason": "Duplicate"},
        ],
    )
    with ZipFile(BytesIO(content)) as workbook:
        names = workbook.read("xl/workbook.xml").decode("utf-8")
        assert len([name for name in SHEET_NAMES if name in names]) == 4
        assert len([name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")]) == 4
