# ruff: noqa: E501, E402, UP031
"""PingPong 账单明细：一张导出含多个用户 / 子账户。
只入本公司用户编号下的账户（专用户按币种、店铺户按账号 Id，必须已登记，否则整文件拒绝）；
其他主体店铺行不入标准层，但其「资金归集至专用账户」出账 = 毛额，用来把专用户「专用账户入账」（净额）
拆成 回款全额 + PingPong 归集手续费 两行，余额链保持连续。"""

from __future__ import annotations

import re

from ..model import ParsedRow, RejectFile
from ..normalize import excel_serial_to_datetime, parse_local_datetime, to_decimal
from ._common import blank, getter, header_index

TZ = "Asia/Shanghai"


def _id(s: str) -> str:
    return re.sub(r"\.0$", "", s or "")


def _local(raw: str):
    if re.fullmatch(r"\d+(\.\d+)?", raw or ""):
        return excel_serial_to_datetime(raw)
    d, _, t = (raw or "").partition(" ")
    return parse_local_datetime(d, t)


def parse(det, seed):
    _name, rows = det.sheets[0]
    hi = next(i for i, r in enumerate(rows) if any((x or "") == "出账/入账" for x in r))
    ix = header_index(rows[hi])
    g = getter(ix)
    # 付款带「费用」（Rocky 11-10：出账金额里含 PingPong 手续费）：
    # 写进备注，日记账提示一键拆出手续费。
    fee_key = next((key for key in ix if key.startswith("费用")), None)
    users = seed.pp_user_nos()
    gross = {}
    for r in rows[hi + 1 :]:
        if (
            not blank(r)
            and g(r, "业务类型") == "资金归集至专用账户"
            and g(r, "出账/入账") == "出账"
        ):
            v = to_decimal(g(r, "出/入账金额"))
            if v is not None:
                gross[g(r, "订单号")] = abs(v)
    out = []
    for ri, r in enumerate(rows[hi + 1 :], start=hi + 2):
        if blank(r):
            continue
        user = _id(g(r, "用户编号"))
        if user not in users:
            continue  # 其他主体：只留在 RAW
        v = to_decimal(g(r, "出/入账金额"))
        if v is None:
            continue
        amt = v if g(r, "出账/入账") == "入账" else -abs(v)
        cur = g(r, "出/入账币种") or "USD"
        acc_id = _id(g(r, "账号Id"))
        acct = seed.pp_main(user, cur) if acc_id.startswith(user) else seed.pp_store(acc_id)
        if acct is None:
            raise RejectFile(
                "PingPong 账户未登记（%s 尾号 %s）"
                % ("专用户 " + cur if acc_id.startswith(user) else "店铺户", acc_id[-4:])
            )
        ptype, plat = g(r, "业务类型"), g(r, "平台")
        desc = ptype + ((" " + plat) if plat not in ("", "/") else "")
        bal = to_decimal(g(r, "账户余额"))
        party = g(r, "交易对手方账户名")
        local = _local(g(r, "创建时间"))
        ref = g(r, "流水号")
        gv = gross.get(g(r, "订单号")) if ptype == "专用账户入账" and amt > 0 else None
        if gv is not None and gv > amt:
            fee = gv - amt
            out.append(
                ParsedRow(
                    acct.account_key,
                    "",
                    "",
                    TZ,
                    str(gv),
                    cur,
                    None if bal is None else str(bal + fee),
                    party,
                    g(r, "交易对手方账号"),
                    desc,
                    g(r, "附言"),
                    ref,
                    ri,
                    local_dt=local,
                )
            )
            out.append(
                ParsedRow(
                    acct.account_key,
                    "",
                    "",
                    TZ,
                    str(-fee),
                    cur,
                    None if bal is None else str(bal),
                    "PingPong",
                    "",
                    "PingPong 归集手续费",
                    "",
                    ref + ":fee",
                    ri,
                    local_dt=local,
                )
            )
            continue
        memo = g(r, "附言")
        fee_paid = to_decimal(g(r, fee_key)) if fee_key and amt < 0 else None
        if fee_paid is not None and fee_paid > 0:
            memo = ("%s；" % memo if memo else "") + "PingPong 手续费 %.2f" % fee_paid
        out.append(
            ParsedRow(
                acct.account_key,
                "",
                "",
                TZ,
                str(amt),
                cur,
                None if bal is None else str(bal),
                party,
                g(r, "交易对手方账号"),
                desc,
                memo,
                ref,
                ri,
                local_dt=local,
            )
        )
    return out
