"""结算利润 V3 存储（PRP finance-settlement-profit-v3 §6.2，PR-1 只建表）。

分层：RAW（既有 ods_api_raw_*）→ ODS → FACT → MART；manual_ 只覆盖计算结果，不写
RAW / ODS / FACT；cfg_ 是财务设置。本模块只声明表结构：同步（PR-2）、订单审核计算与
页面、结算利润计算与页面在后续 PR 交付。

约定（PRP §6.2 / §8）：
- 金额 numeric(18,4)，列名带币种后缀（_usd / _cny）或配 currency_code；有折算的行同时存
  fx_rate、fx_month、fx_status（final / missing；missing 时 CNY 与 fx_rate 为空，不兜底）；
- 外部 ID（订单号、GTIN、item_id、店铺 ID、发货单号、出库单号、report_key）一律字符串；
- period_key = 回款对账的期（mart_walmart_bill_periods.report_key）；bill_month / 月份列
  一律是当月 1 号（CHECK）；
- FACT / MART 行带 calc_version 与 content_hash（同一输入重算 hash 不变则不写新版本）；
  manual_ 表引用稳定业务键 line_key，不引用会随重算变化的 UUID；
- 结账冻结：FACT / MART 行的 frozen_at / frozen_by / frozen_calc_version。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(18, 4)
FX_RATE = Numeric(18, 8)
# 件数（可能有小数，如平均在库件数）；和金额分开定义，不复用 MONEY
QTY = Numeric(18, 4)
LINE_KEY = String(320)
# 汇率齐（final）时必须有汇率，缺汇率（missing）时汇率必须为空，不兜底
FX_RATE_MATCHES_STATUS = "(fx_status = 'final') = (fx_rate IS NOT NULL)"
# 成本录入的范围标识必须由发货单号 / 出库单号推出，写入方拼错会被数据库拒绝
SCOPE_REF_MATCHES = (
    "scope_ref = CASE WHEN shipping_list_code IS NOT NULL "
    "THEN 'shipping:' || shipping_list_code ELSE 'outbound:' || outbound_order_no END"
)

FX_STATUSES = ("final", "missing")
# 订单行待审原因（§8.4，订单行 8 个）；店铺级项目只有 price_missing（§8.6）。
ORDER_LINE_REASONS = (
    "wfs_carrier_shipment",
    "self_fulfilled",
    "fixed_value",
    "last_received",
    "cost_missing",
    "shipment_detail_invalid",
    "owner_missing",
    "cancelled_refund",
)
STORE_ITEM_REASONS = ("price_missing",)
LINE_KINDS = ("sale", "refund", "mcf")
FULFILLMENT_TYPES = ("wfs", "seller")
REVIEW_STATUSES = ("pending", "auto", "first_passed", "final_passed", "rejected")
REVIEW_ROW_KINDS = ("order", "store_item", "reconcile_diff")
STORE_ITEM_KINDS = (
    "review_accelerator",
    "discount_back",
    "transfer_fee",
    "mcf",
    "storage_fee",
    "other_wfs_service",
    "company_cost",
    "unassigned_bill",
    "unassigned_wfs",
)
ASSIGN_STATUSES = ("assigned", "pending", "not_applicable")
RECONCILE_STATUSES = ("ok", "reconcile_failed", "unassigned_pending")
POST_CLOSE_DIFF_STATUSES = ("open", "acknowledged", "resolved_by_unlock")
COST_ENTRY_KINDS = ("confirm", "override")
MANUAL_STATUSES = ("pending_first", "first_passed", "final_passed", "rejected", "revoked")
ADJUSTMENT_KINDS = ("amount", "assign_item", "note")
ADJUSTMENT_STATUSES = ("active", "revoked")
REVIEW_TARGETS = ("order_line", "store_item", "cost_entry", "adjustment")
REVIEW_STAGES = ("first", "final")
REVIEW_DECISIONS = ("pass", "reject", "revert")
MONTH_CLOSE_ACTIONS = ("close", "unlock")
# §0.5 六项 + §8.3 WFS 承运商清单；默认值与人名只在生产库配置，仓库里不出现。
SETTING_KEYS = (
    "review_accelerator_price_formula",
    "company_cost_allocation",
    "fixed_cost_fallback",
    "review_accelerator_snapshot_frequency",
    "no_order_months",
    "bill_month_cutoff_day",
    "wfs_carrier_provider_ids",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _first_of_month(column: str) -> str:
    return f"EXTRACT(DAY FROM {column}) = 1"


def _json_list() -> Any:
    return mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))


def _json_dict() -> Any:
    return mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


def _money() -> Any:
    return mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default=text("0"))


def _qty() -> Any:
    return mapped_column(QTY, nullable=False, default=Decimal("0"), server_default=text("0"))


def _version() -> Any:
    return mapped_column(Integer, nullable=False, default=1, server_default=text("1"))


class _Created:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class _Timestamps(_Created):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class _Ods(_Timestamps):
    """领星 / 沃尔玛同步落地的公共列：来源账号、店铺、同步批次、RAW 引用、原始行、行 hash。"""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_run_id: Mapped[UUID | None] = mapped_column()
    source_raw_request_ref_id: Mapped[UUID | None] = mapped_column()
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_row: Mapped[dict[str, Any]] = _json_dict()


class _Fx:
    fx_rate: Mapped[Decimal | None] = mapped_column(FX_RATE)
    fx_month: Mapped[date | None] = mapped_column(Date)
    fx_status: Mapped[str] = mapped_column(
        String(8), nullable=False, default="missing", server_default=text("'missing'")
    )


class _Calc:
    """计算结果的版本、内容 hash 与结账冻结。"""

    calc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frozen_by: Mapped[str | None] = mapped_column(String(255))
    frozen_calc_version: Mapped[int | None] = mapped_column(Integer)


class _Actor:
    """写操作的操作人、角色、请求号（§5：全部写操作留痕）。"""

    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))


# --------------------------------------------------------------------------- ODS


class FinShippingList(_Ods, Base):
    """领星多平台发货单（/basicOpen/multiplatform/query/shippingList v2）当前状态。

    与 PMC #282 的 ods_lingxing_wfs_shipping_lists（每次运行一份快照）不同名、互不依赖。
    """

    __tablename__ = "ods_lingxing_fin_shipping_lists"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "shipping_list_code",
            name="uq_ods_lx_fin_shipping_list",
        ),
        CheckConstraint("shipping_list_code <> ''", name="shipping_list_code_not_blank"),
    )

    shipping_list_code: Mapped[str] = mapped_column(String(64), nullable=False)
    shipping_list_status: Mapped[str | None] = mapped_column(String(32))
    logistics_provider_id: Mapped[str | None] = mapped_column(String(64))
    logistics_provider_name: Mapped[str | None] = mapped_column(Text)
    logistics_channel_name: Mapped[str | None] = mapped_column(Text)
    head_fee_type: Mapped[str | None] = mapped_column(String(32))
    warehouse_id: Mapped[str | None] = mapped_column(String(64))
    delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lx_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FinShippingDetailItem(_Ods, Base):
    """领星发货单明细（shippingDetail.firstLetListResponseList），一行 = 发货单 × MSKU。

    货本字段映射（§8.3）：采购价 purchase_price、出库头程 head_stock_price、头程费用
    per_firstlet_cost（= per_firstlet_actual，已含 other_cost）、税 per_tax、单位成本
    wfs_stock_price（¥）。
    """

    __tablename__ = "ods_lingxing_fin_shipping_detail_items"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "shipping_list_code",
            "msku",
            name="uq_ods_lx_fin_shipping_detail_item",
        ),
        Index("ix_ods_lx_fin_shipping_detail_store_msku", "store_id", "msku"),
    )

    shipping_list_code: Mapped[str] = mapped_column(String(64), nullable=False)
    msku: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(String(64))
    purchase_price: Mapped[Decimal | None] = mapped_column(MONEY)
    head_stock_price: Mapped[Decimal | None] = mapped_column(MONEY)
    per_firstlet_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    per_firstlet_actual: Mapped[Decimal | None] = mapped_column(MONEY)
    per_firstlet_expected: Mapped[Decimal | None] = mapped_column(MONEY)
    per_tax: Mapped[Decimal | None] = mapped_column(MONEY)
    wfs_stock_price: Mapped[Decimal | None] = mapped_column(MONEY)
    other_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    transportation_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    logistics_way: Mapped[str | None] = mapped_column(Text)
    logistics_provider_id: Mapped[str | None] = mapped_column(String(64))
    head_fee_type: Mapped[str | None] = mapped_column(String(32))
    value_source: Mapped[str | None] = mapped_column(String(32))
    delivery_num: Mapped[Decimal | None] = mapped_column(QTY)


class FinWmsOutboundOrder(_Ods, Base):
    """领星销售出库单（wmsOrderList）：非 WFS 自发货订单的尾程物流费用，按平台订单号。

    字段以 PR-2 同步时的接口返回为准；这里只落计算要用的列，其余进 raw_row。
    """

    __tablename__ = "ods_lingxing_fin_wms_outbound_orders"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "outbound_order_no",
            name="uq_ods_lx_fin_wms_outbound_order",
        ),
        Index("ix_ods_lx_fin_wms_outbound_platform_order", "store_id", "platform_order_no"),
        CheckConstraint("outbound_order_no <> ''", name="outbound_order_no_not_blank"),
    )

    outbound_order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_order_no: Mapped[str | None] = mapped_column(String(64))
    order_status: Mapped[str | None] = mapped_column(String(32))
    logistics_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[dict[str, Any]]] = _json_list()


class ReviewAcceleratorSnapshot(_Ods, Base):
    """评价加速器报名清单快照（云函数 POST /v3/growth/reviews-accelerator/items，翻 scrollId）。

    只当分摊权重用（§8.6）：接口没有费用金额，也没有费用与评论的对应关系。
    """

    __tablename__ = "ods_walmart_review_accelerator_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_account_ref",
            "store_id",
            "snapshot_date",
            "item_id",
            name="uq_ods_wm_review_accelerator_snapshot",
        ),
        Index("ix_ods_wm_review_accelerator_item", "store_id", "item_id", "snapshot_date"),
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(32))
    reviews_collected: Mapped[int | None] = mapped_column(Integer)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- FACT


class SettlementOrderLine(_Calc, _Fx, _Created, Base):
    """订单审核的订单行（一期一行一订单行）：收入、费用、货本三项、成本来源、待审原因。

    line_key = 店铺 + reportKey + 订单号 + 订单行号 + GTIN（§8.11）。WFS 订单的尾程 =
    结算单配送费，只展示、不计入货本合计（cost_total_cny 不含它）。
    """

    __tablename__ = "fact_settlement_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "period_key",
            "calc_version",
            "line_key",
            name="uq_fact_settlement_order_line",
        ),
        Index("ix_fact_settlement_order_lines_current", "store_id", "period_key", "is_current"),
        # 同店同期同一订单行只能有一个当前版本，否则利润 / 对平 / 审核页会重复计算
        Index(
            "uq_fact_settlement_order_line_current",
            "store_id",
            "period_key",
            "line_key",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_fact_settlement_order_lines_item", "store_id", "bill_month", "item_id"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("line_kind", LINE_KINDS), name="line_kind"),
        CheckConstraint(_in("fulfillment_type", FULFILLMENT_TYPES), name="fulfillment_type"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="fx_status"),
        CheckConstraint(FX_RATE_MATCHES_STATUS, name="fx_rate_matches_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    line_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    fulfillment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    order_line_no: Mapped[str] = mapped_column(String(32), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(Text)
    msku: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(128))
    posted_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal] = _qty()
    transaction_types: Mapped[list[str]] = _json_list()
    # 收入与订单费用（USD，结算单口径；正 = 收入，负 = 扣费）
    sales_usd: Mapped[Decimal] = _money()
    refund_usd: Mapped[Decimal] = _money()
    promotion_usd: Mapped[Decimal] = _money()
    commission_usd: Mapped[Decimal] = _money()
    return_fee_usd: Mapped[Decimal] = _money()
    tax_withheld_usd: Mapped[Decimal] = _money()
    wfs_fulfillment_fee_usd: Mapped[Decimal] = _money()
    mcf_fee_usd: Mapped[Decimal] = _money()
    ad_allocated_usd: Mapped[Decimal] = _money()
    settlement_amount_usd: Mapped[Decimal] = _money()
    # 货本三项（CNY）；尾程只在非 WFS 自发货订单计入
    purchase_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    head_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    last_leg_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_total_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_total_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_sources: Mapped[list[dict[str, Any]]] = _json_list()
    cost_entry_ids: Mapped[list[str]] = _json_list()
    reasons: Mapped[list[str]] = _json_list()
    auto_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    source_run_ids: Mapped[list[str]] = _json_list()


class SettlementStoreMonthItem(_Calc, _Fx, _Timestamps, Base):
    """店铺 × 账单月的店铺级项目：评价加速器、返还、调拨、MCF、仓储费、公司级费用、待指定。

    待指定（§8.12）也存这里：assign_status = pending；source_kind 区分来自结算单行
    （unassigned_bill，参与对平）与来自 WFS 费用表（unassigned_wfs，不参与对平但挡结账）。
    """

    __tablename__ = "fact_settlement_store_month_items"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "bill_month",
            "source_kind",
            "source_ref",
            name="uq_fact_settlement_store_month_item",
        ),
        Index("ix_fact_settlement_store_month_items_line", "line_key"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("source_kind", STORE_ITEM_KINDS), name="source_kind"),
        CheckConstraint(_in("assign_status", ASSIGN_STATUSES), name="assign_status"),
        CheckConstraint(_in("review_status", REVIEW_STATUSES), name="review_status"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="fx_status"),
        CheckConstraint(FX_RATE_MATCHES_STATUS, name="fx_rate_matches_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    period_key: Mapped[str | None] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    transaction_type: Mapped[str | None] = mapped_column(String(128))
    amount_usd: Mapped[Decimal] = _money()
    amount_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    allocation_method: Mapped[str | None] = mapped_column(String(32))
    allocation: Mapped[dict[str, Any]] = _json_dict()
    reasons: Mapped[list[str]] = _json_list()
    notes: Mapped[list[str]] = _json_list()
    assign_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="assigned", server_default=text("'assigned'")
    )
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    version: Mapped[int] = _version()


class SettlementPostCloseDiff(_Created, Base):
    """结账后源数据变化：只记旧值 / 新值，不改冻结数（§8.11）。"""

    __tablename__ = "fact_settlement_post_close_diffs"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "bill_month",
            "line_key",
            "detected_at",
            name="uq_fact_settlement_post_close_diff",
        ),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("status", POST_CLOSE_DIFF_STATUSES), name="status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    frozen_calc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    new_calc_version: Mapped[int | None] = mapped_column(Integer)
    old_values: Mapped[dict[str, Any]] = _json_dict()
    new_values: Mapped[dict[str, Any]] = _json_dict()
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="open", server_default=text("'open'")
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- MART


class SettlementProfitItemMonth(_Calc, _Fx, _Timestamps, Base):
    """结算利润：店铺 × ItemID × 账单月（§0.3 各列；店铺合计单列项在店铺级项目表）。"""

    __tablename__ = "mart_settlement_profit_item_month"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_profit_item_month"
        ),
        Index("ix_mart_settlement_profit_item_month_owner", "owner_id", "bill_month"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("fx_status", FX_STATUSES), name="fx_status"),
        CheckConstraint(FX_RATE_MATCHES_STATUS, name="fx_rate_matches_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    sku: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[Decimal] = _qty()
    sales_usd: Mapped[Decimal] = _money()
    refund_usd: Mapped[Decimal] = _money()
    promotion_usd: Mapped[Decimal] = _money()
    commission_usd: Mapped[Decimal] = _money()
    return_fee_usd: Mapped[Decimal] = _money()
    tax_withheld_usd: Mapped[Decimal] = _money()
    wfs_fulfillment_fee_usd: Mapped[Decimal] = _money()
    storage_fee_usd: Mapped[Decimal] = _money()
    transfer_fee_usd: Mapped[Decimal] = _money()
    mcf_fee_usd: Mapped[Decimal] = _money()
    review_accelerator_usd: Mapped[Decimal] = _money()
    other_wfs_service_usd: Mapped[Decimal] = _money()
    disposal_loss_usd: Mapped[Decimal] = _money()
    packing_fee_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    ad_sp_usd: Mapped[Decimal] = _money()
    ad_sb_usd: Mapped[Decimal] = _money()
    ad_sv_usd: Mapped[Decimal] = _money()
    sem_usd: Mapped[Decimal] = _money()
    purchase_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    head_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    last_leg_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_total_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    settlement_profit_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    settlement_profit_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    company_cost_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    net_profit_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    flags: Mapped[list[str]] = _json_list()


class SettlementOrderReview(_Calc, _Timestamps, Base):
    """订单审核页的行：订单行、店铺级项目、对平差额行（row_kind），带审核状态与乐观锁。"""

    __tablename__ = "mart_settlement_order_review"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "period_key", "line_key", name="uq_mart_settlement_order_review"
        ),
        Index("ix_mart_settlement_order_review_status", "store_id", "period_key", "review_status"),
        Index("ix_mart_settlement_order_review_order", "platform_order_no"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("row_kind", REVIEW_ROW_KINDS), name="row_kind"),
        CheckConstraint(_in("review_status", REVIEW_STATUSES), name="review_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    row_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_order_no: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(Text)
    msku: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(128))
    transaction_types: Mapped[list[str]] = _json_list()
    reasons: Mapped[list[str]] = _json_list()
    settlement_amount_usd: Mapped[Decimal] = _money()
    cost_total_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    first_reviewed_by: Mapped[str | None] = mapped_column(String(255))
    first_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_reviewed_by: Mapped[str | None] = mapped_column(String(255))
    final_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = _version()


class SettlementReconcileStorePeriod(_Calc, _Timestamps, Base):
    """每店每期对平（§8.10）：结算单总额 = 订单行 + 分摊的店铺级费用 + 店铺级审核项目
    + 店铺合计单列项 + 待指定（只算来自结算单的）；|差额| ≤ $0.01 为 ok。"""

    __tablename__ = "mart_settlement_reconcile_store_period"
    __table_args__ = (
        UniqueConstraint("store_id", "period_key", name="uq_mart_settlement_reconcile_period"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("status", RECONCILE_STATUSES), name="status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    bill_total_usd: Mapped[Decimal] = _money()
    order_lines_usd: Mapped[Decimal] = _money()
    item_allocated_usd: Mapped[Decimal] = _money()
    store_items_usd: Mapped[Decimal] = _money()
    store_columns_usd: Mapped[Decimal] = _money()
    pending_usd: Mapped[Decimal] = _money()
    diff_usd: Mapped[Decimal] = _money()
    wfs_detail_vs_bill_usd: Mapped[Decimal] = _money()
    inbound_vs_bill_usd: Mapped[Decimal] = _money()
    ad_vs_bill_usd: Mapped[Decimal] = _money()
    company_income_usd: Mapped[Decimal] = _money()
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[dict[str, Any]] = _json_dict()


class SettlementNoOrderFlag(_Calc, _Timestamps, Base):
    """无订单标记（§8.9）：连续 N 个账单月无销售订单且 WFS 有库存；只给财务分析用。"""

    __tablename__ = "mart_settlement_no_order_flags"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "item_id", "bill_month", name="uq_mart_settlement_no_order_flag"
        ),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(128))
    months_without_order: Mapped[int] = mapped_column(Integer, nullable=False)
    last_order_date: Mapped[date | None] = mapped_column(Date)
    wfs_inventory_qty: Mapped[Decimal | None] = mapped_column(QTY)
    inventory_snapshot_date: Mapped[date | None] = mapped_column(Date)
    storage_fee_cum_usd: Mapped[Decimal] = _money()
    disposal_loss_cum_usd: Mapped[Decimal] = _money()


# --------------------------------------------------------------------------- MANUAL


class SettlementCostEntry(_Actor, _Timestamps, Base):
    """订单审核录成本 / 确认（§8.4）：范围 = MSKU × 发货单（或 MSKU × 出库单），一次录入覆盖
    范围内所有订单行（含跨期）；不回写领星。同一范围同时只有一条未撤销的录入。"""

    __tablename__ = "manual_settlement_cost_entries"
    __table_args__ = (
        Index(
            "uq_manual_settlement_cost_entry_active",
            "store_id",
            "msku",
            "scope_ref",
            unique=True,
            postgresql_where=text("status <> 'revoked'"),
        ),
        UniqueConstraint("idempotency_key", name="uq_manual_settlement_cost_entry_idem"),
        CheckConstraint(_in("entry_kind", COST_ENTRY_KINDS), name="entry_kind"),
        CheckConstraint(_in("status", MANUAL_STATUSES), name="status"),
        CheckConstraint(
            "(shipping_list_code IS NULL) <> (outbound_order_no IS NULL)", name="one_scope"
        ),
        CheckConstraint(SCOPE_REF_MATCHES, name="scope_ref_matches"),
        CheckConstraint(
            "entry_kind <> 'override' OR coalesce(reason, '') <> ''", name="override_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    msku: Mapped[str] = mapped_column(Text, nullable=False)
    shipping_list_code: Mapped[str | None] = mapped_column(String(64))
    outbound_order_no: Mapped[str | None] = mapped_column(String(64))
    # scope_ref = 'shipping:<发货单号>' 或 'outbound:<出库单号>'，给唯一索引用
    scope_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    purchase_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    head_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    last_leg_cny: Mapped[Decimal | None] = mapped_column(MONEY)
    entry_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    prefilled: Mapped[dict[str, Any]] = _json_dict()
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending_first", server_default=text("'pending_first'")
    )
    version: Mapped[int] = _version()
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    revoked_by: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class SettlementSemMonth(_Timestamps, Base):
    """SEM 月值（旧系统下线前，财务从旧系统广告板块导出后人工导入）。"""

    __tablename__ = "manual_settlement_sem_month"
    __table_args__ = (
        UniqueConstraint("store_id", "item_id", "bill_month", name="uq_manual_settlement_sem"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    sem_usd: Mapped[Decimal] = _money()
    source_file_name: Mapped[str | None] = mapped_column(String(255))
    imported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))


class SettlementOrderAdjustment(_Actor, _Timestamps, Base):
    """财务调整（§8.11）：改金额、指定商品（待指定 → ItemID）、备注；乐观锁 + 可撤销。"""

    __tablename__ = "manual_settlement_order_adjustments"
    __table_args__ = (
        Index("ix_manual_settlement_adjustments_line", "line_key"),
        Index("ix_manual_settlement_adjustments_month", "store_id", "bill_month"),
        UniqueConstraint("idempotency_key", name="uq_manual_settlement_adjustment_idem"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("kind", ADJUSTMENT_KINDS), name="kind"),
        CheckConstraint(_in("status", ADJUSTMENT_STATUSES), name="status"),
        CheckConstraint(_in("review_status", MANUAL_STATUSES), name="review_status"),
        CheckConstraint("kind <> 'assign_item' OR target_item_id IS NOT NULL", name="assign_item"),
        CheckConstraint("kind <> 'amount' OR amount_usd IS NOT NULL", name="amount_value"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    period_key: Mapped[str | None] = mapped_column(String(64))
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_field: Mapped[str | None] = mapped_column(String(64))
    amount_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    target_item_id: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending_first", server_default=text("'pending_first'")
    )
    version: Mapped[int] = _version()
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    revoked_by: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class SettlementReviewAction(_Actor, Base):
    """初审 / 终审 / 退回记录（只增不改）；同一人不可对同一对象既初审又终审（服务层校验）。"""

    __tablename__ = "manual_settlement_review_actions"
    __table_args__ = (
        Index("ix_manual_settlement_review_line", "line_key", "acted_at"),
        Index("ix_manual_settlement_review_month", "store_id", "bill_month"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("target_kind", REVIEW_TARGETS), name="target_kind"),
        CheckConstraint(_in("stage", REVIEW_STAGES), name="stage"),
        CheckConstraint(_in("decision", REVIEW_DECISIONS), name="decision"),
        CheckConstraint(
            "decision = 'pass' OR coalesce(comment, '') <> ''", name="reject_needs_comment"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    period_key: Mapped[str | None] = mapped_column(String(64))
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column()
    line_key: Mapped[str] = mapped_column(LINE_KEY, nullable=False)
    stage: Mapped[str] = mapped_column(String(8), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any]] = _json_dict()
    after: Mapped[dict[str, Any]] = _json_dict()
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SettlementMonthClose(_Actor, Base):
    """店铺 × 账单月 结账 / 解锁记录（只增不改；seq 递增，最后一条决定当前状态）。"""

    __tablename__ = "manual_settlement_month_close"
    __table_args__ = (
        UniqueConstraint("store_id", "bill_month", "seq", name="uq_manual_settlement_month_close"),
        CheckConstraint(_first_of_month("bill_month"), name="bill_month_first_day"),
        CheckConstraint(_in("action", MONTH_CLOSE_ACTIONS), name="action"),
        CheckConstraint(
            "action <> 'unlock' OR coalesce(reason, '') <> ''", name="unlock_needs_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[date] = mapped_column(Date, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    frozen_calc_version: Mapped[int | None] = mapped_column(Integer)
    totals: Mapped[dict[str, Any]] = _json_dict()
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# --------------------------------------------------------------------------- CFG


class SettlementSetting(_Timestamps, Base):
    """财务设置（§0.5 六项 + WFS 承运商清单），按生效月取值；值只在生产库配置。"""

    __tablename__ = "cfg_finance_settlement_settings"
    __table_args__ = (
        UniqueConstraint(
            "setting_key", "effective_month", name="uq_cfg_finance_settlement_setting"
        ),
        CheckConstraint(_first_of_month("effective_month"), name="effective_month_first_day"),
        CheckConstraint(_in("setting_key", SETTING_KEYS), name="setting_key"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    setting_key: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))


class OwnerTagRule(_Timestamps, Base):
    """按 Listing 标签指定负责人（标签名 → 负责人）；只存数据库，仓库里不出现标签名和人名。"""

    __tablename__ = "cfg_finance_owner_tag_rules"
    __table_args__ = (UniqueConstraint("tag_name", name="uq_cfg_finance_owner_tag_rule"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tag_name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))


SETTLEMENT_PROFIT_TABLES: tuple[str, ...] = (
    FinShippingList.__tablename__,
    FinShippingDetailItem.__tablename__,
    FinWmsOutboundOrder.__tablename__,
    ReviewAcceleratorSnapshot.__tablename__,
    SettlementOrderLine.__tablename__,
    SettlementStoreMonthItem.__tablename__,
    SettlementPostCloseDiff.__tablename__,
    SettlementProfitItemMonth.__tablename__,
    SettlementOrderReview.__tablename__,
    SettlementReconcileStorePeriod.__tablename__,
    SettlementNoOrderFlag.__tablename__,
    SettlementCostEntry.__tablename__,
    SettlementSemMonth.__tablename__,
    SettlementOrderAdjustment.__tablename__,
    SettlementReviewAction.__tablename__,
    SettlementMonthClose.__tablename__,
    SettlementSetting.__tablename__,
    OwnerTagRule.__tablename__,
)
