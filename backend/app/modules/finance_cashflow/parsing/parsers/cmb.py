# ruff: noqa: E501, E402, UP031
"""招商银行「交易流水」PDF（一网通 / 掌上生活申请的流水证明）。

每行：记账日期 货币 交易金额 联机余额 交易摘要 对手信息；对手信息太长时折到下一行，接回上一笔。
没有时间、没有流水号；同一天按 PDF 里的先后顺序（旧 → 新）。
"""

from __future__ import annotations

import re

from ..model import ParsedRow, RejectFile

TZ = "Asia/Shanghai"
ROW = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+([A-Z]{3})\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})\s+(\S+)(?:\s+(.*))?$"
)
# 每页重复的表头、页码，最后一页的「温馨提示」说明：都不是流水。
NOISE = re.compile(r"^(\d+/\d+|记账日期.*|Date\s+Currency.*|Amount\s+Balance.*|—+)$")


def rows_of(det) -> list[tuple[str, str, str, str, str, str]]:
    out: list[list[str]] = []
    for page in det.pdf_pages:
        last: list[str] | None = None
        for raw in page:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("温馨提示"):
                last = None  # 说明文字不接到流水上；PDF 抽字顺序里它可能排在本页流水前面
                continue
            m = ROW.match(line)
            if m:
                last = [
                    m.group(1),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    (m.group(6) or "").strip(),
                ]
                out.append(last)
            elif last is not None and not NOISE.match(line):
                last[5] += line  # 对手信息折行
    return [tuple(r) for r in out]  # type: ignore[misc]


def parse(det, seed):
    out = []
    for index, (day, currency, amount, balance, kind, party) in enumerate(rows_of(det), start=1):
        acct = seed.cmb(det.inquiry_account, currency)
        if acct is None:
            raise RejectFile(
                "招商银行流水里有 %s 的交易，但这个币种的账户没登记（尾号 %s）"
                % (currency, det.inquiry_account[-4:])
            )
        out.append(
            ParsedRow(
                acct.account_key,
                day,
                "",
                TZ,
                amount,
                currency,
                balance,
                party,
                "",
                kind,
                "",
                "",
                index,
            )
        )
    return out
