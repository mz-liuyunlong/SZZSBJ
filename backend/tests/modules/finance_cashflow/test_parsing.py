# ruff: noqa: E501
"""解析（纯函数，全部合成样本）：不需要数据库。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.finance_cashflow.parsing import readers
from app.modules.finance_cashflow.parsing.model import RejectFile
from app.modules.finance_cashflow.parsing.normalize import mask_text, to_decimal
from app.modules.finance_cashflow.parsing.pipeline import parse_file
from app.modules.finance_cashflow.parsing.seed import ACCOUNT_KEYS_V1
from tests.modules.finance_cashflow import synth as S


def boc_rows(prefix="R", n=3, cur="CNY", start_bal=1000, descending=False):
    rows, bal = [], Decimal(start_bal)
    for i in range(n):
        amt = Decimal(10 + i)
        bal += amt
        rows.append(
            (
                "来账",
                f"202610{10 + i:02d}",
                f"10:00:0{i}",
                cur,
                str(amt),
                str(bal),
                "某客户",
                "6222000000001234",
                f"{prefix}{i:06d}",
                "货款",
            )
        )
    return list(reversed(rows)) if descending else rows


def payo(date, time, credit, bal, desc, debit="0", tz="UTC", status="Completed"):
    return (date, time, tz, credit, debit, status, bal, desc)


def eleven_account_files():
    pp = S.pingpong(
        [
            (
                "2026-10-06 09:00:00",
                "PP001",
                "O1",
                "入账",
                "专用账户入账",
                "USD",
                "97.00",
                S.PP_USER + "01",
                "其他主体A",
                "1097.00",
                S.PP_USER,
            ),
            (
                "2026-10-06 08:59:00",
                "PP000",
                "O1",
                "出账",
                "资金归集至专用账户",
                "USD",
                "100.00",
                "OTHER-1",
                "",
                "0",
                S.OTHER_USER,
            ),
            (
                "2026-10-07 09:00:00",
                "PP002",
                "O2",
                "入账",
                "FX向资金账户转账",
                "CNH",
                "700.00",
                S.PP_USER + "02",
                "",
                "700.00",
                S.PP_USER,
            ),
            (
                "2026-10-08 09:00:00",
                "PP003",
                "O3",
                "入账",
                "入账",
                "USD",
                "50.00",
                S.PP_STORE,
                "WALMART",
                "50.00",
                S.PP_USER,
            ),
        ]
    )
    usd = ("来账", "20261015", "11:00:00", "USD", "5.00", "5.00", "X", "", "USD01", "")
    return {
        "boc_a.xlsx": S.boc(S.BOC_A, [*boc_rows("A"), usd]),
        "boc_b.xlsx": S.boc(S.BOC_B, [*boc_rows("B"), usd]),
        "yz.xlsx": S.yz(
            S.YZ_NO,
            [
                (
                    "2026-10-10 09:00:00",
                    "",
                    "=n:100.5",
                    "=n:100.5",
                    "6222000000005678",
                    "某人",
                    "收款",
                    "YZ1",
                )
            ],
        ),
        "payo_seller.csv": S.payoneer(
            [payo("10-04-2026", "10:00:00", "100", "100", "Payment from Walmart ")]
        ),
        "payo_collector.csv": S.payoneer(
            [payo("10-04-2026", "10:00:00", "50", "50", "Payment from STRIPE - XX-1 (Shop)")]
        ),
        "wf.xlsx": S.worldfirst(
            [("-", "入账", "收款", "=n:20", "", "=n:20", "WF1", "2026-10-13", "10:00:00")]
        ),
        "pp.xlsx": pp,
    }


def test_all_eleven_accounts_recognized_by_content():
    seen = set()
    for content in eleven_account_files().values():
        seen |= {line.account_key for line in parse_file(content, S.seed()).lines}
    assert seen == set(ACCOUNT_KEYS_V1)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"%PDF-1.4 xxx", id="pdf"),
        pytest.param(b"hello world", id="random"),
        pytest.param(S.xlsx([["随便", "表头"], ["1", "2"]]), id="unknown_header"),
        pytest.param(S.boc("123456789012", boc_rows()), id="boc_unregistered"),
        pytest.param(
            S.boc(S.BOC_A, [("来账", "20261010", "10:00:00", "EUR", "1", "1", "X", "", "E1", "")]),
            id="boc_unknown_currency",
        ),
        pytest.param(
            S.yz(
                "600000000000000", [("2026-10-10 09:00:00", "", "=n:1", "=n:1", "", "x", "y", "Z1")]
            ),
            id="yz_unregistered",
        ),
        pytest.param(
            S.payoneer(
                [
                    payo("10-04-2026", "10:00:00", "1", "1", "Payment from Walmart"),
                    payo("10-04-2026", "11:00:00", "1", "2", "Payment from STRIPE"),
                ]
            ),
            id="payoneer_tie",
        ),
        pytest.param(
            S.payoneer([payo("10-04-2026", "10:00:00", "1", "1", "Something")]), id="payoneer_none"
        ),
        pytest.param(
            S.payoneer(
                [payo("10-04-2026", "10:00:00", "1", "1", "Payment from Walmart", tz="Mars/Base")]
            ),
            id="payoneer_bad_tz",
        ),
        pytest.param(
            S.pingpong(
                [
                    (
                        "2026-10-08 09:00:00",
                        "P9",
                        "O9",
                        "入账",
                        "入账",
                        "USD",
                        "1",
                        "STORE-NEW",
                        "",
                        "1",
                        S.PP_USER,
                    )
                ]
            ),
            id="pingpong_unregistered_store",
        ),
        pytest.param(b"\xd0\xcf\x11\xe0" + b"\0" * 64, id="xls_garbage"),
        pytest.param(
            S.boc(
                S.BOC_A, [("来账", "20261010", "10:00:00", "CNY", "abc", "1", "X", "", "Q1", "")]
            ),
            id="boc_bad_amount",
        ),
    ],
)
def test_rejected_files_get_a_reason(content):
    with pytest.raises(RejectFile) as caught:
        parse_file(content, S.seed())
    assert str(caught.value)


def test_pdf_reason_is_the_rule_text():
    with pytest.raises(RejectFile, match="PDF 不是流水导出"):
        parse_file(b"%PDF-1.4", S.seed())


def test_zip_limits():
    with pytest.raises(RejectFile, match="解压超限"):
        parse_file(S.xlsx([["a"]], extra_entries=readers.MAX_ZIP_ENTRIES), S.seed())


def test_pingpong_splits_fee_and_skips_other_entity():
    parsed = parse_file(eleven_account_files()["pp.xlsx"], S.seed())
    usd = [line for line in parsed.lines if line.account_key == "PINGPONG_MAIN_USD"]
    assert sorted(line.amount for line in usd) == [Decimal("-3"), Decimal("100")]
    gross = next(line for line in usd if line.amount > 0)
    fee = next(line for line in usd if line.amount < 0)
    assert gross.balance_after + fee.amount == fee.balance_after
    assert not [line for line in parsed.lines if line.source_ref == "PP000"]


def test_declared_ranges():
    assert parse_file(S.boc(S.BOC_A, boc_rows()), S.seed()).declared_range == (
        "2026-10-01",
        "2026-10-28",
    )
    yz = S.yz(S.YZ_NO, [("2026-10-10 09:00:00", "", "=n:1", "=n:1", "", "x", "y", "Z1")])
    assert parse_file(yz, S.seed()).declared_range == ("2026-10-01", "2026-10-31")


def test_descending_export_is_normalized_to_time_order():
    parsed = parse_file(S.boc(S.BOC_A, boc_rows(descending=True)), S.seed())
    ordered = sorted(parsed.lines, key=lambda line: line.file_row_order)
    assert [line.source_ref for line in ordered] == ["R000000", "R000001", "R000002"]


def test_repeated_header_and_footer_are_skipped_with_a_warning():
    header = (
        "交易类型[ Transaction Type]",
        "交易日期[ Transaction Date]",
        "交易时间[ Transaction time]",
        "交易货币[ Trade Currency ]",
        "交易金额[ Trade Amount ]",
        "交易后余额[ After-transaction balance ]",
        "收款人名称",
        "收款人账号",
        "交易流水号",
        "用途",
    )
    rows = boc_rows()
    rows = [rows[0], header, *rows[1:], ("合计", "共 3 笔", "", "", "=n:0", "", "", "", "", "")]
    parsed = parse_file(S.boc(S.BOC_A, rows), S.seed())
    assert len(parsed.lines) == 3
    assert any("跳过" in warning for warning in parsed.warnings)
    yz = parse_file(
        S.yz(
            S.YZ_NO,
            [
                ("2026-10-10 09:00:00", "", "=n:1", "=n:1", "", "x", "y", "Z1"),
                ("汇总金额", "=n:0", "=n:1", "", "", "", "", ""),
            ],
        ),
        S.seed(),
    )
    assert len(yz.lines) == 1


def test_same_second_same_amount_keeps_both_lines():
    same = payo("10-04-2026", "10:00:00", "100", "100", "Payment from Walmart ")
    parsed = parse_file(S.payoneer([same, same]), S.seed())
    assert sorted(line.dup_ordinal for line in parsed.lines) == [1, 2]
    assert len({line.line_uid for line in parsed.lines}) == 2


def test_broken_balance_chain_warns_but_does_not_reject():
    rows = boc_rows("Z")
    rows[1] = rows[1][:5] + ("9999",) + rows[1][6:]
    parsed = parse_file(S.boc(S.BOC_A, rows), S.seed())
    assert parsed.balance_chain_ok is False
    assert any("余额链" in warning for warning in parsed.warnings)


def test_masking():
    text = mask_text(
        "身份证 110101199003071234 报文号 12345678901234567890 邮箱 abcdef@example.com"
    )
    assert "110101199003071234" not in text
    assert "…7890" in text
    assert "abc…@example.com" in text
    line = parse_file(S.boc(S.BOC_A, boc_rows()), S.seed()).lines[0]
    assert line.counterparty_account_last4 == "1234"


def test_full_reference_is_in_fingerprint_but_only_tail_is_stored():
    a = ("来账", "20261010", "10:00:00", "CNY", "10", "10", "X", "", "AAAA0123456789", "")
    b = ("来账", "20261010", "10:00:00", "CNY", "10", "10", "X", "", "BBBB0123456789", "")
    parsed = parse_file(S.boc(S.BOC_A, [a, b], range_=None), S.seed())
    assert {line.source_ref for line in parsed.lines} == {"0123456789"}
    assert len({line.line_uid for line in parsed.lines}) == 2


def test_money_never_goes_through_float():
    with pytest.raises(TypeError):
        to_decimal(0.1)
    assert to_decimal("0.1") + to_decimal("0.2") == Decimal("0.3000")


def test_payoneer_business_date_is_shanghai():
    parsed = parse_file(
        S.payoneer([payo("10-31-2026", "20:00:00", "5", "5", "Payment from Walmart ")]), S.seed()
    )
    line = parsed.lines[0]
    assert line.business_date.isoformat() == "2026-11-01"
    assert line.source_timezone == "UTC"
    assert line.source_time_utc.isoformat().startswith("2026-10-31T20:00:00")
