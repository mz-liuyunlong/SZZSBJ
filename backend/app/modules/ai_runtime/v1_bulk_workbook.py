"""V1.0 Walmart Bulk workbook with immutable 01 decisions and explicit confirmation.

No automatic ad creation. Rejects missing reviewed evidence, incomplete listing,
unverified template, unconfirmed product facts and quota violations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from app.modules.ai_runtime.listing_recommendations import BLOCKED_TYPES, create_listing_actions
from app.modules.ai_runtime.v1_review_sheets import (
    RISK_HEADERS,
    ROOT_HEADERS,
    project_v1_review_sheets,
)
from app.modules.keyword_planning.internal_export import HEADERS_01, _make_xlsx

HEADERS_04 = (
    "前台相关度检查提示",
    "Record Type",
    "Operation",
    "Campaign Id",
    "Ad Group Id",
    "Campaign Name",
    "Ad Group Name",
    "Start Date",
    "End Date",
    "Campaign Targeting Type",
    "Total Budget",
    "Daily Budget",
    "Bid",
    "Suggested Bid",
    "Item Id",
    "Item Name",
    "Keyword",
    "Keyword Id",
    "Match Type",
    "Status",
    "Placement Inclusion Type",
    "Placement Bid Multiplier Type",
    "Placement Bid Multiplier",
    "Platform Bid Multiplier Type",
    "Platform Bid Multiplier",
)
SHEET_NAMES = (
    "01_最终投放总表",
    "02_词根与Broad拓展规则",
    "03_风险词与不投放词",
    "04_Walmart上传表",
    "05_Listing优化建议",
)


@dataclass(frozen=True)
class V1ConfirmedConfig:
    item_id: str
    sku: str
    owner_initials: str
    product_facts_confirmed: bool
    rule_version_published: bool
    user_confirmed_generation: bool
    walmart_template_verified: bool
    manual_budget: Decimal = Decimal("10")
    auto_budget: Decimal = Decimal("10")
    manual_bid: Decimal = Decimal("0.31")
    auto_bid: Decimal = Decimal("0.21")
    start_date: str | None = None

    def validate(self) -> None:
        if not all(
            (
                self.product_facts_confirmed,
                self.rule_version_published,
                self.user_confirmed_generation,
                self.walmart_template_verified,
            )
        ):
            raise ValueError("V1_GENERATION_NOT_AUTHORIZED")
        if not all((self.item_id.isdigit(), self.sku.strip(), self.owner_initials.strip())):
            raise ValueError("V1_PRODUCT_IDENTITY_INVALID")
        if not self.owner_initials.isascii() or len(self.owner_initials) > 8:
            raise ValueError("V1_OWNER_INVALID")
        for number in (self.manual_budget, self.auto_budget, self.manual_bid, self.auto_bid):
            if not number.is_finite() or number <= 0:
                raise ValueError("V1_BID_OR_BUDGET_INVALID")
        if self.start_date is not None:
            datetime.strptime(self.start_date, "%m/%d/%Y")


def _structure(
    hint: str,
    record: str,
    campaign: str,
    group: str,
    *,
    keyword: str = "",
    match: str = "",
    bid: str = "",
    item: str = "",
    budget: str = "",
    start: str = "",
    targeting: str = "",
) -> tuple[str, ...]:
    values = dict.fromkeys(HEADERS_04, "")
    values.update(
        {
            "前台相关度检查提示": hint,
            "Record Type": record,
            "Operation": "Create",
            "Campaign Name": campaign,
            "Ad Group Name": group,
            "Start Date": start,
            "Campaign Targeting Type": targeting,
            "Daily Budget": budget,
            "Bid": bid,
            "Item Id": item,
            "Keyword": keyword,
            "Match Type": match,
            "Status": "Enabled",
        }
    )
    return tuple(values[key] for key in HEADERS_04)


def create_v1_workbook(
    headers_01: tuple[str, ...],
    rows_01: list[tuple],
    config: V1ConfirmedConfig,
    *,
    metadata: Mapping[str, Mapping[str, object]] | None = None,
    listing_draft: dict | None = None,
) -> bytes:
    config.validate()
    metadata = metadata or {}
    if headers_01 != HEADERS_01:
        raise ValueError("V1_SOURCE_SCHEMA_INVALID")
    col = {name: index for index, name in enumerate(headers_01)}
    exact = []
    broad = []
    root_count = 0
    tail_count = 0
    seen = set()
    grades = {"P0": 0, "P1": 0, "P2": 0}
    for row in rows_01:
        if len(row) != 14:
            raise ValueError("V1_SOURCE_SCHEMA_INVALID")
        keyword = str(row[col["关键词"]]).strip()
        if not keyword or keyword.casefold() in seen:
            raise ValueError("V1_DUPLICATE_OR_EMPTY_KEYWORD")
        seen.add(keyword.casefold())
        grade = str(row[col["投放等级"]])
        score = row[col["冷启动投放潜力分"]]
        if score in ("", None) and grade in grades:
            raise ValueError("V1_UNVERIFIED_SCORE")
        if grade in grades:
            grades[grade] += 1
            minimum = {"P0": 85, "P1": 75, "P2": 60}[grade]
            if not isinstance(score, (int, float)) or score < minimum:
                raise ValueError("V1_GRADE_SCORE_MISMATCH")
        selected_exact = row[col["是否进入手动Exact"]] == "是"
        selected_broad = row[col["是否进入手动Broad"]] == "是"
        if selected_exact or selected_broad:
            if grade not in grades or not isinstance(score, (int, float)):
                raise ValueError("V1_INCONSISTENT_SELECTION")
            if str(row[col["关键词类型"]]) in BLOCKED_TYPES:
                raise ValueError("V1_RISK_KEYWORD_SELECTED")
            if row[col["页面承接情况"]] in ("页面看不出来", "页面不建议埋"):
                raise ValueError("V1_UNVERIFIED_PAGE_COVERAGE")
        if selected_exact:
            exact.append((grade, keyword))
        if selected_broad:
            role = str(metadata.get(keyword.casefold(), {}).get("broad_role") or "")
            if role not in ("root", "long_tail"):
                raise ValueError("V1_BROAD_ROLE_EVIDENCE_MISSING")
            broad.append((role, keyword))
            if role == "root":
                root_count += 1
            else:
                tail_count += 1
    if grades["P0"] > 5 or grades["P1"] > 10 or grades["P2"] > 30:
        raise ValueError("V1_GRADE_QUOTA_EXCEEDED")
    if len(exact) > 20 or len(broad) > 20:
        raise ValueError("V1_AD_QUOTA_EXCEEDED")
    if any(grade not in grades for grade, _ in exact):
        raise ValueError("V1_INCONSISTENT_SELECTION")
    if any(grade == "P2" for grade, _ in exact) and (
        sum(grade in ("P0", "P1") for grade, _ in exact)
        + sum(
            row[col["投放等级"]] in ("P0", "P1") and row[col["是否进入手动Exact"]] != "是"
            for row in rows_01
        )
        > 20
    ):
        raise ValueError("V1_P2_BEFORE_PRIORITY_SELECTION")
    if root_count > 5 or tail_count > 15:
        raise ValueError("V1_BROAD_ROLE_QUOTA_EXCEEDED")
    start = config.start_date or datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%m/%d/%Y")
    manual = f"{config.sku}-手动-{config.owner_initials}"
    automatic = f"{config.sku}-自动-{config.owner_initials}"
    rows04 = [
        _structure(
            "【结构行】检查Campaign、日期、预算",
            "Campaign",
            manual,
            "",
            budget=str(config.manual_budget),
            start=start,
            targeting="Manual",
        ),
        _structure("【结构行】检查Campaign、Ad Group命名", "Ad Group", manual, "Exact"),
    ]
    for grade, kw in exact:
        rows04.append(
            _structure(
                f"【{grade} Exact】上传前在Walmart前台确认同类商品",
                "Keyword",
                manual,
                "Exact",
                keyword=kw,
                match="exact",
                bid=str(config.manual_bid),
                item=config.item_id,
            )
        )
    rows04.append(_structure("【结构行】检查Campaign、Ad Group命名", "Ad Group", manual, "Broad"))
    for recorded_role, kw in broad:
        role = "Broad词根" if recorded_role == "root" else "Broad长尾"
        rows04.append(
            _structure(
                f"【{role}】前台检查相关度及跑偏风险",
                "Keyword",
                manual,
                "Broad",
                keyword=kw,
                match="broad",
                bid=str(config.manual_bid),
                item=config.item_id,
            )
        )
    rows04.extend(
        [
            _structure(
                "【auto】检查Item ID与预算",
                "Campaign",
                automatic,
                "",
                budget=str(config.auto_budget),
                start=start,
                targeting="auto",
            ),
            _structure("【auto】检查Item ID与预算", "Ad Group", automatic, "auto"),
        ]
    )
    rows04.append(
        _structure(
            "【auto】检查Item ID与默认竞价",
            "Item",
            automatic,
            "auto",
            item=config.item_id,
            bid=str(config.auto_bid),
        )
    )
    roots, risk = project_v1_review_sheets(headers_01, rows_01, metadata)
    headers05, listing = create_listing_actions(headers_01, rows_01, draft=listing_draft)
    return _make_xlsx(
        [
            (SHEET_NAMES[0], headers_01, rows_01),
            (SHEET_NAMES[1], ROOT_HEADERS, roots),
            (SHEET_NAMES[2], RISK_HEADERS, risk),
            (SHEET_NAMES[3], HEADERS_04, rows04),
            (SHEET_NAMES[4], headers05, listing),
        ],
        header_fill=False,
    )


def read_review_primary_sheet(workbook: bytes) -> list[tuple]:
    """Recover the locked 14-column 01 view without recalculating any score."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(BytesIO(workbook)) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for record in root.findall(f".//{namespace}sheetData/{namespace}row"):
        cells = [""] * len(HEADERS_01)
        for cell in record.findall(f"{namespace}c"):
            column = cell.get("r", "").rstrip("0123456789")
            position = 0
            for character in column:
                position = position * 26 + ord(character) - 64
            if not 1 <= position <= len(HEADERS_01):
                raise ValueError("V1_SOURCE_SCHEMA_INVALID")
            content = cell.find(f"{namespace}is/{namespace}t")
            if content is None:
                content = cell.find(f"{namespace}v")
            value = content.text if content is not None and content.text is not None else ""
            if cell.get("t") != "inlineStr" and value != "":
                try:
                    value = float(value) if "." in value else int(value)
                except ValueError:
                    pass
            cells[position - 1] = value
        rows.append(tuple(cells))
    if not rows or rows[0] != HEADERS_01:
        raise ValueError("V1_SOURCE_SCHEMA_INVALID")
    return rows[1:]
