"""三种报表的解析：按内容认类型、两种结算报表列名、仓储新旧表头与守恒、入库按货件汇总、金额取反。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import tests.modules.wfs_fees.synth as S
from app.modules.wfs_fees.parsing import (
    FEE_SOURCE_INBOUND,
    FEE_SOURCE_SETTLEMENT,
    FEE_SOURCE_STORAGE,
    ParseError,
    detect,
    friday_of,
    parse,
)


def test_detect_by_content_not_file_name():
    assert (
        detect(S.settlement([S.fee("LostInventory", "2026-10-07", "-10.00", gtin=S.GTIN_1)]))
        == FEE_SOURCE_SETTLEMENT
    )
    assert detect(S.storage([(S.GTIN_1, "SKU-1", "1.00", "1.10", "0.10")])) == FEE_SOURCE_STORAGE
    assert (
        detect(
            S.inbound(
                [(S.CARGO, "2026-10-01", "Parcel", "Base", "$12.00")], ("2026-10-03", "2026-10-16")
            )
        )
        == FEE_SOURCE_INBOUND
    )
    with pytest.raises(ParseError, match="认不出"):
        detect(b"a,b\n1,2\n")


def test_settlement_api_and_seller_center_columns_give_the_same_lines():
    rows = [
        S.fee("LostInventory", "2026-10-07", "-15.30", gtin=S.GTIN_1, ref="R1", qty="6"),
        S.fee("Refund", "2026-10-08", "-5.00", reason="StorageFeeDispute", ref="R2"),
        S.fee("FulfillmentFee", "2026-10-07", "3.45", gtin=S.GTIN_1, ref="F1"),  # 配送费不入表
        S.fee("StorageFee", "2026-10-09", "100.00", ref="S1"),  # 周汇总行不入表
    ]
    api = parse(S.settlement(rows))
    sc = parse(S.settlement(rows, seller_center=True))
    for report in (api, sc):
        assert report.fee_source == FEE_SOURCE_SETTLEMENT
        assert [line.fee_type for line in report.lines] == ["LostInventory", "Refund"]
        assert report.lines[0].amount_usd == Decimal(
            "15.30"
        )  # Net Payable -15.30 = Walmart 付我们 15.30
        assert report.lines[0].gtin == S.GTIN_1
        assert report.lines[0].partner_id == S.PARTNER_A
        assert report.lines[0].quantity == Decimal("6")
        assert report.lines[1].amount_usd == Decimal("5.00")
        assert report.partner_id == S.PARTNER_A
        assert report.period_start == date(2026, 10, 7) and report.period_end == date(2026, 10, 8)
        assert any("不入表" in w for w in report.warnings)
    assert [line.line_key for line in api.lines] == [line.line_key for line in sc.lines]


def test_settlement_identical_rows_without_reference_id_are_both_kept():
    row = S.fee("RC_InventoryDisposalFee", "2026-10-07", "0.55", gtin=S.GTIN_2)
    report = parse(S.settlement([row, row]))
    assert len(report.lines) == 2
    assert len({line.line_key for line in report.lines}) == 2


def test_settlement_rejects_missing_date_or_amount():
    with pytest.raises(ParseError, match="缺交易日期或金额"):
        parse(S.settlement([S.fee("LostInventory", "", "-1.00")]))


def test_storage_with_summary_block_checks_conservation():
    rows = [
        (S.GTIN_1, "SKU-1", "9.65", "10.62", "0.97"),
        (S.GTIN_2, "SKU-2", "20.25", "22.16", "1.91"),
    ]
    ok = parse(S.storage(rows, period=("2026-09-19", "2026-10-02"), total="29.90"))
    assert ok.fee_source == FEE_SOURCE_STORAGE
    assert ok.period_start == date(2026, 9, 19) and ok.period_end == date(2026, 10, 2)
    assert [line.amount_usd for line in ok.lines] == [Decimal("-9.65"), Decimal("-20.25")]
    assert ok.lines[0].original_amount == Decimal("-10.62") and ok.lines[
        0
    ].discount_savings == Decimal("0.97")
    assert ok.lines[0].sku == "SKU-1"
    with pytest.raises(ParseError, match="守恒不平"):
        parse(S.storage(rows, period=("2026-09-19", "2026-10-02"), total="40.00"))


def test_storage_from_api_needs_a_period_from_the_caller():
    rows = [(S.GTIN_1, "", "1.00", "1.00", "0")]
    with pytest.raises(ParseError, match="请选择账期"):
        parse(S.storage(rows))
    report = parse(S.storage(rows), period_start=date(2026, 10, 3), period_end=date(2026, 10, 16))
    assert report.lines[0].transaction_date == date(2026, 10, 16)
    assert (
        report.lines[0].line_key
        != parse(S.storage(rows), period_start=date(2026, 9, 19), period_end=date(2026, 10, 2))
        .lines[0]
        .line_key
    )


def test_storage_old_header_without_discount_columns_still_parses():
    head = [h for h in S.STORAGE_HEAD if h not in ("Original Amount", "Discount Savings")]
    head = [
        h.replace("average daily units", "average units")
        .replace("(450+ days)", "(451+)")
        .replace("(366-450 days)", "(366-450)")
        for h in head
    ]
    body = [
        S.GTIN_1,
        "SKU-1",
        "",
        "合成",
        "1",
        "1",
        "1",
        "1",
        "0.001",
        "0.001",
        "0.003",
        "0.01",
        "10",
        "0",
        "0",
        "0",
        "14",
        "3.00",
    ]
    content = S._csv([head, body])
    report = parse(content, period_start=date(2026, 10, 3), period_end=date(2026, 10, 16))
    assert report.lines[0].amount_usd == Decimal("-3.00")
    assert report.lines[0].original_amount is None


def test_inbound_sums_rows_per_shipment_and_keeps_an_empty_report():
    report = parse(
        S.inbound(
            [
                (S.CARGO, "2026-10-05", "Parcel", "Base", "$84.88"),
                (S.CARGO, "2026-10-05", "Parcel", "Fuel Surcharge Ground", "$8.72"),
                ("9900002WFB", "2026-10-09", "LTL", "", "$120.00"),
            ],
            ("2026-10-03", "2026-10-16"),
        )
    )
    assert report.fee_source == FEE_SOURCE_INBOUND
    assert report.period_start == date(2026, 10, 3)
    by_cargo = {line.source_ref: line for line in report.lines}
    assert by_cargo[S.CARGO].amount_usd == Decimal("-93.60")
    assert by_cargo[S.CARGO].transaction_date == date(2026, 10, 5)
    assert by_cargo[S.CARGO].detail == "Parcel"
    assert by_cargo["9900002WFB"].amount_usd == Decimal("-120.00")
    assert report.declared_total == Decimal("213.60")
    empty = parse(S.inbound([], ("2026-10-03", "2026-10-16")))
    assert empty.lines == [] and empty.declared_total == Decimal("0")


def test_inbound_rejects_bad_period():
    with pytest.raises(ParseError, match="账期异常"):
        parse(S.inbound([], ("2026-10-16", "2026-10-03")))


def test_friday_of_walmart_bill_week():
    assert friday_of(date(2026, 10, 3)) == date(2026, 10, 9)  # 周六 → 下周五
    assert friday_of(date(2026, 10, 9)) == date(2026, 10, 9)  # 周五
    assert friday_of(date(2026, 10, 8)) == date(2026, 10, 9)