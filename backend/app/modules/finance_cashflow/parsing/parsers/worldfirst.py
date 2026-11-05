# ruff: noqa: E501, E402, UP031
"""万里汇导出：主账号行（子账号昵称 = - / 空）带余额，子账号行不带。"""

from __future__ import annotations

from decimal import Decimal

from ..model import ParsedRow
from ..normalize import to_decimal
from ._common import blank, getter, header_index

TZ = "Asia/Shanghai"
CUR = {"美元": "USD", "人民币": "CNY"}


def parse(det, seed):
    _name, rows = det.sheets[0]
    hi = next(i for i, r in enumerate(rows) if any((x or "") == "子账号昵称" for x in r))
    g = getter(header_index(rows[hi]))
    out = []
    for ri, r in enumerate(rows[hi + 1 :], start=hi + 2):
        if blank(r):
            continue
        vin, vout = to_decimal(g(r, "入账金额")), to_decimal(g(r, "出账金额"))
        if vin is None and vout is None:
            continue
        amt = (vin or Decimal(0)) - abs(vout or Decimal(0))
        nick = g(r, "子账号昵称")
        main = nick in ("", "-")
        ptype, desc = g(r, "动账类型"), g(r, "描述")
        text = desc if (not ptype or desc.startswith(ptype)) else "%s-%s" % (ptype, desc)
        if not main:
            text += " / 子账号 " + nick
        out.append(
            ParsedRow(
                det.account_key,
                g(r, "交易创建日期"),
                g(r, "交易创建时间"),
                TZ,
                str(amt),
                CUR.get(g(r, "币种"), g(r, "币种") or "USD"),
                g(r, "余额") if main else None,
                g(r, "收款人名称") or g(r, "付款人名称"),
                "",
                text,
                g(r, "附言"),
                g(r, "交易号") + ("" if main else ":" + nick),
                ri,
            )
        )
    return out
