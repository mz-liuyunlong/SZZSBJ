# ruff: noqa: E501, E402, UP031
"""深通村镇银座「交易明细查询列表」。"""

from __future__ import annotations

from decimal import Decimal

from ..model import ParsedRow, RejectFile
from ..normalize import to_decimal
from ._common import blank, getter, header_index

TZ = "Asia/Shanghai"


import re as _re

_DATE = _re.compile(r"^\s*(\d{4}[-/.年]?\d{1,2}[-/.月]?\d{1,2}|\d{5}(\.0+)?)")


def parse(det, seed):
    _name, rows = det.sheets[0]
    if det.header_row < 0:
        raise RejectFile("银座交易明细缺表头（交易时间 / 支出 / 收入）")
    ix = header_index(rows[det.header_row])
    g = getter(ix)
    out = []
    for ri, r in enumerate(rows[det.header_row + 1 :], start=det.header_row + 2):
        if blank(r):
            continue
        if not _DATE.match(g(r, "交易时间")):  # 汇总金额等页脚行：跳过
            det.skipped_rows += 1
            continue
        vo, vi = to_decimal(g(r, "支出")), to_decimal(g(r, "收入"))
        if vo is None and vi is None:
            continue
        amt = (vi or Decimal(0)) - abs(vo or Decimal(0))
        dt_raw = g(r, "交易时间")
        date_raw, _, time_raw = dt_raw.partition(" ")
        out.append(
            ParsedRow(
                det.account_key,
                date_raw,
                time_raw,
                TZ,
                str(amt),
                "CNY",
                g(r, "余额") or None,
                g(r, "对方账户名"),
                g(r, "对方账号"),
                " / ".join(x for x in (g(r, "摘要"), g(r, "附言")) if x),
                "",
                g(r, "交易流水号"),
                ri,
            )
        )
    return out
