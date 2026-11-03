"""Synthetic settlement profit fixtures (no real order numbers or amounts)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D

from app.modules.finance.settlement_profit.inputs import (
    FeeDetailLine,
    FifoCost,
    FlowMovement,
    SettlementKind,
    SettlementLine,
    StorageReport,
    StorageShare,
    StoreMonthInput,
)

MONTH = date(2030, 1, 1)
STORE = "store-a"
RATE = D("7.0000")
REPORT = "rk-0001"


def line(
    kind: SettlementKind, amount: str, order: str | None = None, **kw: object
) -> SettlementLine:
    n = kw.pop("n", 0)
    return SettlementLine(
        source_row_hash=f"h-{kind.value}-{order}-{amount}-{n}",
        report_key=REPORT,
        report_date=date(2030, 1, 20),
        kind=kind,
        amount_usd=D(amount),
        platform_order_no=order,
        order_item_no="1" if order else None,
        gtin=kw.pop("gtin", "G1" if order else None),  # type: ignore[arg-type]
        quantity=D(str(kw.pop("quantity", "0"))),
        **kw,  # type: ignore[arg-type]
    )


def movement(
    business_type: str,
    *,
    store_id: str | None = STORE,
    row_hash: str = "flow-hash-1",
    flow_id: str = "00000000-0000-0000-0000-000000000001",
    value: str = "70",
    gtin: str | None = "G1",
) -> FlowMovement:
    return FlowMovement(
        flow_id=flow_id,
        row_hash=row_hash,
        store_code="SC-1",
        store_id=store_id,
        business_type=business_type,
        occurred_at=datetime(2030, 1, 15, tzinfo=UTC),
        quantity=D("1"),
        goods_value_cny=D(value),
        serial_number="SN-SYN-1",
        gtin=gtin,
    )


def base_input(**overrides: object) -> StoreMonthInput:
    """Two orders of item I1 (G1) and one of I2 (G2), store-level fees with weights."""
    lines = [
        line(SettlementKind.SALE, "30.00", "SYN-O1", quantity=1),
        line(SettlementKind.COMMISSION, "-4.50", "SYN-O1"),
        line(SettlementKind.SALE, "60.00", "SYN-O2", quantity=2),
        line(SettlementKind.COMMISSION, "-9.00", "SYN-O2"),
        line(SettlementKind.SALE, "10.00", "SYN-O3", gtin="G2", quantity=1),
        line(SettlementKind.WFS_SERVICE, "-3.00"),
        line(SettlementKind.DISPOSAL_FEE, "-1.00"),
        line(SettlementKind.STORAGE_FEE, "-2.00"),
        line(SettlementKind.AD_CHARGE, "-50.00"),
        line(SettlementKind.INBOUND_WPC, "-5.00"),
        line(SettlementKind.AD_SUBSIDY, "8.00"),
    ]
    inp = StoreMonthInput(
        store_id=STORE,
        bill_month=MONTH,
        fx_rate=RATE,
        settlement_lines=lines,
        gtin_to_item={"G1": "I1", "G2": "I2"},
        owner_by_item={"I1": "owner-x", "I2": "owner-y"},
        fifo={
            ("SYN-O1", "G1"): FifoCost(D("35"), D("7")),
            ("SYN-O2", "G1"): FifoCost(D("70"), D("14")),
            ("SYN-O3", "G2"): FifoCost(D("14"), D("7")),
        },
        fee_details=[
            FeeDetailLine("WFS_Prep", D("-2.00"), date(2030, 1, 10), "G1"),
            FeeDetailLine("WFS_Prep", D("-1.00"), date(2030, 1, 10), "G2"),
            FeeDetailLine("RC_InventoryDisposalFee", D("-1.00"), date(2030, 1, 10), "G1"),
        ],
        storage_report=StorageReport(
            date(2030, 1, 1),
            date(2030, 1, 31),
            (StorageShare("I1", D("3")), StorageShare("I2", D("1"))),
        ),
        ad_cost_by_item={"I1": D("40.00"), "I2": D("10.00")},
    )
    for k, v in overrides.items():
        setattr(inp, k, v)
    return inp
