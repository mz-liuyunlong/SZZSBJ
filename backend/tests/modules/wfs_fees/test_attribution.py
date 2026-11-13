"""归属规则（纯函数）：GTIN 匹配、入库按实发 / 申报、无 GTIN 的几条规则、尾差守恒。"""

from __future__ import annotations

from decimal import Decimal

import tests.modules.wfs_fees.synth as S
from app.modules.wfs_fees import attribution as A

L1 = A.Listing("30000000001", "MSKU-1", "SKU-1")
L2 = A.Listing("30000000002", "MSKU-2", "SKU-2")
LISTINGS = {(S.STORE_A, S.GTIN_1): L1, (S.STORE_A, S.GTIN_2): L2}


def test_lookup_tolerates_leading_zeros():
    assert A.lookup(LISTINGS, S.STORE_A, S.GTIN_1) is L1
    assert A.lookup(LISTINGS, S.STORE_A, S.GTIN_1.lstrip("0")) is L1
    assert A.lookup(LISTINGS, S.STORE_B, S.GTIN_1) is None
    assert A.lookup(LISTINGS, S.STORE_A, "") is None


def test_split_amount_keeps_the_total_with_largest_remainder():
    shares = [
        A.Share(gtin="a", weight=Decimal(1)),
        A.Share(gtin="b", weight=Decimal(1)),
        A.Share(gtin="c", weight=Decimal(1)),
    ]
    out = A.split_amount(Decimal("-10.00"), shares)
    # 余数相同按原顺序补：第一行多 1 分
    assert [amount for _, amount in out] == [Decimal("-3.34"), Decimal("-3.33"), Decimal("-3.33")]
    assert sum(amount for _, amount in out) == Decimal("-10.00")
    assert A.split_amount(Decimal("5"), [A.Share(weight=Decimal(0))]) == []
    uneven = A.split_amount(
        Decimal("1.00"), [A.Share(weight=Decimal(2)), A.Share(weight=Decimal(1))]
    )
    assert [amount for _, amount in uneven] == [Decimal("0.67"), Decimal("0.33")]


def test_split_amount_never_flips_sign_when_shares_outnumber_cents():
    """复审 P2-4：1.00 分 200 份、3.00 分 400 份，旧算法最后一行会变成反号。"""
    for total, count in ((Decimal("1.00"), 200), (Decimal("3.00"), 400), (Decimal("-1.00"), 200)):
        out = A.split_amount(total, [A.Share(gtin=str(i), weight=Decimal(1)) for i in range(count)])
        amounts = [amount for _, amount in out]
        assert sum(amounts) == total
        assert all(a == 0 or (a > 0) == (total > 0) for a in amounts)
        assert max(abs(a) for a in amounts) <= Decimal("0.01")


def test_split_amount_keeps_sub_cent_totals():
    """复审 P3-1：报表给到 4 位小数（1.0050 分 3 份），Σ 仍等于原行，零头补在余数最大的那一行。"""
    for total in (Decimal("1.0050"), Decimal("-1.0050"), Decimal("0.0040"), Decimal("0.0050")):
        out = A.split_amount(total, [A.Share(gtin=str(i), weight=Decimal(1)) for i in range(3)])
        amounts = [amount for _, amount in out]
        assert sum(amounts) == total
        assert all(a == 0 or (a > 0) == (total > 0) for a in amounts)
    out = A.split_amount(Decimal("1.0050"), [A.Share(weight=Decimal(1)) for _ in range(3)])
    assert [amount for _, amount in out] == [Decimal("0.3350"), Decimal("0.34"), Decimal("0.33")]


def test_inbound_uses_shipped_quantity_then_declared():
    items = [
        (S.GTIN_1, "MSKU-1", L1, Decimal(300), Decimal(300)),
        (S.GTIN_2, "MSKU-2", L2, Decimal(100), Decimal(120)),
    ]
    result = A.allocate_inbound(Decimal("-93.60"), items)
    assert result.attribution == A.ATTR_ALLOCATED
    assert [(s.item_id, amt) for s, amt in result.children] == [
        ("30000000001", Decimal("-70.20")),
        ("30000000002", Decimal("-23.40")),
    ]
    declared_only = A.allocate_inbound(
        Decimal("-10"),
        [
            (S.GTIN_1, "MSKU-1", L1, Decimal(0), Decimal(1)),
            (S.GTIN_2, "MSKU-2", L2, Decimal(0), Decimal(3)),
        ],
    )
    assert [amt for _, amt in declared_only.children] == [Decimal("-2.50"), Decimal("-7.50")]
    assert "申报" in declared_only.note
    assert A.allocate_inbound(Decimal("-10"), []).attribution == A.ATTR_UNALLOCATED


