# ruff: noqa: E501, E402, UP031
"""line_uid = sha1(account_key | business_date | source_time(UTC) | amount | balance_after | source_ref 全值 | description 脱敏前原文 | dup_ordinal)[:16]"""

from __future__ import annotations

import hashlib
from collections import Counter

from .model import Line
from .normalize import fmt_amount


def base_key(line: Line) -> str:
    return "|".join(
        (
            line.account_key,
            line.business_date.isoformat(),
            line.source_time_utc.isoformat() if line.source_time_utc else "",
            fmt_amount(line.amount),
            fmt_amount(line.balance_after),
            line.source_ref_full,
            line.description_raw,
        )
    )


def assign_uids(lines: list) -> None:
    """同一文件内同键按出现顺序编 dup_ordinal（1、2、…），再算 uid。调用方保证 lines 为文件内原始顺序。"""
    seen: Counter = Counter()
    for ln in lines:
        k = base_key(ln)
        seen[k] += 1
        ln.dup_ordinal = seen[k]
        ln.line_uid = hashlib.sha1(("%s|%d" % (k, ln.dup_ordinal)).encode("utf-8")).hexdigest()[:16]
