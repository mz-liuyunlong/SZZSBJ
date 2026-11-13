"""审批单来自哪家公司的飞书（Rocky 2026-11-13：第二家公司是另一个飞书企业，进同一张表）。

- 主公司：FEISHU_APP_ID / FEISHU_APP_SECRET + FINANCE_APPROVAL_CODES，单号原样。
- 第二家（env 前缀 YC_）：YC_FEISHU_APP_ID / YC_FEISHU_APP_SECRET + YC_FINANCE_APPROVAL_CODES，
  单号前加「YC-」：两个飞书的流水号都是「日期 + 当天第几单」，会撞号，日记账挂单又按单号挂。
- 配对按公司分：日记账账户的「主体」在 YC_FINANCE_ENTITIES 里的，流水只配第二家的审批单，
  其余账户只配主公司的。没配 YC_FINANCE_ENTITIES 时，第二家的审批单不自动配，只能手动挂。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.core.config import Settings

ORG_MAIN: Final = "zsbj"
ORG_YC: Final = "yc"
YC_PREFIX: Final = "YC-"


def yc_enabled(settings: Settings) -> bool:
    """配了第二家的审批定义编码才拉它（凭证缺了在拉的时候报错，不在这里静默跳过）。"""
    return bool((settings.yc_finance_approval_codes or "").strip())


def org_serial(org: str, raw: str) -> str:
    """存进表里的单号：第二家加 YC- 前缀；已经带前缀的不重复加。"""
    if org != ORG_YC or not raw or raw.startswith(YC_PREFIX):
        return raw
    return f"{YC_PREFIX}{raw}"


def org_label(settings: Settings, org: str) -> str:
    return settings.yc_finance_org_label if org == ORG_YC else settings.finance_approval_org_label


def org_serials(org: str, raw: str) -> str:
    """关联单号可能是逗号隔开的几张：逐个加前缀。"""
    return ",".join(org_serial(org, item.strip()) for item in raw.split(",") if item.strip())


def _split(raw: str | None) -> set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


def account_orgs(settings: Settings, accounts: Iterable[tuple[str, str]]) -> dict[str, str]:
    """账户 → 公司。accounts = (account_key, 主体)；主体在 YC_FINANCE_ENTITIES 里的算第二家。"""
    yc_entities = _split(settings.yc_finance_entities)
    return {
        account_key: ORG_YC if entity.strip() in yc_entities else ORG_MAIN
        for account_key, entity in accounts
    }
