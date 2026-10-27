"""Pure V1.0 export tests. No marketplace upload or OpenAI API call."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from app.modules.ai_runtime.v1_bulk_workbook import (
    SHEET_NAMES,
    V1ConfirmedConfig,
    create_v1_workbook,
)
from app.modules.keyword_planning.internal_export import HEADERS_01


def _config(**overrides) -> V1ConfirmedConfig:
    values = {
        "item_id": "123456789",
        "sku": "TEST-SKU",
        "owner_initials": "AB",
        "product_facts_confirmed": True,
        "rule_version_published": True,
        "user_confirmed_generation": True,
        "walmart_template_verified": True,
        "start_date": "10/27/2026",
    }
    values.update(overrides)
    return V1ConfirmedConfig(**values)


def _row(keyword: str, grade: str = "P0", *, exact: bool = True) -> tuple:
    return (
        keyword,
        "中文直译",
        "核心本体词",
        keyword,
        "标题已埋词",
        91,
        "已核实",
        grade,
        "审核",
        "测试",
        "",
        "",
        "是" if exact else "否",
        "否",
    )


def test_v1_five_sheet_export_contains_expected_source_keywords() -> None:
    content = create_v1_workbook(HEADERS_01, [_row("storage organizer")], _config())
    with ZipFile(BytesIO(content)) as workbook:
        xml = workbook.read("xl/workbook.xml").decode("utf-8")
        for name in SHEET_NAMES:
            assert name in xml
        bulk = workbook.read("xl/worksheets/sheet4.xml").decode("utf-8")
        assert "storage organizer" in bulk
        assert "TEST-SKU" in bulk
        assert "123456789" in bulk


def test_v1_rejects_missing_explicit_confirmation() -> None:
    with pytest.raises(ValueError, match="V1_GENERATION_NOT_AUTHORIZED"):
        create_v1_workbook(
            HEADERS_01, [_row("storage organizer")],
            _config(user_confirmed_generation=False),
        )


def test_v1_prevents_exact_quota_overflow() -> None:
    rows = [_row(f"term {i}", grade="P0") for i in range(21)]
    with pytest.raises(ValueError, match="V1_GRADE_QUOTA_EXCEEDED"):
        create_v1_workbook(HEADERS_01, rows, _config())


def test_v1_prevents_unreviewed_score_becoming_eligible() -> None:
    row = list(_row("unverified"))
    row[5] = ""
    with pytest.raises(ValueError, match="V1_UNVERIFIED_SCORE"):
        create_v1_workbook(HEADERS_01, [tuple(row)], _config())


def test_v1_rejects_identical_raw_keyword_rows() -> None:
    with pytest.raises(ValueError, match="V1_DUPLICATE_OR_EMPTY_KEYWORD"):
        create_v1_workbook(HEADERS_01, [_row("hello"), _row("hello")], _config())
