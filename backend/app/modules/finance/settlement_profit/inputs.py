"""In-memory inputs of one (store, bill month) calculation.

Loaders fill these from the tables; the engine never touches the database.  Two sources
are not on main yet and are filled by protocol-implementing loaders once they land:
``fact_walmart_settlement_lines`` (#290 implementation) and
``ods_lingxing_wfs_cost_valuation_flow`` (inventory-claim PR 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class SettlementKind(StrEnum):
    """Normalised settlement line kinds (the #290 loader maps Walmart types onto these)."""

    # order level (§0.1 / §0.2): carry an order number
    SALE = "sale"
    PLATFORM_SUBSIDY = "platform_subsidy"
    REFUND = "refund"
    COMMISSION = "commission"
    WFS_FULFILLMENT = "wfs_fulfillment"
    RETURN_FEE = "return_fee"
    TAX_WITHHELD = "tax_withheld"
    # item level (§0.3): no order number
    WFS_SERVICE = "wfs_service"
    DISPOSAL_FEE = "disposal_fee"
    STORAGE_FEE = "storage_fee"
    REVIEW_ACCELERATOR = "review_accelerator"
    # not in settlement profit (§0.1) — 其他业务收入
    AD_SUBSIDY = "ad_subsidy"
    MISC_INVOICE = "misc_invoice"
    # shown as difference only (§8.8)
    AD_CHARGE = "ad_charge"
    INBOUND_WPC = "inbound_wpc"
    # anything else that carries no product: goes to 待指定
    OTHER = "other"


ORDER_KINDS = frozenset(
    {
        SettlementKind.SALE,
        SettlementKind.PLATFORM_SUBSIDY,
        SettlementKind.REFUND,
        SettlementKind.COMMISSION,
        SettlementKind.WFS_FULFILLMENT,
        SettlementKind.RETURN_FEE,
        SettlementKind.TAX_WITHHELD,
    }
)
OTHER_INCOME_KINDS = frozenset({SettlementKind.AD_SUBSIDY, SettlementKind.MISC_INVOICE})
DIFF_ONLY_KINDS = frozenset({SettlementKind.AD_CHARGE, SettlementKind.INBOUND_WPC})


@dataclass(frozen=True)
class SettlementLine:
    """One ``fact_walmart_settlement_lines`` row (amount signed: income +, fee −)."""

    source_row_hash: str
    report_key: str
    report_date: date
    kind: SettlementKind
    amount_usd: Decimal
    platform_order_no: str | None = None
    order_item_no: str | None = None
    gtin: str | None = None
    item_id: str | None = None
    quantity: Decimal = Decimal("0")
    posted_at: datetime | None = None


@dataclass(frozen=True)
class OrderTimes:
    """Lingxing 多平台结算利润-订单 (ods_lingxing_mp_profit_order_lines)."""

    ordered_at: datetime | None = None
    shipped_at: datetime | None = None
    msku: str | None = None
    serial_number: str | None = None


@dataclass(frozen=True)
class FifoCost:
    """FIFO cost of one order + GTIN from the cost valuation flow (¥, is_current rows)."""

    purchase_cny: Decimal | None
    head_cny: Decimal | None
    other_cny: Decimal | None = None


@dataclass(frozen=True)
class FeeDetailLine:
    """ods_walmart_wfs_fee_detail_lines: GTIN weights for WFS service / disposal fees."""

    fee_type: str
    amount_usd: Decimal
    transaction_date: date
    gtin: str | None


@dataclass(frozen=True)
class StorageShare:
    item_id: str
    amount_usd: Decimal  # report amount, used as weight only


@dataclass(frozen=True)
class StorageReport:
    period_start: date
    period_end: date
    shares: tuple[StorageShare, ...]
    is_latest_fallback: bool = False  # 该期没有报表，用最近账期并标注 (§0.3)


@dataclass(frozen=True)
class ReviewSnapshotItem:
    item_id: str
    reviews_collected: int


@dataclass(frozen=True)
class ReviewAcceleratorInput:
    current: tuple[ReviewSnapshotItem, ...] | None  # None: snapshot missing
    previous: tuple[ReviewSnapshotItem, ...] | None  # None: first period
    price_by_item: dict[str, Decimal | None] = field(default_factory=dict)


@dataclass(frozen=True)
class FlowMovement:
    """One is_current row of ods_lingxing_wfs_cost_valuation_flow (inventory movement)."""

    flow_id: str
    row_hash: str
    store_code: str
    store_id: str | None  # None ⇔ store_mapping_status = unmapped
    business_type: str
    occurred_at: datetime
    quantity: Decimal
    goods_value_cny: Decimal | None
    serial_number: str | None = None
    gtin: str | None = None
    msku: str | None = None
    destination: str | None = None
    sync_batch_id: str | None = None


@dataclass(frozen=True)
class Adjustment:
    """Active manual_settlement_order_adjustments row."""

    id: str
    line_key: str
    kind: str  # cost / amount / assign_item / assign_store / note
    payload: dict[str, object]
    acted_at: datetime


@dataclass(frozen=True)
class ReviewAction:
    line_key: str
    stage: str  # first / final
    decision: str  # pass / reject
    acted_at: datetime


@dataclass
class StoreMonthInput:
    store_id: str
    bill_month: date
    fx_rate: Decimal | None
    settlement_lines: list[SettlementLine]
    order_times: dict[tuple[str, str], OrderTimes] = field(default_factory=dict)
    fifo: dict[tuple[str, str], FifoCost] = field(default_factory=dict)  # (order no, gtin)
    gtin_to_item: dict[str, str] = field(default_factory=dict)
    msku_to_item: dict[str, str] = field(default_factory=dict)
    owner_by_item: dict[str, str | None] = field(default_factory=dict)
    fee_details: list[FeeDetailLine] = field(default_factory=list)
    storage_report: StorageReport | None = None
    review_accelerator: ReviewAcceleratorInput | None = None
    ad_cost_by_item: dict[str, Decimal] = field(default_factory=dict)  # positive cost
    ad_scope_note: str | None = "sp_only"
    movements: list[FlowMovement] = field(default_factory=list)  # store's + manually assigned
    adjustments: list[Adjustment] = field(default_factory=list)
    review_actions: list[ReviewAction] = field(default_factory=list)
    # line_key → latest acted_at / revoked_at of any adjustment, revoked ones included (§8.9)
    adjustment_changed_at: dict[str, datetime] = field(default_factory=dict)
