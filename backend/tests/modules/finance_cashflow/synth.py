# ruff: noqa: E501, E741, UP031
"""合成样本（全部虚构：账号 / 户名 / 金额都不是真实数据）。"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from app.modules.finance_cashflow.parsing.seed import Seed, SeedAccount

BOC_A, BOC_B = "100000000011", "100000000022"
YZ_NO = "600000000000099"
PP_USER = "999900000000000001"
PP_STORE = "STORE-ACC-0001"
OTHER_USER = "888800000000000002"


def seed() -> Seed:
    S = SeedAccount
    return Seed(
        [
            S(
                "BOC_CNY",
                "甲公司 · 中行人民币户",
                "甲",
                "CNY",
                "对公",
                "boc",
                "0011",
                {"inquiry_account": BOC_A, "currency": "CNY"},
            ),
            S(
                "BOC_USD",
                "甲公司 · 中行外币户",
                "甲",
                "USD",
                "对公",
                "boc",
                "0011",
                {"inquiry_account": BOC_A, "currency": "USD"},
            ),
            S(
                "ZSBJ_BOC",
                "乙公司 · 中行对公",
                "甲",
                "CNY",
                "对公",
                "boc",
                "0022",
                {"inquiry_account": BOC_B, "currency": "CNY"},
            ),
            S(
                "ZSBJ_BOC_USD",
                "乙公司 · 中行外币户",
                "甲",
                "USD",
                "对公",
                "boc",
                "0033",
                {"inquiry_account": BOC_B, "currency": "USD"},
            ),
            S(
                "ZSBJ_YZ",
                "乙公司 · 银座对公",
                "甲",
                "CNY",
                "对公",
                "shenzhen_rural_bank",
                "0099",
                {"account_no": YZ_NO},
            ),
            S(
                "PAYONEER",
                "派安盈 · 卖家户",
                "甲",
                "USD",
                "平台",
                "payoneer",
                "",
                {"feature": "seller"},
            ),
            S(
                "PAYONEER_FH",
                "派安盈 · 归集户",
                "甲",
                "USD",
                "平台",
                "payoneer",
                "",
                {"feature": "collector"},
            ),
            S("WORLDFIRST", "万里汇", "甲", "USD", "平台", "worldfirst", "", {}),
            S(
                "PINGPONG_MAIN_USD",
                "PingPong · 专用户 USD",
                "甲",
                "USD",
                "平台",
                "pingpong",
                "",
                {"user_no": PP_USER, "main": True},
            ),
            S(
                "PINGPONG_MAIN_CNH",
                "PingPong · 专用户 CNH",
                "甲",
                "CNH",
                "平台",
                "pingpong",
                "",
                {"user_no": PP_USER, "main": True},
            ),
            S(
                "PINGPONG_STORE_A",
                "PingPong · 店铺户 A",
                "甲",
                "USD",
                "平台",
                "pingpong",
                "",
                {"user_no": PP_USER, "account_id": PP_STORE},
            ),
        ]
    )


def xlsx(rows, extra_entries=0, pad_bytes=0) -> bytes:
    """最小 xlsx：inlineStr 文本；纯数字字符串写成数值单元格（<v>原文）。"""

    def col(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    xml_rows = []
    for ri, r in enumerate(rows, start=1):
        cells = []
        for ci, v in enumerate(r):
            if v is None or v == "":
                continue
            ref = "%s%d" % (col(ci), ri)
            if isinstance(v, (int,)) or (isinstance(v, str) and v.startswith("=n:")):
                num = str(v)[3:] if isinstance(v, str) else str(v)
                cells.append('<c r="%s"><v>%s</v></c>' % (ref, num))
            else:
                cells.append(
                    '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(v)))
                )
        xml_rows.append('<row r="%d">%s</row>' % (ri, "".join(cells)))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>%s</sheetData></worksheet>" % "".join(xml_rows)
    )
    wb = (
        '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    )
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        for i in range(extra_entries):
            z.writestr("xl/media/pad%d.bin" % i, b"x")
        if pad_bytes:
            z.writestr("xl/media/big.bin", b"\0" * pad_bytes)
    return bio.getvalue()


BOC_HEAD = [
    "交易类型[ Transaction Type]",
    "业务类型[ Business type]",
    "付款人账号[ Debit Account No.]",
    "付款人名称[ Payer's Name]",
    "收款人账号[ Payee's Account Number]",
    "收款人名称[ Payee's Name]",
    "交易日期[ Transaction Date]",
    "交易时间[ Transaction time]",
    "交易货币[ Trade Currency]",
    "交易金额[ Trade Amount]",
    "交易后余额[ After-transaction balance]",
    "交易流水号[ Transaction reference number]",
    "用途[ Purpose]",
    "交易附言[ Remark]",
    "摘要[ Reference]",
]


def boc(inquiry, data, range_=("20261001", "20261028")):
    rows = [[], ["查询账号[ Inquirer account]", inquiry], ["总笔数[ Total number]", str(len(data))]]
    if range_:
        rows.append(["查询时间范围[ Time Range]", "%s-%s" % range_])
    rows.append(BOC_HEAD)
    for d in data:  # d = (类型, 日期, 时间, 币种, 金额, 余额, 对方, 对方账号, 流水号, 用途)
        typ, date, time, cur, amt, bal, party, pacc, ref, purpose = d
        payer = ("甲方", pacc) if typ == "来账" else ("本公司", "x")
        payee = ("本公司", "x") if typ == "来账" else (party, pacc)
        if typ == "来账":
            payer = (party, pacc)
        rows.append(
            [
                typ,
                "转账",
                payer[1],
                payer[0],
                payee[1],
                payee[0],
                date,
                time,
                cur,
                amt,
                bal,
                ref,
                purpose,
                "",
                "",
            ]
        )
    return xlsx(rows)


def yz(account_no, data, range_=("2026-10-01", "2026-10-31")):
    rows = [["交易明细查询列表"], ["账号", account_no], ["账户名", "乙公司"], ["币种", "人民币"]]
    if range_:
        rows.append(["交易时间", "%s 至 %s" % range_])
    rows.append(
        [
            "交易时间",
            "支出",
            "收入",
            "余额",
            "对方账号",
            "对方账户名",
            "对方行名",
            "摘要",
            "附言",
            "交易流水号",
        ]
    )
    for d in data:  # (时间, 支出, 收入, 余额, 对方账号, 对方, 摘要, 流水号)
        t, out, inc, bal, pacc, party, summ, ref = d
        rows.append([t, out, inc, bal, pacc, party, "某行", summ, "", ref])
    return xlsx(rows)


PAYO_HEAD = "Currency,Payout method,Transaction date,Transaction time,Time zone,Credit amount,Debit amount,Status,Running balance,Description\n"


def payoneer(lines) -> bytes:
    """lines: (date MM-DD-YYYY, time, tz, credit, debit, status, balance, desc)"""
    body = "".join("USD,USD balance,%s,%s,%s,%s,%s,%s,%s,%s\n" % l for l in lines)
    return ("﻿" + PAYO_HEAD + body).encode("utf-8")


WF_HEAD = [
    "子账号昵称",
    "子账号登录外标",
    "动账类型",
    "描述",
    "币种",
    "入账金额",
    "出账金额",
    "余额",
    "交易号",
    "交易创建日期",
    "交易创建时间",
]


def worldfirst(data):
    rows = [WF_HEAD]
    for d in data:  # (昵称, 动账类型, 描述, 入, 出, 余额, 交易号, 日期, 时间)
        nick, typ, desc, i, o, bal, ref, date, time = d
        rows.append([nick, "", typ, desc, "美元", i, o, bal, ref, date, time])
    return xlsx(rows)


PP_HEAD = [
    "创建时间",
    "流水号",
    "订单号",
    "出账/入账",
    "业务类型",
    "出/入账币种",
    "出/入账金额",
    "账号Id",
    "平台",
    "店铺所在地区",
    "店铺名称",
    "交易对手方支付机构名称",
    "交易对手方账户名",
    "交易对手方账号",
    "实际汇出币种",
    "实际汇出金额",
    "费用",
    "优惠金额",
    "账户余额",
    "汇率",
    "用户编号",
    "附言",
]


def pingpong(data):
    rows = [PP_HEAD]
    for (
        d
    ) in data:  # (时间, 流水号, 订单号, 方向, 业务类型, 币种, 金额, 账号Id, 对手方, 余额, 用户编号)
        t, ref, order, direction, typ, cur, amt, acc, party, bal, user = d
        rows.append(
            [
                t,
                ref,
                order,
                direction,
                typ,
                cur,
                amt,
                acc,
                "WALMART",
                "US",
                "/",
                "",
                party,
                "",
                "",
                "",
                "",
                "",
                bal,
                "",
                user,
                "",
            ]
        )
    return xlsx(rows)
