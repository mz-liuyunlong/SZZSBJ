"""Five-sheet INTERNAL keyword review workbook; NEVER Walmart Bulk upload.

All rows project ONE persisted ai_kw_analysis_run + ai_kw_run_keyword snapshot.
Unapproved bidding policy, translation, listing copy and Walmart bulk templates
are deliberately not invented. Formula injection and CSV-style malicious prefixes
are escaped. No raw payloads or private credentials are exported.
"""

from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", X)
ET.register_namespace("r", R)

HEADERS_01 = (
    "关键词",
    "关键词中文意思",
    "关键词类型",
    "核心词根",
    "页面承接情况",
    "冷启动投放潜力分",
    "词质说明",
    "投放等级",
    "后续处理路径",
    "建议操作",
    "未上传原因",
    "后续手动优化建议出价",
    "是否进入手动Exact",
    "是否进入手动Broad",
)
SHEET_NAMES = (
    "01_最终投放总表",
    "02_词根Broad拓展",
    "03_风险与不投放",
    "04_广告结构_内部预览",
    "05_Listing优化建议",
)
HEADERS_04 = (
    "上传状态",
    "分析 Run ID",
    "关键词",
    "关键词类型",
    "账户范围",
    "Walmart Item ID",
    "规则版本 ID",
    "实际页面承接",
    "核心词根",
    "匹配分",
    "意图分",
    "页面分",
    "词根分",
    "数据分",
    "风险扣分",
    "总分",
    "投放等级",
    "Exact 内部候选",
    "Broad 内部候选",
    "Broad 角色",
    "建议优化出价（未执行）",
    "Exact 理由",
    "Broad 理由",
    "风险原因",
    "说明",
)


