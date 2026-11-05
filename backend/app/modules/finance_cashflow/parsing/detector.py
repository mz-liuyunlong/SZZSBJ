# ruff: noqa: E501, E402, UP031
"""按内容识别账户（不看文件名）。认不出 / 不合规 → RejectFile（按文件原子）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import readers
from .model import RejectFile
from .readers import cell, norm_head

PAYONEER_HEADER = "Currency,Payout method,Transaction date"
PAYONEER_SELLER = re.compile(r"Payment from Walmart|Card charge|Maintenance fee")
PAYONEER_COLLECTOR = re.compile(r"STRIPE|connected account")
RANGE_RE = re.compile(
    r"(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})\s*[-~至到]\s*(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})"
)


@dataclass
class Detection:
    provider: str  # boc / shenzhen_rural_bank / payoneer / worldfirst / pingpong / cmb
    note: str
    sheets: list = field(default_factory=list)  # [(name, rows)]
    csv_rows: list = field(default_factory=list)
    account_key: str | None = None  # 单账户文件直接给；中行 / PingPong 由解析器按行定
    inquiry_account: str = ""
    header_row: int = -1
    pdf_pages: list = field(default_factory=list)  # PDF：每页的文本行
    declared_range: tuple | None = None
    skipped_rows: int = 0


def _digits(s: str) -> str:
    return re.sub(r"\D", "", re.sub(r"\.0$", "", cell(s)))


def _range_in(rows, keys) -> tuple | None:
    for r in rows[:40]:
        line = " ".join(cell(x) for x in (r or []) if cell(x))
        if not line or not any(k in line for k in keys):
            continue
        m = RANGE_RE.search(line)
        if m:
            g = m.groups()
            return ("%s-%s-%s" % g[0:3], "%s-%s-%s" % g[3:6])
    return None


CMB_TITLE = "招商银行交易流水"
CMB_ACCOUNT = re.compile(r"账号[:：]\s*(\d{4})\**(\d{4})")
CMB_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*--\s*(\d{4}-\d{2}-\d{2})$")


def _detect_pdf(content: bytes, seed) -> Detection:
    pages = readers.read_pdf_lines(content)
    head = [line.strip() for line in (pages[0] if pages else [])[:30]]
    if not any(CMB_TITLE in line for line in head):
        raise RejectFile("PDF 认不出：目前只接招商银行「交易流水」PDF；中行请导「交易明细」xls")
    masked = next((m for m in (CMB_ACCOUNT.search(line) for line in head) if m), None)
    if masked is None:
        raise RejectFile("招商银行流水 PDF 里没找到账号")
    key = masked.group(1) + masked.group(2)  # 前 4 位 + 后 4 位，中间银行打了星号
    if not seed.cmb_known(key):
        raise RejectFile("招商银行流水，但账号没登记（尾号 %s）" % key[-4:])
    declared = next((m.groups() for m in (CMB_RANGE.match(line) for line in head) if m), None)
    return Detection(
        "cmb",
        "招商银行交易流水",
        pdf_pages=pages,
        inquiry_account=key,
        declared_range=declared,
    )


def detect(
    content: bytes, seed, max_bytes=readers.MAX_UNZIPPED_BYTES, max_entries=readers.MAX_ZIP_ENTRIES
) -> Detection:
    kind = readers.kind_of(content)
    if kind == "pdf":
        return _detect_pdf(content, seed)
    if kind == "text":
        try:
            head = content[:200].decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RejectFile("不是 xlsx / xls / Payoneer CSV") from exc
        if not head.startswith(PAYONEER_HEADER):
            raise RejectFile("不是 xlsx / xls / Payoneer CSV")
        rows = readers.read_csv(content)
        hdr = rows[0]
        if "Description" not in hdr:
            raise RejectFile("Payoneer CSV 缺 Description 列")
        di = hdr.index("Description")
        seller = sum(1 for r in rows[1:] if len(r) > di and PAYONEER_SELLER.search(r[di]))
        collector = sum(1 for r in rows[1:] if len(r) > di and PAYONEER_COLLECTOR.search(r[di]))
        if seller == collector:
            raise RejectFile(
                "派安盈账户无法判定，请人工指定"
                if seller
                else "Payoneer CSV 但没有可识别的交易描述"
            )
        acct = seed.payoneer("seller" if seller > collector else "collector")
        if acct is None:
            raise RejectFile("派安盈账户没登记")
        return Detection(
            "payoneer",
            "派安盈 · %s" % acct.display_name,
            csv_rows=rows,
            account_key=acct.account_key,
        )
    sheets = (
        readers.read_xlsx(content, max_bytes, max_entries)
        if kind == "xlsx"
        else readers.read_xls(content)
    )
    for _name, rows in sheets:
        top = [[norm_head(x) for x in r if cell(x)] for r in rows[:12]]
        flat = " ".join(" ".join(r) for r in top)
        flat_raw = " ".join(" ".join(cell(x) for x in r if cell(x)) for r in rows[:12]).replace(
            " ", ""
        )
        if "子账号昵称" in flat and "动账类型" in flat:
            acct = seed.worldfirst()
            if acct is None:
                raise RejectFile("万里汇账户没登记")
            return Detection(
                "worldfirst", "万里汇导出", sheets=[(_name, rows)], account_key=acct.account_key
            )
        if "出账/入账" in flat and "流水号" in flat and "用户编号" in flat:
            return Detection("pingpong", "PingPong 账单明细", sheets=[(_name, rows)])
        if "交易明细查询列表" in flat or ("对方账户名" in flat and "交易流水号" in flat):
            acc = ""
            for r in rows[:12]:
                if r and norm_head(r[0]) == "账号" and len(r) > 1:
                    acc = _digits(r[1])
            acct = seed.yz(acc)
            if acct is None:
                raise RejectFile("交易明细查询列表，但账号没登记（尾号 %s）" % acc[-4:])
            hi = next(
                (
                    i
                    for i, r in enumerate(rows)
                    if r
                    and norm_head(r[0]) == "交易时间"
                    and len(r) > 1
                    and norm_head(r[1]) == "支出"
                ),
                -1,
            )
            return Detection(
                "shenzhen_rural_bank",
                "深通村镇银座交易明细",
                sheets=[(_name, rows)],
                account_key=acct.account_key,
                header_row=hi,
                declared_range=_range_in(rows[: max(hi, 0)], ("交易时间",)),
            )
        if "查询账号[Inquireraccount]" in flat_raw or (
            "查询账号" in flat and "TransactionType" in flat_raw
        ):
            acc = ""
            for r in rows[:12]:
                if r and norm_head(r[0]).startswith("查询账号") and len(r) > 1:
                    acc = _digits(r[1])
            if not seed.boc_known_inquiry(acc):
                raise RejectFile("中行交易明细，但查询账号没登记（尾号 %s）" % acc[-4:])
            hi = next((i for i, r in enumerate(rows) if r and norm_head(r[0]) == "交易类型"), -1)
            if hi < 0:
                raise RejectFile("中行交易明细缺「交易类型[Transaction Type]」表头")
            return Detection(
                "boc",
                "中行交易明细",
                sheets=[(_name, rows)],
                inquiry_account=acc,
                header_row=hi,
                declared_range=_range_in(rows[:hi], ("查询时间范围", "TimeRange", "Time Range")),
            )
    raise RejectFile(
        "表头不认识（支持：万里汇 / PingPong / 中行交易明细 / 银座交易明细 / Payoneer CSV / 招商银行流水 PDF）"
    )
