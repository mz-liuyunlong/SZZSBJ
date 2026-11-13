"""三种报表的解析：按内容认类型、两种结算报表列名、仓储新旧表头与守恒、入库按货件汇总、金额取反。"""

from __future__ import annotations

import io
import zipfile
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
    expand_upload,
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


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_zip_upload_expands_to_csv_members_only():
    csv_a = S.settlement([S.fee("LostInventory", "2026-10-07", "-1.00", gtin=S.GTIN_1)])
    csv_b = S.storage([(S.GTIN_1, "SKU-1", "1.00", "1.10", "0.10")])
    content = _zip(
        {
            "dir/a.csv": csv_a,
            "b.CSV": csv_b,
            "__MACOSX/dir/._a.csv": b"junk",
            ".hidden.csv": b"junk",
            "readme.txt": b"x",
        }
    )
    parts = expand_upload("bundle.zip", content)
    assert parts == [("bundle.zip/a.csv", csv_a), ("bundle.zip/b.CSV", csv_b)]
    plain = b"Transaction Type,Net Payable"
    assert expand_upload("x.csv", plain) == [("x.csv", plain)]


def test_zip_without_csv_or_broken_is_rejected():
    with pytest.raises(ParseError, match="没有 CSV"):
        expand_upload("a.zip", _zip({"readme.txt": b"x"}))
    with pytest.raises(ParseError, match="损坏"):
        expand_upload("a.zip", b"PK\x03\x04broken")


def test_summary_only_settlement_keeps_partner_and_explains_skip():
    """卖家后台「服务费 → StorageFee」下载的只有店铺周汇总行：不入表，但要能认店、说清原因。"""
    report = parse(S.settlement([S.fee("StorageFee", "2026-10-09", "100.00", ref="S1")]))
    assert report.lines == []
    assert report.partner_id == S.PARTNER_A
    assert any("仓储费店铺周汇总 1 行" in w for w in report.warnings)


def test_storage_duplicate_gtin_rows_are_merged_or_split_by_sku():
    """复审 P3：同一 GTIN 多行不能撞唯一键 —— 同 SKU 合并，不同 SKU 各自一行。"""
    report = parse(
        S.storage(
            [
                (S.GTIN_1, "SKU-1", "1.00", "1.10", "0.10"),
                (S.GTIN_1, "SKU-1", "2.00", "2.20", "0.20"),
                (S.GTIN_1, "SKU-2", "0.50", "0.50", "0"),
            ],
            period=("2026-10-03", "2026-10-16"),
            total="3.50",
        )
    )
    by_sku = {line.sku: line for line in report.lines}
    assert set(by_sku) == {"SKU-1", "SKU-2"}
    assert by_sku["SKU-1"].amount_usd == Decimal("-3.00")
    assert by_sku["SKU-1"].original_amount == Decimal("-3.30")
    assert len({line.line_key for line in report.lines}) == 2


def test_settlement_line_key_ignores_trailing_zeros_without_reference_id():
    a = parse(S.settlement([S.fee("Charge", "2026-10-07", "-1.5", ref="")])).lines[0]
    b = parse(S.settlement([S.fee("Charge", "2026-10-07", "-1.50", ref="")])).lines[0]
    assert a.line_key == b.line_key


def test_fulfillment_rows_read_carriage_return_files_and_skip_bad_ones():
    """复审 P2-5：新卖家补贴分摊读存档时和导入同一个读法，纯 \\r 换行也认；坏文件跳过不报错。"""
    from app.modules.wfs_fees.service import _fulfillment_rows

    content = S.settlement(
        [
            S.fee("FulfillmentFee", "2026-10-07", "3.45", gtin=S.GTIN_1, ref="F1", orig="3.45"),
            S.fee("FulfillmentFee", "bad-date", "1.00", gtin=S.GTIN_2, ref="F2", orig="1.00"),
        ]
    ).replace(b"\r\n", b"\r")
    rows = list(_fulfillment_rows(content))
    assert [(ref, gtin, orig) for ref, _when, gtin, orig, _disc in rows] == [
        ("F1", S.GTIN_1, Decimal("3.45"))
    ]
    assert list(_fulfillment_rows(b"\x00\xff not a csv")) == []