def _no_gtin(**over):
    base = dict(
        fee_type="Refund",
        reason_code="",
        detail="",
        amount=Decimal("10"),
        cargo_shares={},
        storage_base=None,
        fulfillment_base=None,
        listings=LISTINGS,
        store_id=S.STORE_A,
    )
    return A.allocate_no_gtin(**{**base, **over})


def test_storage_fee_dispute_is_company_and_unknown_is_unallocated():
    assert _no_gtin(reason_code="StorageFeeDispute").attribution == A.ATTR_COMPANY
    assert _no_gtin(fee_type="Charge").attribution == A.ATTR_UNALLOCATED


def test_inbound_shipping_refund_follows_the_shipment_shares():
    detail = f"Refund for shipment _{S.CARGO}_ overcharge"
    missing = _no_gtin(reason_code="InboundTransportationShippingRefund", detail=detail)
    assert missing.attribution == A.ATTR_UNALLOCATED and S.CARGO in missing.note
    shares = {
        S.CARGO: [
            A.Share(gtin=S.GTIN_1, item_id=L1.item_id, msku=L1.msku, weight=Decimal("70.20")),
            A.Share(gtin=S.GTIN_2, item_id=L2.item_id, msku=L2.msku, weight=Decimal("23.40")),
        ]
    }
    done = _no_gtin(
        reason_code="InboundTransportationShippingRefund",
        detail=detail,
        amount=Decimal("9.36"),
        cargo_shares=shares,
    )
    assert done.attribution == A.ATTR_ALLOCATED
    assert [amt for _, amt in done.children] == [Decimal("7.02"), Decimal("2.34")]


def test_rebate_period_is_read_from_the_detail():
    assert A.parse_rebate_period(
        "Discount for FulfillmentFee for AUG-26-26 to SEP-25-26 at 10%"
    ) == (__import__("datetime").date(2026, 8, 26), __import__("datetime").date(2026, 9, 25))
    assert A.parse_rebate_period("no period here") is None


def test_fulfillment_rebate_ten_percent_of_undiscounted_base_is_exact_otherwise_check():
    detail = "Discount for FulfillmentFee for OCT-03-26 to OCT-16-26"
    base = {S.GTIN_1: Decimal("300.00"), S.GTIN_2: Decimal("100.00")}
    exact = _no_gtin(
        fee_type="DiscountAdjustment", detail=detail, amount=Decimal("40.00"), fulfillment_base=base
    )
    assert exact.attribution == A.ATTR_ALLOCATED
    assert [(s.item_id, amt) for s, amt in exact.children] == [
        ("30000000001", Decimal("30.00")),
        ("30000000002", Decimal("10.00")),
    ]
    off = _no_gtin(
        fee_type="DiscountAdjustment", detail=detail, amount=Decimal("13.74"), fulfillment_base=base
    )
    assert off.attribution == A.ATTR_ALLOCATED_CHECK and "待核" in off.note
    assert sum(amt for _, amt in off.children) == Decimal("13.74")
    assert (
        _no_gtin(fee_type="DiscountAdjustment", detail=detail, amount=Decimal("1")).attribution
        == A.ATTR_UNALLOCATED
    )


def test_storage_rebate_prefers_undiscounted_periods_when_they_explain_the_amount():
    detail = "Discount for StorageFee for OCT-03-26 to OCT-16-26"
    storage_base = {
        (S.GTIN_1, "MSKU-1"): (Decimal("200"), Decimal("200"), L1),
        (S.GTIN_2, "MSKU-2"): (Decimal("100"), Decimal("0"), L2),
    }
    nodisc = _no_gtin(
        fee_type="DiscountAdjustment",
        detail=detail,
        amount=Decimal("20.00"),
        storage_base=storage_base,
    )
    assert nodisc.attribution == A.ATTR_ALLOCATED
    assert [(s.msku, amt) for s, amt in nodisc.children] == [("MSKU-1", Decimal("20.00"))]
    whole = _no_gtin(
        fee_type="DiscountAdjustment",
        detail=detail,
        amount=Decimal("30.00"),
        storage_base=storage_base,
    )
    assert whole.attribution == A.ATTR_ALLOCATED
    assert [amt for _, amt in whole.children] == [Decimal("20.00"), Decimal("10.00")]
