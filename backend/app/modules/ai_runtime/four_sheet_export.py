"""One four-sheet AI review export based on immutable persisted keyword decisions.

AI annotations never re-score the deterministic keyword source of truth.
No Walmart Bulk upload is created or authorized by this export.
"""

from __future__ import annotations

from app.modules.ai_runtime.listing_recommendations import create_listing_actions
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


def generate_four_sheet_review(
    *,
    run,
    keyword_rows: list[tuple[object, str]],
    ai_items: list[dict] | None = None,
    listing_draft: dict | None = None,
) -> bytes:
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
    # Semantic annotations inform manual review but never change immutable scores,
    # P-grades, advertising eligibility, bids, or the source keyword vocabulary.
    advisory = {}
    for item in ai_items or []:
        keyword = str(item.get("keyword") or "").casefold().strip()
        if keyword and keyword not in advisory:
            advisory[keyword] = item
    if advisory:
        columns = {name: i for i, name in enumerate(HEADERS_01)}
        updated = []
        for row in sheets[0][2]:
            cells = list(row)
            match = advisory.get(str(cells[columns["关键词"]]).casefold().strip())
            if match:
                translation = str(match.get("translation") or "").strip()
                translation_index = columns["关键词中文意思"]
                if translation and len(translation) <= 100:
                    cells[translation_index] = translation
                relevance = str(match.get("relevance") or "review")[:24]
                reason = str(match.get("reason") or "")[:180].replace("\\n", " ")
                prefix = "AI语义复核（非投放依据）: " + relevance
                note = prefix + ("；" + reason if reason else "")
                index = columns["词质说明"]
                cells[index] = (str(cells[index] or "") + "；" + note)[:800]
            updated.append(tuple(cells))
        sheets[0] = (sheets[0][0], sheets[0][1], updated)
    headers_05, rows_05 = create_listing_actions(sheets[0][1], sheets[0][2], draft=listing_draft)
    sheets[3] = (SHEET_NAMES[3], headers_05, rows_05)
    return _make_xlsx(sheets, header_fill=False)
