# ruff: noqa: E501, E402, UP031
"""中行企业网银「交易明细」：一个查询账号一份导出，按「交易货币」拆人民币户 / 外币户。"""

from __future__ import annotations

from ..model import ParsedRow, RejectFile
from ._common import blank, getter, header_index

TZ = "Asia/Shanghai"


import re as _re

_DATE = _re.compile(r"^\s*(\d{4}[-/.年]?\d{1,2}[-/.月]?\d{1,2}|\d{5}(\.0+)?)")


def parse(det, seed):
    _name, rows = det.sheets[0]
    ix = header_index(rows[det.header_row])
    for need in ("交易类型", "交易日期", "交易金额", "交易货币"):
        if need not in ix:
            raise RejectFile("中行交易明细缺列：%s" % need)
    g = getter(ix)
    out = []
    for ri, r in enumerate(rows[det.header_row + 1 :], start=det.header_row + 2):
        if blank(r) or g(r, "交易金额") == "":
            continue
        if not _DATE.match(g(r, "交易日期")):  # 重复表头 / 汇总 / 页脚：跳过，不拒文件
            det.skipped_rows += 1
            continue
        cur = g(r, "交易货币") or "CNY"
        acct = seed.boc(det.inquiry_account, cur)
        if acct is None:
            raise RejectFile("中行导出里有未登记币种：%s" % cur)
        amt = g(r, "交易金额").replace(",", "")
        outgoing = g(r, "交易类型") == "往账" or amt.startswith("-")
        amt = amt.lstrip("-+")
        signed = ("-" + amt) if outgoing else amt
        party = g(r, "收款人名称") if outgoing else g(r, "付款人名称")
        party_acc = g(r, "收款人账号") if outgoing else g(r, "付款人账号")
        desc = " / ".join(
            x for x in (g(r, "业务类型"), g(r, "用途"), g(r, "交易附言"), g(r, "摘要")) if x
        )
        out.append(
            ParsedRow(
                acct.account_key,
                g(r, "交易日期"),
                g(r, "交易时间"),
                TZ,
                signed,
                cur,
                g(r, "交易后余额") or None,
                party,
                party_acc,
                desc,
                "",
                g(r, "交易流水号"),
                ri,
            )
        )
    return out
