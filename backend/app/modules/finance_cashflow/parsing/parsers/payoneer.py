# ruff: noqa: E501, E402, UP031
"""派安盈 Transactions CSV：时间列为 Time zone 列所示时区（实测 UTC），业务日折算 Asia/Shanghai。"""

from __future__ import annotations

import re
from decimal import Decimal

from ..model import ParsedRow
from ..normalize import to_decimal
from ..readers import cell

PARTY = re.compile(
    r"(?:Payment to|Payment from|Transfer from connected account|Card charge \()\s*(.+?)\)?$"
)


def parse(det, seed):
    rows = det.csv_rows
    hdr = rows[0]
    ix = {h: i for i, h in enumerate(hdr)}

    def g(r, k):
        i = ix.get(k)
        return cell(r[i]) if i is not None and i < len(r) else ""

    out = []
    for ri, r in enumerate(rows[1:], start=2):
        if not r or g(r, "Status") != "Completed":
            continue  # 未完成交易不入（数量记在 dq warnings，由 store 统计）
        c, d = to_decimal(g(r, "Credit amount")), to_decimal(g(r, "Debit amount"))
        amt = (c or Decimal(0)) + (d or Decimal(0))
        if not amt:
            continue
        desc = g(r, "Description")
        m = PARTY.search(desc)
        party = m.group(1).strip(" )") if m else ""
        acc_tail = re.search(r"\((\d{3,})\)\s*$", desc)
        out.append(
            ParsedRow(
                det.account_key,
                g(r, "Transaction date"),
                g(r, "Transaction time"),
                g(r, "Time zone") or "UTC",
                str(amt),
                g(r, "Currency") or "USD",
                g(r, "Running balance") or None,
                party,
                acc_tail.group(1) if acc_tail else "",
                desc,
                "",
                "",
                ri,
            )
        )
    return out
