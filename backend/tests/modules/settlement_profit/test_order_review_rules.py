"""订单审核纯规则（PRP §8.1～§8.4）：全部合成数据，不碰数据库。"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.settlement_profit.order_review.rules import (
    BillRow,
    CostEntry,
    FlowSegment,
    Lookups,
    OriginalLine,
    OutboundItem,
    OutboundOrder,
    ReviewSettings,
    ShipmentDetail,
    ShipmentHeader,
    bill_month_of,
    compute_line,
    content_hash,
    fulfillment_of,
    group_order_rows,
)
from app.modules.settlement_profit.transaction_types import categorize, describe

FIXTURE = Path(__file__).parent / "fixtures" / "bill_transaction_types.csv"
STORE = "990000000000000001"
ORDER = "900000000000000001"
GTIN = "00000000000001"
MSKU = "SYN-001"
CODE = "SP2026T0001"
WFS = "Walmart-fulfilled(WFS)"
SELLER = "Seller Fulfilled"
REPORT = date(2026, 11, 3)


def row(
    ttype: str,
    desc: str,
    atype: str,
    amount: str,
    *,
    qty: int | None = 1,
    fulfillment: str = WFS,
    order: str = ORDER,
    line: str = "1",
    gtin: str | None = GTIN,
    item: str | None = "SYN-ITEM-1",
) -> BillRow:
    return BillRow(
        transaction_type=ttype,
        transaction_description=desc,
        amount_type=atype,
        amount=Decimal(amount),
        currency_code="USD",
        ship_qty=qty,
        customer_order_no=order,
        customer_order_line_no=line,
        purchase_order_no=order,
        purchase_order_line_no=line,
        partner_gtin=gtin,
        partner_item_id=item,
        fulfillment_type=fulfillment,
        posted_date=date(2026, 10, 20),
        report_key="2026-11-03",
        report_date=REPORT,
    )


def sale_rows(fulfillment: str = WFS, qty: int = 1) -> list[BillRow]:
    return [
        row("Sale", "Purchase", "Product Price", "20.00", qty=qty, fulfillment=fulfillment),
        row("Sale", "Purchase", "Commission on Product", "-3.00", qty=qty, fulfillment=fulfillment),
        row("Sale", "Purchase", "Product tax", "1.50", qty=qty, fulfillment=fulfillment),
        row("Sale", "Purchase", "Product tax withheld", "-1.50", qty=qty, fulfillment=fulfillment),
        row("Sale", "Purchase", "Promo Code", "-2.00", qty=qty, fulfillment=fulfillment),
        row("Adjustment", "WFS Fulfillment fee", "Fee/Reimbursement", "-4.00", qty=None),
        # 店铺级和 WFS 退货处理费不进订单行
        row("Service Fee", "WFS StorageFee", "WFS Inventory Fee/Reimbursement", "-9", order=""),
        row("Adjustment", "WFS Return Processing Fee", "Fee/Reimbursement", "-1.00"),
    ]


def detail(**overrides: object) -> ShipmentDetail:
    values: dict[str, object] = {
        "shipping_list_code": CODE,
        "msku": MSKU,
        "purchase_price": Decimal("3.00"),
        "head_stock_price": Decimal("1.50"),
        "per_firstlet_cost": Decimal("2.00"),
        "per_tax": Decimal("0.00"),
        "wfs_stock_price": Decimal("6.50"),
        "currency_code": "CNY",
        "logistics_way": "合成-卡派",
    }
    values.update(overrides)
    return ShipmentDetail(**values)  # type: ignore[arg-type]


def flow(source: str | None = f"shipment:{CODE}", qty: int = 1, msku: str = MSKU) -> FlowSegment:
    return FlowSegment(
        cost_source=source,
        msku=msku,
        gtin=GTIN,
        quantity=Decimal(qty),
        business_number="7600000001",
        purchase_total=Decimal("-6.00"),
        logistics_total=Decimal("-2.00"),
        other_total=Decimal("0"),
        currency_code="CNY",
        row_hash="a" * 64,
    )


class DictLookups(Lookups):
    def __init__(self) -> None:
        self.flows: list[FlowSegment] = []
        self.details: dict[tuple[str, str], ShipmentDetail] = {}
        self.headers: dict[str, ShipmentHeader] = {}
        self.outbound: dict[str, list[OutboundOrder]] = {}
        self.entries: dict[tuple[str, str], CostEntry] = {}
        self.owners: dict[str, str] = {"SYN-ITEM-1": "owner-a"}
        self.mskus: dict[str, str] = {"SYN-ITEM-1": MSKU}
        self.item_ids: dict[str, str] = {}
        self.local_skus: dict[str, str] = {}
        self.rates: dict[str, Decimal] = {"2026-11": Decimal("7.2")}
        self.originals: dict[tuple[str, str, str], OriginalLine] = {}
        self.entry_calls: list[tuple[str, str]] = []

    def flow_segments(self, order_nos: Iterable[str], gtin: str | None) -> list[FlowSegment]:
        del gtin
        return list(self.flows) if ORDER in set(order_nos) else []

    def shipment_detail(self, code: str, msku: str) -> ShipmentDetail | None:
        return self.details.get((code, msku))

    def shipment_header(self, code: str) -> ShipmentHeader | None:
        return self.headers.get(code)

    def outbound_orders(self, platform_order_no: str) -> list[OutboundOrder]:
        return list(self.outbound.get(platform_order_no, []))

    def cost_entry(self, msku: str, scope_ref: str) -> CostEntry | None:
        self.entry_calls.append((msku, scope_ref))
        return self.entries.get((msku, scope_ref))

    def owner_for_item(self, item_id: str | None) -> str | None:
        return self.owners.get(item_id or "")

    def msku_for_item(self, item_id: str | None) -> str | None:
        return self.mskus.get(item_id or "")

    def listing_item_id(self, item_id: str | None) -> str | None:
        return self.item_ids.get(item_id or "")

    def local_sku_for_item(self, item_id: str | None) -> str | None:
        return self.local_skus.get(item_id or "")

    def fx_rate(self, month: date) -> Decimal | None:
        return self.rates.get(f"{month.year:04d}-{month.month:02d}")

    def original_line(
        self, platform_order_no: str, order_line_no: str, gtin: str | None
    ) -> OriginalLine | None:
        return self.originals.get((platform_order_no, order_line_no, gtin or ""))


def settings(**overrides: object) -> ReviewSettings:
    values: dict[str, object] = {"wfs_carrier_provider_ids": frozenset({"6899"})}
    values.update(overrides)
    return ReviewSettings(**values)  # type: ignore[arg-type]


def compute(rows: list[BillRow], lookups: DictLookups, cfg: ReviewSettings | None = None):
    groups = group_order_rows(rows)
    assert len(groups) == 1
    return compute_line(groups[0], store_id=STORE, lookups=lookups, settings=cfg or settings())


def outbound(
    number: str,
    *items: tuple[str, int | None, str | None],
    fee: str = "0",
    currency: str = "CNY",
    status: str | None = "已出库",
) -> OutboundOrder:
    """合成出库单：items = (MSKU, 件数, 分摊运费)；默认状态已出库。"""
    return OutboundOrder(
        number,
        Decimal(fee),
        currency,
        tuple(
            OutboundItem(
                msku,
                None if count is None else Decimal(count),
                None if freight is None else Decimal(freight),
                None,
            )
            for msku, count, freight in items
        ),
        status,
    )


def shipped(number: str) -> dict[str, object]:
    return {"no": number, "status": "已出库", "counted": True}


# --------------------------------------------------------------------------- 翻译表 / 归类


def test_every_known_transaction_type_has_a_chinese_name_and_a_category() -> None:
    with FIXTURE.open(encoding="utf-8") as fh:
        combos = list(csv.DictReader(fh))
    assert len(combos) >= 90
    for combo in combos:
        info = describe(
            combo["transaction_type"], combo["transaction_description"], combo["amount_type"]
        )
        assert info is not None, combo
        assert info.name_zh and "/" in info.name_zh
    assert describe("Sale", "Brand New Type", "Product Price") is None


def test_categories_follow_prp_0_3() -> None:
    assert categorize("Sale", "Purchase", "Product Price") == "sales"
    assert categorize("Refund", "Return Refund", "Product Price") == "refund"
    assert categorize("Sale", "Purchase", "Commission on Product") == "commission"
    assert categorize("Sale", "Purchase", "Product tax withheld") == "tax_withheld"
    assert categorize("Sale", "Purchase", "Total Walmart Funded Savings") == "promotion"
    assert (
        categorize("Adjustment", "WFS Fulfillment fee", "Fee/Reimbursement")
        == "wfs_fulfillment_fee"
    )
    assert categorize("Other", "WFS MultiChannelFulfillmentFee", "") == "mcf_fee"
    assert categorize("Adjustment", "WFS Return Processing Fee", "Fee/Reimbursement") == "excluded"
    assert categorize("Service Fee", "Walmart Return Shipping Charge", "Item Fees") == "return_fee"
    assert categorize("Service Fee", "WFS StorageFee", "WFS Inventory Fee/Reimbursement") == "store"
    assert categorize("Campaigns", "SEM Marketing", "SEM Marketing Fee") == "store"


# --------------------------------------------------------------------------- 分组 / 期


def test_bill_month_cutoff_and_fulfillment() -> None:
    assert bill_month_of(date(2026, 11, 3), 5) == date(2026, 10, 1)
    assert bill_month_of(date(2026, 11, 6), 5) == date(2026, 11, 1)
    assert bill_month_of(date(2026, 1, 2), 5) == date(2025, 12, 1)
    assert fulfillment_of(WFS) == "wfs"
    assert fulfillment_of(SELLER) == "seller"
    assert fulfillment_of(None) == "seller"


def test_group_drops_store_level_and_excluded_rows() -> None:
    groups = group_order_rows(sale_rows())
    assert len(groups) == 1
    assert len(groups[0].rows) == 6  # 仓储费（无订单号）和 WFS 退货处理费不进组


# --------------------------------------------------------------------------- 自动通过 / 待审


def test_shipment_with_valid_detail_and_non_wfs_carrier_auto_passes() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "合成物流商")
    line = compute(sale_rows(), lookups)
    assert line.line_kind == "sale"
    assert line.fulfillment_type == "wfs"
    assert line.quantity == Decimal("1")
    assert (line.sales_usd, line.commission_usd, line.promotion_usd) == (
        Decimal("20.00"),
        Decimal("-3.00"),
        Decimal("-2.00"),
    )
    assert line.tax_withheld_usd == Decimal("0")
    assert line.wfs_fulfillment_fee_usd == Decimal("-4.00")
    assert line.settlement_amount_usd == Decimal("11.00")
    assert (line.purchase_cny, line.head_cny, line.last_leg_cny) == (
        Decimal("3.0000"),
        Decimal("3.5000"),
        None,
    )
    assert line.cost_total_cny == Decimal("6.5000")
    assert line.cost_total_usd == Decimal("0.9028")
    assert line.fx_status == "final"
    assert line.reasons == []
    assert line.auto_passed is True
    assert line.msku == MSKU
    assert line.cost_sources[0]["kind"] == "shipment"
    assert line.content_hash == content_hash(line)


@pytest.mark.parametrize(
    ("header", "cfg", "way"),
    [
        (ShipmentHeader(CODE, "6899", "WFS"), settings(), "合成-卡派"),
        (ShipmentHeader(CODE, None, None), settings(), "合成-卡派"),
        (ShipmentHeader(CODE, "1234", "x"), settings(wfs_carrier_provider_ids=None), "合成-卡派"),
        (ShipmentHeader(CODE, "1234", "x"), settings(), "WFS-WFS-FedEx"),
        (None, settings(), "合成-卡派"),
    ],
)
def test_wfs_carrier_shipment_is_pending(
    header: ShipmentHeader | None, cfg: ReviewSettings, way: str
) -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail(logistics_way=way)
    if header is not None:
        lookups.headers[CODE] = header
    line = compute(sale_rows(), lookups, cfg)
    assert line.reasons == ["wfs_carrier_shipment"]
    assert line.auto_passed is False
    # 四项预填仍然带出来，财务点「确认」即可
    assert line.purchase_cny == Decimal("3.0000")
    assert line.cost_sources[0]["prefill"]["wfs_stock_price"] == "6.5000"


@pytest.mark.parametrize(
    "bad",
    [
        {"purchase_price": None},
        {"purchase_price": Decimal("0")},
        {"per_tax": Decimal("-1")},
        {"wfs_stock_price": Decimal("6.60")},
        {"currency_code": "USD"},
        {"logistics_way": ""},
    ],
)
def test_invalid_shipment_detail_is_pending(bad: dict[str, object]) -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail(**bad)
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    line = compute(sale_rows(), lookups)
    assert "shipment_detail_invalid" in line.reasons
    assert line.auto_passed is False


def test_missing_detail_row_is_pending() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    line = compute(sale_rows(), lookups)
    assert line.reasons == ["shipment_detail_invalid"]
    assert line.cost_total_cny is None


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("无源单配置-固定值", "fixed_value"),
        ("无源单配置-最近签收成本", "last_received"),
        (None, "cost_missing"),
        ("", "cost_missing"),
    ],
)
def test_non_shipment_sources_are_pending_with_flow_prefill(
    source: str | None, reason: str
) -> None:
    lookups = DictLookups()
    lookups.flows = [flow(source=source, qty=2)]
    line = compute(sale_rows(qty=2), lookups)
    assert line.reasons == [reason]
    assert line.cost_total_cny is None
    assert line.cost_sources[0]["prefill"] == {"purchase_cny": "3.0000", "head_cny": "1.0000"}
    assert line.cost_sources[0]["scope_ref"] == "outbound:7600000001"


def test_no_flow_row_at_all_is_cost_missing() -> None:
    line = compute(sale_rows(), DictLookups())
    assert line.reasons == ["cost_missing"]
    assert line.cost_sources[0]["scope_ref"] == f"order:{ORDER}"
    assert line.cost_sources[0]["scope_kind"] == "platform_order"


def test_two_segments_are_weighted_and_partial_coverage_is_missing() -> None:
    lookups = DictLookups()
    other = "SP2026T0002"
    lookups.flows = [flow(qty=2), flow(source=f"shipment:{other}", qty=1)]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.details[(other, MSKU)] = detail(
        shipping_list_code=other, purchase_price=Decimal("6.00"), wfs_stock_price=Decimal("9.50")
    )
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    lookups.headers[other] = ShipmentHeader(other, "1234", "x")
    line = compute(sale_rows(qty=3), lookups)
    assert line.purchase_cny == Decimal("12.0000")  # 2×3 + 1×6
    assert line.head_cny == Decimal("10.5000")  # 3×3.5
    assert line.auto_passed is True

    line = compute(sale_rows(qty=4), lookups)
    assert "cost_missing" in line.reasons
    assert line.cost_total_cny is None
    assert line.cost_sources[-1]["note"] == "flow_not_covering"


def test_owner_missing_blocks_auto_pass_and_tag_rules_are_the_lookups_job() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    lookups.owners = {}
    line = compute(sale_rows(), lookups)
    assert line.reasons == ["owner_missing"]
    assert line.auto_passed is False
    assert line.owner_id is None


def test_seller_fulfilled_prefills_last_leg_from_outbound_in_usd() -> None:
    lookups = DictLookups()
    lookups.flows = [flow(qty=2)]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "6899", "WFS")
    lookups.outbound[ORDER] = [outbound("WO1", (MSKU, 2, "4.20"), fee="4.20", currency="USD")]
    line = compute(sale_rows(SELLER, qty=2), lookups)
    assert line.fulfillment_type == "seller"
    assert line.reasons == ["self_fulfilled"]  # 自发货不叠加 wfs_carrier_shipment
    assert line.last_leg_cny == Decimal("30.2400")  # 本 MSKU 分摊 4.20 × 7.2
    assert line.cost_total_cny == Decimal("6.0000") + Decimal("7.0000") + Decimal("30.2400")
    assert line.cost_sources[0]["scope_ref"] == f"order:{ORDER}"
    assert line.cost_sources[0]["last_leg_prefill_cny"] == "15.1200"  # 单价
    assert line.cost_sources[0]["outbound_order_nos"] == [shipped("WO1")]
    assert line.auto_passed is False


def test_seller_two_goods_one_outbound_each_gets_only_its_own_freight() -> None:
    other_item, other_msku = "SYN-ITEM-2", "SYN-002"
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.mskus[other_item] = other_msku
    lookups.owners[other_item] = "owner-a"
    lookups.outbound[ORDER] = [
        outbound("WO1", (MSKU, 1, "4.00"), (other_msku, 1, "6.00"), fee="10.00")
    ]
    rows = [
        row("Sale", "Purchase", "Product Price", "20.00", fulfillment=SELLER, line="1"),
        row(
            "Sale",
            "Purchase",
            "Product Price",
            "30.00",
            fulfillment=SELLER,
            line="2",
            gtin="00000000000002",
            item=other_item,
        ),
    ]
    groups = group_order_rows(rows)
    lines = [compute_line(g, store_id=STORE, lookups=lookups, settings=settings()) for g in groups]
    legs = {line.msku: line.last_leg_cny for line in lines}
    # 各自只摊到自己的运费，合计 = 整单运费（以前整单 10 元每行各扣一次）
    assert legs == {MSKU: Decimal("4.0000"), other_msku: Decimal("6.0000")}
    assert sum(legs.values(), Decimal("0")) == Decimal("10.00")


def test_seller_one_good_two_outbounds_adds_up() -> None:
    lookups = DictLookups()
    lookups.flows = [flow(qty=2)]
    lookups.outbound[ORDER] = [
        outbound("WO1", (MSKU, 1, "3.00"), fee="3.00", currency="USD"),
        outbound("WO2", (MSKU, 1, "1.00"), fee="1.00", currency="USD"),
    ]
    line = compute(sale_rows(SELLER, qty=2), lookups)
    assert line.last_leg_cny == Decimal("28.8000")  # (3 + 1) × 7.2，拆两个包裹都算上
    assert line.cost_sources[0]["outbound_order_nos"] == [shipped("WO1"), shipped("WO2")]
    assert line.cost_sources[0]["last_leg_msku_total_cny"] == "28.8000"


@pytest.mark.parametrize(
    ("items", "note"),
    [
        ((("SYN-002", 1, "6.00"),), "msku_not_in_outbound"),
        (((MSKU, 1, None),), "apportion_freight_missing"),
        (((MSKU, None, "6.00"),), "outbound_count_missing"),
    ],
)
def test_seller_without_own_msku_freight_leaves_last_leg_empty(
    items: tuple[tuple[str, int | None, str | None], ...], note: str
) -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.outbound[ORDER] = [outbound("WO1", *items, fee="10.00")]
    line = compute(sale_rows(SELLER), lookups)
    # 不退回整单运费：尾程留空、待审
    assert line.last_leg_cny is None
    assert line.cost_total_cny is None
    assert line.reasons == ["self_fulfilled"]
    assert line.cost_sources[0]["last_leg_note"] == note
    assert line.cost_sources[0]["scope_ref"] == f"order:{ORDER}"


def test_seller_voided_outbound_is_skipped_only_shipped_one_counts() -> None:
    # 刘云龙 11-27 终审：已截单 / 已作废不计运费（以前会 5 + 6 = 11）
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.outbound[ORDER] = [
        outbound("WO1", (MSKU, 1, "5.00"), fee="5.00", status="已作废"),
        outbound("WO2", (MSKU, 1, "6.00"), fee="6.00"),
    ]
    line = compute(sale_rows(SELLER), lookups)
    assert line.last_leg_cny == Decimal("6.0000")
    assert line.cost_sources[0]["outbound_order_nos"] == [
        {"no": "WO1", "status": "已作废", "counted": False},
        shipped("WO2"),
    ]
    assert "last_leg_note" not in line.cost_sources[0]


@pytest.mark.parametrize("status", [None, "3", "物流下单"])
def test_seller_outbound_with_unverified_status_leaves_last_leg_pending(
    status: str | None,
) -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.outbound[ORDER] = [outbound("WO1", (MSKU, 1, "6.00"), fee="6.00", status=status)]
    line = compute(sale_rows(SELLER), lookups)
    # 状态确认不了：不自动算，单独的留空原因，页面显示"出库单状态待核实"
    assert line.last_leg_cny is None
    assert line.cost_total_cny is None
    assert line.reasons == ["self_fulfilled"]
    assert line.cost_sources[0]["last_leg_note"] == "outbound_status_unverified"
    assert line.cost_sources[0]["last_leg_msku_total_cny"] is None


def test_seller_all_outbounds_voided_is_not_in_outbound() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.outbound[ORDER] = [outbound("WO1", (MSKU, 1, "5.00"), status="已截单")]
    line = compute(sale_rows(SELLER), lookups)
    assert line.last_leg_cny is None
    assert line.cost_sources[0]["last_leg_note"] == "msku_not_in_outbound"


def test_seller_one_package_missing_count_blanks_the_whole_freight() -> None:
    # 两个包裹 3 + 5，其中一个没填件数：整体留空待审，不是 8 ÷ 1 全摊到一件上
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.outbound[ORDER] = [
        outbound("WO1", (MSKU, 1, "3.00"), fee="3.00"),
        outbound("WO2", (MSKU, None, "5.00"), fee="5.00"),
    ]
    line = compute(sale_rows(SELLER), lookups)
    assert line.last_leg_cny is None
    assert line.cost_total_cny is None
    assert line.cost_sources[0]["last_leg_note"] == "outbound_count_missing"
    assert line.cost_sources[0]["last_leg_msku_total_cny"] is None  # 合计也不给，免得误导
    assert line.cost_sources[0]["last_leg_prefill_cny"] is None


def test_cost_entry_on_platform_order_scope_covers_seller_line() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    lookups.outbound[ORDER] = [outbound("WO1", (MSKU, 1, "30"), fee="30")]
    lookups.entries[(MSKU, f"order:{ORDER}")] = CostEntry(
        "entry-1",
        MSKU,
        f"order:{ORDER}",
        Decimal("3.5"),
        Decimal("4"),
        Decimal("28"),
        "override",
        "pending_first",
    )
    line = compute(sale_rows(SELLER), lookups)
    assert line.reasons == ["self_fulfilled"]
    assert line.cost_entry_ids == ["entry-1"]
    assert (line.purchase_cny, line.head_cny, line.last_leg_cny) == (
        Decimal("3.5000"),
        Decimal("4.0000"),
        Decimal("28.0000"),
    )
    assert line.cost_sources[0]["kind"] == "entry"
    assert all(scope != f"shipping:{CODE}" for _, scope in lookups.entry_calls)


def test_cost_entry_on_shipping_scope_clears_shipment_reasons() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.headers[CODE] = ShipmentHeader(CODE, "6899", "WFS")
    lookups.entries[(MSKU, f"shipping:{CODE}")] = CostEntry(
        "entry-2",
        MSKU,
        f"shipping:{CODE}",
        Decimal("3"),
        Decimal("3.5"),
        None,
        "confirm",
        "pending_first",
    )
    line = compute(sale_rows(), lookups)
    assert line.reasons == []
    assert line.cost_entry_ids == ["entry-2"]
    assert line.cost_total_cny == Decimal("6.5000")
    # 套用了人工录入的段不自动通过，要走初审 / 终审（#373 复审 P1）
    assert line.auto_passed is False
    revoked = CostEntry("entry-2", MSKU, f"shipping:{CODE}", None, None, None, "confirm", "revoked")
    lookups.entries[(MSKU, f"shipping:{CODE}")] = revoked
    line = compute(sale_rows(), lookups)
    assert "shipment_detail_invalid" in line.reasons



def test_bill_store_sku_resolves_walmart_item_id_and_local_sku_via_listing() -> None:
    # 账单 Partner Item Id 是店铺 SKU；沃尔玛 ItemID、本地 SKU、MSKU、负责人都按它经 Listing 查
    lookups = DictLookups()
    line = compute(sale_rows(), lookups)
    assert (line.item_id, line.sku, line.msku, line.owner_id) == (None, None, MSKU, "owner-a")
    lookups.item_ids["SYN-ITEM-1"] = "30000000001"
    lookups.local_skus["SYN-ITEM-1"] = "SYN-L001"
    line = compute(sale_rows(), lookups)
    assert (line.item_id, line.sku) == ("30000000001", "SYN-L001")

def test_cancelled_refund_is_pending_with_zero_cost() -> None:
    rows = sale_rows(SELLER) + [
        row("Refund", "Keep-it refund", "Product Price", "-20.00", fulfillment=SELLER),
        row("Refund", "Keep-it refund", "Commission on Product", "3.00", fulfillment=SELLER),
    ]
    line = compute(rows, DictLookups())
    assert line.line_kind == "sale"
    assert line.quantity == Decimal("0")
    assert line.reasons == ["cancelled_refund"]
    assert line.cost_total_cny == Decimal("0")
    assert line.refund_usd == Decimal("-20.00")


def test_refund_line_reverses_original_cost_only_when_goods_came_back() -> None:
    refund = [
        row("Refund", "Return Refund", "Product Price", "-20.00", qty=1),
        row("Refund", "Return Refund", "Commission on Product", "3.00", qty=1),
    ]
    lookups = DictLookups()
    line = compute(refund, lookups)
    assert line.line_kind == "refund"
    # 退货入库却找不到原订单行：货本冲不了，待审（#373 复审 P3-6）
    assert line.reasons == ["cost_missing"]
    assert line.cost_total_cny is None
    assert line.auto_passed is False
    lookups.originals[(ORDER, "1", GTIN)] = OriginalLine(
        Decimal("2"), Decimal("6"), Decimal("7"), None, True, MSKU
    )
    line = compute(refund, lookups)
    assert line.quantity == Decimal("-1")
    assert (line.purchase_cny, line.head_cny) == (Decimal("-3.0000"), Decimal("-3.5000"))
    assert line.cost_total_cny == Decimal("-6.5000")
    assert line.reasons == []
    assert line.auto_passed is True

    keep = [row("Refund", "Keep-it refund", "Product Price", "-20.00", qty=1)]
    line = compute(keep, lookups)
    assert line.cost_total_cny == Decimal("0")


def test_mcf_line_follows_wfs_rules_not_seller() -> None:
    rows = [
        row("Other", "WFS MultiChannelFulfillmentFee", "", "-6.00", qty=None, fulfillment=""),
        row("Sale", "Purchase", "Product Price", "20.00", qty=1, fulfillment=""),
    ]
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    lookups.outbound[ORDER] = [outbound("WO1", (MSKU, 1, "30"), fee="30")]
    line = compute(rows, lookups)
    assert line.line_kind == "sale"  # 同组里有 Product Price 销售行
    mcf_only = compute(rows[:1], lookups)
    assert mcf_only.line_kind == "mcf"
    assert mcf_only.fulfillment_type == "wfs"
    assert mcf_only.mcf_fee_usd == Decimal("-6.00")
    assert "self_fulfilled" not in mcf_only.reasons
    assert mcf_only.last_leg_cny is None
    assert mcf_only.cost_sources[0]["scope_ref"] == f"shipping:{CODE}"


def test_refund_reversal_goes_to_refund_column() -> None:
    assert (
        categorize("Dispute Settlement", "Customer Return Reversal", "Fee/Reimbursement")
        == "refund"
    )
    assert (
        categorize(
            "Adjustment",
            "CUSTOMER RETURN REFUND REVERSAL-LOST LATER DELIVERED",
            "Fee/Reimbursement",
        )
        == "refund"
    )
    assert categorize("Service Fee", "Walmart Return Shipping Charge", "Item Fees") == "return_fee"


def test_fx_missing_leaves_usd_cost_empty() -> None:
    lookups = DictLookups()
    lookups.rates = {}
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    line = compute(sale_rows(), lookups)
    assert (line.fx_status, line.fx_rate, line.cost_total_usd) == ("missing", None, None)
    assert line.cost_total_cny == Decimal("6.5000")


def test_content_hash_ignores_nothing_business_and_changes_with_cost() -> None:
    lookups = DictLookups()
    lookups.flows = [flow()]
    lookups.details[(CODE, MSKU)] = detail()
    lookups.headers[CODE] = ShipmentHeader(CODE, "1234", "x")
    first = compute(sale_rows(), lookups)
    second = compute(sale_rows(), lookups)
    assert first.content_hash == second.content_hash
    lookups.details[(CODE, MSKU)] = detail(
        purchase_price=Decimal("3.10"), wfs_stock_price=Decimal("6.60")
    )
    third = compute(sale_rows(), lookups)
    assert third.content_hash != first.content_hash
