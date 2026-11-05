# ruff: noqa: E501
"""派安盈月结补充（全部合成数据）：识别、对上已有提现、折人民币、派安盈那层差额、配对。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.parsing import payoneer_statement as P
from app.modules.finance_cashflow.parsing.model import RejectFile
from tests.modules.finance_cashflow import synth as S

INTERNAL = frozenset({"T02"})
CLASSIFIER = J.Classifier([J.Rule("text", "内部调拨", "T02", 10)])
RATE = Decimal("7.1000")


def line(
    uid, amount, *, account="PAYONEER_FH", cur="USD", day="2026-10-15", desc="", time=None, **extra
):
    return J.LineInput(
        line_uid=uid,
        account_key=account,
        provider=extra.pop("provider", "payoneer"),
        currency_code=cur,
        business_date=date.fromisoformat(day),
        amount=Decimal(str(amount)),
        balance_after=None,
        description=desc,
        memo="",
        counterparty_name="",
        file_row_order=1,
        source_time=time,
        **extra,
    )


def row(
    key,
    amount,
    *,
    txn="T1",
    day="2026-10-15",
    time=None,
    desc="Payment to 某银行 (0000)",
    transfer=None,
    tcur="",
    account="PAYONEER_FH",
):
    return J.StatementRow(
        row_key=key,
        account_key=account,
        txn_id=txn,
        txn_time=time or datetime.fromisoformat(f"{day}T08:00:00+00:00"),
        business_date=date.fromisoformat(day),
        description=desc,
        amount=Decimal(str(amount)),
        currency_code="USD",
        transfer_amount=Decimal(str(transfer)) if transfer is not None else None,
        transfer_currency=tcur,
    )


def compute(lines, rows=(), today=date(2026, 10, 20)):
    return J.compute_journal(lines, CLASSIFIER, INTERNAL, lambda _d: RATE, (), rows, today)


def by_uid(result):
    return {item.source.line_uid: item for item in result.lines}


def types(result):
    return [alert.type for alert in result.alerts]


T1 = datetime(2026, 10, 15, 15, 56, 15, tzinfo=UTC)


def test_withdrawal_blank_until_statement_and_card_charge_uses_lingxing_rate():
    result = compute(
        [
            line("w", "-3000.00", desc="Payment to 招商银行 (0000)", time=T1),
            line("c", "-39", desc="Card charge (SHOPIFY)", account="PAYONEER"),
        ]
    )
    items = by_uid(result)
    assert (items["w"].amount_cny, items["w"].fx_source) == (None, J.FX_SOURCE_PENDING)
    assert items["c"].amount_cny == Decimal("-276.9000")
    assert (items["c"].fx_rate, items["c"].fx_source) == (RATE, J.FX_SOURCE_LINGXING)
    assert J.ALERT_PAYONEER_MISSING not in types(result)  # 月份还没结束：不报


def test_month_ended_without_statement_is_an_anomaly():
    result = compute([line("w", "-100", desc="Payment to 某人", time=T1)], today=date(2026, 11, 3))
    assert types(result) == [J.ALERT_PAYONEER_MISSING]
    assert "还没导派安盈月结单" in result.alerts[0].message


def test_statement_fills_actual_cny_and_payoneer_rate_by_exact_time():
    result = compute(
        [
            line("w", "-3000.00", desc="Payment to 招商银行 (0000)", time=T1),
            line(
                "x",
                "-3000.00",
                desc="Payment to 招商银行 (0000)",
                time=datetime(2026, 10, 15, 3, 0, tzinfo=UTC),
            ),
        ],
        [
            row(
                "f:2",
                "-3000.00",
                time=T1,
                transfer="20000",
                tcur="CNY",
                desc="Payment to 某人（招商）",
            )
        ],
    )
    items = by_uid(result)
    assert items["w"].amount_cny == Decimal("-20000")
    assert (items["w"].fx_rate, items["w"].fx_source) == (Decimal("6.6667"), J.FX_SOURCE_PAYONEER)
    assert items["w"].statement and items["w"].statement.txn_id == "T1"
    assert items["x"].amount_cny is None  # 同金额另一笔时间对不上：不补
    assert types(result) == [J.ALERT_PAYONEER_MISSING]  # 这个月月结单里没有 x


def test_statement_matches_by_date_when_time_missing_and_refuses_to_guess():
    one = compute(
        [line("w", "-50", desc="Payment to 某人")],
        [row("f:2", "-50", day="2026-10-16", transfer="333", tcur="CNY")],
    )
    assert by_uid(one)["w"].amount_cny == Decimal("-333")
    two = compute(
        [line("a", "-50", desc="Payment to 某人"), line("b", "-50", desc="Payment to 某人")],
        [row("f:2", "-50", transfer="333", tcur="CNY")],
    )
    assert J.ALERT_STATEMENT_AMBIGUOUS in types(two)
    assert all(item.amount_cny is None for item in two.lines)


def test_statement_row_without_line_and_conflicting_reimport():
    result = compute(
        [], [row("f:2", "-80", txn="A"), row("f:3", "-90", txn="B"), row("g:3", "-91", txn="B")]
    )
    assert sorted(types(result)) == sorted(
        [J.ALERT_STATEMENT_UNMATCHED, J.ALERT_STATEMENT_CONFLICT]
    )
    same = compute(
        [line("w", "-80", desc="Payment to 某人")],
        [
            row("f:2", "-80", txn="A", transfer="500", tcur="CNY"),
            row("g:2", "-80", txn="A", transfer="500", tcur="CNY"),
        ],
    )
    assert by_uid(same)["w"].amount_cny == Decimal("-500")
    assert types(same) == []


def test_non_withdrawal_rows_are_only_for_coverage():
    result = compute(
        [line("c", "-39", desc="Card charge (X)")], [row("f:2", "-39", desc="Card charge (X)")]
    )
    assert types(result) == []
    assert by_uid(result)["c"].fx_source == J.FX_SOURCE_LINGXING


def test_payoneer_layer_gap_is_an_anomaly_and_pairing_uses_stated_amount():
    lines = [
        line("p", "-10000", desc="Payment to BANK OF CHINA (0000) 内部调拨", day="2026-10-24"),
        line(
            "b",
            "9981.60",
            account="ZSBJ_BOC_USD",
            provider="boc",
            desc="国际汇款 内部调拨",
            day="2026-10-26",
        ),
    ]
    result = compute(
        lines, [row("f:2", "-10000", day="2026-10-24", transfer="9981.60", tcur="USD")]
    )
    items = by_uid(result)
    fee = [alert for alert in result.alerts if alert.type == J.ALERT_PAYONEER_FEE]
    assert [(alert.amount, alert.currency_code, alert.line_uid) for alert in fee] == [
        (Decimal("18.40"), "USD", "p")
    ]
    assert "扣款 10000.00 USD" in fee[0].message and "交易号 T1" in fee[0].message
    assert items["p"].pair_id and items["p"].pair_id == items["b"].pair_id
    assert items["p"].amount_cny == Decimal("-71000.0000")  # 美元到美元：照旧用领星汇率
    assert J.payoneer_fee_gap(items["p"]) == Decimal("18.40")


def test_payoneer_gap_gone_once_fee_part_recorded():
    parts = [
        {"amount": "9981.6000", "category_code": "T02", "fee_layer": None},
        {"amount": "18.4000", "category_code": "F01", "fee_layer": J.FEE_LAYER_PAYONEER},
    ]
    result = compute(
        [line("p", "-10000", desc="Payment to BANK OF CHINA (0000) 内部调拨", parts=parts)],
        [row("f:2", "-10000", transfer="9981.60", tcur="USD")],
    )
    assert J.ALERT_PAYONEER_FEE not in types(result)


def test_cny_withdrawal_pairs_with_bank_on_actual_cny():
    result = compute(
        [
            line("p", "-1000", desc="Payment to 招商银行 (0000) 内部调拨", day="2026-10-09"),
            line(
                "b",
                "6683.00",
                account="ZSBJ_CMB",
                provider="boc",
                cur="CNY",
                desc="内部调拨",
                day="2026-10-10",
            ),
        ],
        [row("f:2", "-1000", day="2026-10-09", transfer="6683.00", tcur="CNY")],
    )
    items = by_uid(result)
    assert items["p"].pair_id and items["p"].pair_id == items["b"].pair_id
    assert items["p"].fx_rate == Decimal("6.6830")
    assert J.ALERT_UNPAIRED not in types(result)


# ---------------------------------------------------------------- 文件识别

HEAD = "Transaction Date,Transaction Time,Time Zone,Transaction ID,Description,Credit Amount,Debit Amount,Currency,Transfer Amount,Transfer Amount Currency,Status,Running Balance,Additional Description,Store Name,Source,Target,Reference ID\n"


def statement(rows) -> bytes:
    return ("﻿" + HEAD + "".join(",".join(r) + "\n" for r in rows)).encode("utf-8")


def srow(date_, time_, txn, desc, credit="", debit="", transfer="", tcur="", status="Completed"):
    return [
        date_,
        time_,
        "UTC",
        txn,
        desc,
        credit,
        debit,
        "USD",
        transfer,
        tcur,
        status,
        "1",
        "",
        "",
        "",
        "",
        "",
    ]


def test_parse_statement_collector_account_and_fields():
    content = statement(
        [
            srow(
                "10/15/2026",
                "15:56:15",
                "1000000001",
                "Payment to 某人（招商）",
                debit="3000.00",
                transfer="20100.00",
                tcur="CNY",
            ),
            srow(
                "10/05/2026",
                "17:00:00",
                "1",
                "Payment from STRIPE - XX-1 (某公司)",
                credit="241.39",
            ),
            srow(
                "10/29/2026",
                "17:53:10",
                "2",
                "Transfer from connected account ab@example.com",
                credit="237.37",
            ),
            srow("10/30/2026", "01:00:00", "3", "Payment to 某人", debit="5", status="Pending"),
        ]
    )
    assert P.is_statement(content)
    parsed = P.parse_statement(content, S.seed())
    assert parsed.account_key == "PAYONEER_FH"
    assert len(parsed.rows) == 3  # Pending 不收
    first = parsed.rows[0]
    assert (first.txn_id, first.amount, first.transfer_amount, first.transfer_currency) == (
        "1000000001",
        Decimal("-3000.0000"),
        Decimal("20100.0000"),
        "CNY",
    )
    assert first.txn_time_utc == T1 and first.business_date == date(2026, 10, 15)
    assert parsed.rows[2].description == "Transfer from connected account ab@example.com"
    late = P.parse_statement(
        statement([srow("10/31/2026", "20:00:00", "9", "Payment from STRIPE", credit="1")]),
        S.seed(),
    )
    assert late.rows[0].business_date == date(2026, 11, 1)  # 业务日按上海


def test_parse_statement_rejects_missing_columns_and_weekly_format_is_not_statement():
    with pytest.raises(RejectFile, match="缺列"):
        P.parse_statement(
            "﻿Transaction Date,Transaction Time,Time Zone,Transaction ID\n1,2,3,4\n".encode(),
            S.seed(),
        )
    assert not P.is_statement(
        S.payoneer(
            [("10-04-2026", "10:00:00", "UTC", "1", "0", "Completed", "1", "Card charge (X)")]
        )
    )


def test_two_fee_layers_with_round3_gap_pairing():
    """中行那笔：派安盈扣 10000、写到账 9981.60（差 18.40），中行实收 9969.60（再差 12.00）。"""
    statement = [row("f:2", "-10000", day="2026-10-24", transfer="9981.60", tcur="USD")]

    def lines(parts=None):
        return [
            line(
                "p",
                "-10000",
                desc="Payment to BANK OF CHINA (0000) 内部调拨",
                day="2026-10-24",
                counterparty_last4="0000",
                parts=parts,
            ),
            line(
                "b",
                "9969.60",
                account="ZSBJ_BOC_USD",
                provider="boc",
                desc="国际汇款 内部调拨",
                day="2026-10-26",
                account_last4="0000",
            ),
        ]

    result = compute(lines(), statement)
    gaps = {alert.type: alert.amount for alert in result.alerts if alert.line_uid == "p"}
    assert gaps == {J.ALERT_PAYONEER_FEE: Decimal("18.40"), J.ALERT_PAIR_GAP: Decimal("12.00")}
    items = by_uid(result)
    assert items["p"].pair_id and items["p"].pair_id == items["b"].pair_id
    both = [
        {"amount": "9969.6000", "category_code": "T02"},
        {"amount": "18.4000", "category_code": "F01", "fee_layer": J.FEE_LAYER_PAYONEER},
        {"amount": "12.0000", "category_code": "F01", "fee_layer": "fee"},
    ]
    done = compute(lines(both), statement)
    assert [alert.type for alert in done.alerts] == []
    assert by_uid(done)["p"].pair_id == by_uid(done)["b"].pair_id
