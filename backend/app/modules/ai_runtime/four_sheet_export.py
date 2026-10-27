"""One four-sheet AI review export based on immutable persisted keyword decisions.

AI annotations never re-score the deterministic keyword source of truth.
No Walmart Bulk upload is created or authorized by this export.
"""

from __future__ import annotations

from app.modules.keyword_planning.internal_export import (
    HEADERS_01,
    _make_xlsx,
    generate_internal_workbook,
)

SHEET_NAMES = (
    "01_最终投放总表",
    "02_词根与Broad拓展规则",
    "03_风险词与不投放词",
    "05_Listing编写建议",
)


def generate_four_sheet_review(*, run, keyword_rows: list[tuple[object, str]]) -> bytes:
    """Project the existing immutable analysis; never recalculate or invent scores.

    The source generator already enforces account boundaries, size limits,
    export escaping and persisted decision invariants. Four-sheet mode removes
    only the internal preview sheet without altering source judgments.
    """
    from io import BytesIO
    from xml.etree import ElementTree as ET
    from zipfile import ZipFile

    if run.status not in ("succeeded", "blocked"):
        raise ValueError("ANALYSIS_NOT_FINALIZED")
    original = generate_internal_workbook(run=run, keyword_rows=keyword_rows)
    x = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with ZipFile(BytesIO(original)) as source:
        # Decode typed cell values from the existing validated workbook, preserving
        # the exact row order and content, not deriving scoring in a second engine.
        from app.modules.keyword_planning.internal_export import SHEET_NAMES as ORIGINAL

        sheets = []
        positions = (0, 1, 2, 4)
        for position, name in zip(positions, SHEET_NAMES, strict=True):
            tree = ET.fromstring(source.read(f"xl/worksheets/sheet{position + 1}.xml"))
            rows = []
            for row in tree.findall(f".//{{{x}}}sheetData/{{{x}}}row"):
                values = []
                for cell in row.findall(f"{{{x}}}c"):
                    ref = cell.attrib["r"]
                    column = ref.rstrip("0123456789")
                    index = 0
                    for ch in column:
                        index = index * 26 + ord(ch) - 64
                    while len(values) < index:
                        values.append("")
                    node = cell.find(f"{{{x}}}is/{{{x}}}t")
                    if node is None:
                        node = cell.find(f"{{{x}}}v")
                    value = node.text if node is not None and node.text is not None else ""
                    if cell.get("t") != "inlineStr" and value != "":
                        try:
                            value = float(value) if "." in value else int(value)
                        except ValueError:
                            pass
                    values[index - 1] = value
                rows.append(tuple(values))
            if not rows:
                raise ValueError("INTERNAL_EXPORT_INVALID")
            sheets.append((name, tuple(rows[0]), rows[1:]))
    assert ORIGINAL[0] == SHEET_NAMES[0]
    assert sheets[0][1] == HEADERS_01
    return _make_xlsx(sheets, header_fill=False)