def _safe(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return "[详见后台来源证据]"
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _column_name(index: int) -> str:
    out = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(65 + remainder) + out
    return out


def _xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _make_sheet(headers: tuple[str, ...], rows: list[tuple]) -> bytes:
    ws = ET.Element(f"{{{X}}}worksheet")
    view = ET.SubElement(
        ET.SubElement(ws, f"{{{X}}}sheetViews"),
        f"{{{X}}}sheetView",
        {"workbookViewId": "0", "showGridLines": "0"},
    )
    ET.SubElement(
        view,
        f"{{{X}}}pane",
        {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"},
    )
    col_defs = ET.SubElement(ws, f"{{{X}}}cols")
    for i, header in enumerate(headers, 1):
        ET.SubElement(
            col_defs,
            f"{{{X}}}col",
            {
                "min": str(i),
                "max": str(i),
                "width": str(min(42, max(16, len(header) + 6))),
                "customWidth": "1",
            },
        )
    data = ET.SubElement(ws, f"{{{X}}}sheetData")
    all_rows = [headers] + rows
    for row_index, values in enumerate(all_rows, 1):
        row = ET.SubElement(
            data,
            f"{{{X}}}row",
            {"r": str(row_index), **({"ht": "27", "customHeight": "1"} if row_index == 1 else {})},
        )
        for i, raw in enumerate(values, 1):
            value = _safe(raw)
            if value == "":
                continue
            cell = ET.SubElement(
                row,
                f"{{{X}}}c",
                {"r": f"{_column_name(i)}{row_index}", "s": "1" if row_index == 1 else "0"},
            )
            if type(value) in (int, float) and not isinstance(value, bool):
                ET.SubElement(cell, f"{{{X}}}v").text = str(value)
            else:
                cell.set("t", "inlineStr")
                t = ET.SubElement(ET.SubElement(cell, f"{{{X}}}is"), f"{{{X}}}t")
                t.text = str(value)
                if str(value).startswith(" ") or str(value).endswith(" "):
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    ET.SubElement(
        ws, f"{{{X}}}autoFilter", {"ref": f"A1:{_column_name(len(headers))}{max(1, len(all_rows))}"}
    )
    return _xml(ws)


def _make_xlsx(sheets: list[tuple[str, tuple[str, ...], list[tuple]]]) -> bytes:
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as zipf:
        types = ET.Element(
            "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
        )
        ET.SubElement(
            types,
            "Default",
            {
                "Extension": "rels",
                "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
            },
        )
        ET.SubElement(types, "Default", {"Extension": "xml", "ContentType": "application/xml"})
        for path, typ in [
            (
                "/xl/workbook.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            ),
            (
                "/xl/styles.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
            ),
            ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ]:
            ET.SubElement(types, "Override", {"PartName": path, "ContentType": typ})
        for i in range(1, len(sheets) + 1):
            ET.SubElement(
                types,
                "Override",
                {
                    "PartName": f"/xl/worksheets/sheet{i}.xml",
                    "ContentType": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
                    ),
                },
            )
        zipf.writestr("[Content_Types].xml", _xml(types))
        rels = ET.Element("Relationships", xmlns=P)
        ET.SubElement(
            rels,
            "Relationship",
            {
                "Id": "rId1",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                "Target": "xl/workbook.xml",
            },
        )
        ET.SubElement(
            rels,
            "Relationship",
            {
                "Id": "rId2",
                "Type": "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
                "Target": "docProps/core.xml",
            },
        )
        zipf.writestr("_rels/.rels", _xml(rels))
        props = ET.Element(
            "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties"
        )
        ET.SubElement(props, "{http://purl.org/dc/elements/1.1/}creator").text = "SZZSBJ"
        ET.SubElement(
            props, "{http://purl.org/dc/elements/1.1/}description"
        ).text = "INTERNAL ANALYSIS - NOT WALMART BULK UPLOAD"
        zipf.writestr("docProps/core.xml", _xml(props))
        workbook = ET.Element(f"{{{X}}}workbook")
        collection = ET.SubElement(workbook, f"{{{X}}}sheets")
        wr = ET.Element("Relationships", xmlns=P)
        for i, (name, headers, rows) in enumerate(sheets, 1):
            ET.SubElement(
                collection,
                f"{{{X}}}sheet",
                {"name": name, "sheetId": str(i), f"{{{R}}}id": f"rId{i}"},
            )
            ET.SubElement(
                wr,
                "Relationship",
                {
                    "Id": f"rId{i}",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                    "Target": f"worksheets/sheet{i}.xml",
                },
            )
            zipf.writestr(f"xl/worksheets/sheet{i}.xml", _make_sheet(headers, rows))
        ET.SubElement(
            wr,
            "Relationship",
            {
                "Id": f"rId{len(sheets) + 1}",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
                "Target": "styles.xml",
            },
        )
        zipf.writestr("xl/workbook.xml", _xml(workbook))
        zipf.writestr("xl/_rels/workbook.xml.rels", _xml(wr))
        # 2 cell styles: normal and navy header. All content cells wrap.
        styles = ET.Element(f"{{{X}}}styleSheet")
        fonts = ET.SubElement(styles, f"{{{X}}}fonts", {"count": "2"})
        f = ET.SubElement(fonts, f"{{{X}}}font")
        ET.SubElement(f, f"{{{X}}}sz", {"val": "10"})
        ET.SubElement(f, f"{{{X}}}name", {"val": "Microsoft YaHei"})
        f = ET.SubElement(fonts, f"{{{X}}}font")
        ET.SubElement(f, f"{{{X}}}b")
        ET.SubElement(f, f"{{{X}}}color", {"rgb": "FFFFFFFF"})
        ET.SubElement(f, f"{{{X}}}sz", {"val": "10"})
        fills = ET.SubElement(styles, f"{{{X}}}fills", {"count": "3"})
        ET.SubElement(
            ET.SubElement(fills, f"{{{X}}}fill"), f"{{{X}}}patternFill", {"patternType": "none"}
        )
        ET.SubElement(
            ET.SubElement(fills, f"{{{X}}}fill"), f"{{{X}}}patternFill", {"patternType": "gray125"}
        )
        solid = ET.SubElement(
            ET.SubElement(fills, f"{{{X}}}fill"), f"{{{X}}}patternFill", {"patternType": "solid"}
        )
        ET.SubElement(solid, f"{{{X}}}fgColor", {"rgb": "FF203A59"})
        ET.SubElement(solid, f"{{{X}}}bgColor", {"indexed": "64"})
        borders = ET.SubElement(styles, f"{{{X}}}borders", {"count": "1"})
        ET.SubElement(borders, f"{{{X}}}border")
        xfs = ET.SubElement(styles, f"{{{X}}}cellStyleXfs", {"count": "1"})
        ET.SubElement(
            xfs, f"{{{X}}}xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"}
        )
        xfs = ET.SubElement(styles, f"{{{X}}}cellXfs", {"count": "2"})
        for fontid, fillid in ((0, 0), (1, 2)):
            xf = ET.SubElement(
                xfs,
                f"{{{X}}}xf",
                {
                    "numFmtId": "0",
                    "fontId": str(fontid),
                    "fillId": str(fillid),
                    "borderId": "0",
                    "xfId": "0",
                    "applyAlignment": "1",
                },
            )
            ET.SubElement(xf, f"{{{X}}}alignment", {"vertical": "top", "wrapText": "1"})
        cs = ET.SubElement(styles, f"{{{X}}}cellStyles", {"count": "1"})
        ET.SubElement(cs, f"{{{X}}}cellStyle", {"name": "Normal", "xfId": "0", "builtinId": "0"})
        zipf.writestr("xl/styles.xml", _xml(styles))
    return out.getvalue()


def generate_internal_workbook(*, run, keyword_rows: list[tuple[object, str]]) -> bytes:
    """keyword_rows: one (AiKwRunKeyword, canonical_keyword) pair per row.

    This is an internal analysis projection only. Never store as official export.
    """
    if run.status not in ("succeeded", "blocked"):
        raise ValueError("ANALYSIS_NOT_FINALIZED")
    if any(
        row.source_account_ref != run.source_account_ref or row.run_id != run.id
        for row, _keyword in keyword_rows
    ):
        raise ValueError("CROSS_ACCOUNT_EXPORT_DENIED")
    if len(keyword_rows) > 20000:
        raise ValueError("EXPORT_TOO_LARGE")
    base = []
    roots = []
    risks = []
    listing = []
    ad_preview = []
    for row, keyword in keyword_rows:
        status = "人工复核" if row.decision_status == "review" else row.decision_status
        reason = "; ".join(row.risk_reasons_json or []) or "; ".join(
            filter(None, (row.exact_reason, row.broad_reason))
        )
        path = "待复核" if row.score is None else "内部分析完成，待人工确认"
        base.append(
            (
                keyword,
                "",
                row.keyword_primary_type or "人工确认词",
                row.core_root or "",
                row.page_coverage or "页面看不出来",
                row.score,
                row.quality_note or "缺少已核实的完整评分证据",
                row.allocation_grade or "候选复查",
                path,
                "补齐证据；禁止直接上传" if row.score is None else "审核 Exact/Broad 与风险",
                reason,
                row.suggested_optimization_bid,
                "是" if row.exact_selected else "否",
                "是" if row.broad_selected else "否",
            )
        )
        if row.core_root or row.broad_selected:
            roots.append(
                (
                    keyword,
                    row.core_root or "",
                    row.broad_role or "",
                    "是" if row.broad_selected else "否",
                    row.broad_reason or "需审核词根语义与扩词风险",
                )
            )
        if (
            row.hard_risk
            or row.risk_reasons_json
            or row.score is None
            or row.decision_status != "ready"
        ):
            risks.append(
                (
                    keyword,
                    row.keyword_primary_type or "人工确认词",
                    "是" if row.hard_risk else "未证实",
                    reason,
                    status,
                    "仅复核，不是自动否定词指令",
                )
            )
        if row.page_coverage not in ("标题已埋词", "详情/属性已埋词"):
            listing.append(
                (
                    keyword,
                    row.page_coverage or "页面看不出来",
                    "待人工核对真实商品事实与页面文本；不得自动改写 Listing",
                )
            )
        ad_preview.append(
            (
                "禁止上传",
                str(run.id),
                keyword,
                row.keyword_primary_type,
                run.source_account_ref,
                getattr(run, "item_id", None),
                getattr(run, "rule_version_id", None),
                row.page_coverage,
                row.core_root,
                getattr(row, "match_points", None),
                getattr(row, "intent_points", None),
                getattr(row, "page_points", None),
                getattr(row, "root_points", None),
                getattr(row, "data_points", None),
                getattr(row, "risk_points", None),
                row.score,
                row.allocation_grade,
                "是" if row.exact_selected else "否",
                "是" if row.broad_selected else "否",
                row.broad_role,
                row.suggested_optimization_bid,
                row.exact_reason,
                row.broad_reason,
                reason,
                "内部分析投影；不是 Walmart 官方 Bulk 模板",
            )
        )
    return _make_xlsx(
        [
            (SHEET_NAMES[0], HEADERS_01, base),
            (SHEET_NAMES[1], ("关键词", "核心词根", "角色", "Broad入选", "未入选/复核原因"), roots),
            (SHEET_NAMES[2], ("关键词", "类型", "已证明硬风险", "原因", "状态", "处理边界"), risks),
            (
                SHEET_NAMES[3],
                HEADERS_04,
                ad_preview
                or [
                    (
                        "禁止上传",
                        str(run.id),
                        *([""] * 22),
                        "内部分析版；没有关键词可投影，不是 Walmart 官方 Bulk 模板",
                    )
                ],
            ),
            (SHEET_NAMES[4], ("关键词", "实际页面承接", "优化建议"), listing),
        ]
    )
