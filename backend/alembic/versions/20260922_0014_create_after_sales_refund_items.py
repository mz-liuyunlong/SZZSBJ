"""Create after sales refund item fact table.

Revision ID: 20260922_0014_after_sales_refund_items
Revises: 20260921_0013_business_rule_operation_logs
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0014_after_sales_refund_items"
down_revision: str | None = "20260921_0013_business_rule_operation_logs"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "after_sales_refund_items",
        sa.Column(
            "id",
            sa.String(length=64),
            primary_key=True,
            comment="稳定行ID：由 source_account_ref + return_order_id + item_index 等生成哈希。",
        ),
        sa.Column(
            "source_account_ref",
            sa.String(length=64),
            nullable=False,
            server_default="primary",
            comment="数据源账号范围，例如 primary。",
        ),
        sa.Column(
            "platform_code",
            sa.String(length=32),
            nullable=False,
            server_default="walmart",
            comment="平台编码，当前为 walmart。",
        ),
        sa.Column(
            "source_request_id",
            sa.String(length=128),
            nullable=True,
            comment="接口返回 request_id，用于追踪本次接口响应。",
        ),
        sa.Column(
            "return_order_id",
            sa.String(length=128),
            nullable=False,
            comment="售后单号 / RMA 编号：body.data.list[].returnOrderId。",
        ),
        sa.Column(
            "item_index",
            sa.Integer(),
            nullable=False,
            comment="售后单 items 数组下标，用于区分同一 return_order_id 下多条商品明细。",
        ),
        sa.Column(
            "customer_order_id",
            sa.String(length=128),
            nullable=True,
            comment="买家订单号：body.data.list[].customerOrderId。",
        ),
        sa.Column(
            "purchase_order_id",
            sa.String(length=128),
            nullable=True,
            comment="平台订单号：body.data.list[].items[].purchaseOrderId。",
        ),
        sa.Column(
            "store_id",
            sa.String(length=64),
            nullable=False,
            comment="店铺ID，统一字符串存储，避免大数字精度问题。",
        ),
        sa.Column(
            "raw_store_name",
            sa.String(length=255),
            nullable=True,
            comment="接口返回的原始店铺名，仅兜底和追溯使用。",
        ),
        sa.Column(
            "store_name",
            sa.String(length=255),
            nullable=True,
            comment="标准店铺名：优先从 dim_lingxing_stores 匹配，失败时用 raw_store_name 兜底。",
        ),
        sa.Column(
            "store_match_status",
            sa.String(length=32),
            nullable=False,
            server_default="raw_only",
            comment="店铺匹配状态：matched/raw_only/unmatched。",
        ),
        sa.Column(
            "site_code",
            sa.String(length=64),
            nullable=True,
            comment="接口返回站点编码，例如 10008-US；页面不直接依赖。",
        ),
        sa.Column(
            "return_type",
            sa.String(length=64),
            nullable=True,
            comment="售后类型：body.data.list[].returnType，例如 REFUND。",
        ),
        sa.Column(
            "return_order_at",
            sa.DateTime(timezone=False),
            nullable=True,
            comment="售后申请时间：body.data.list[].returnOrderDate。",
        ),
        sa.Column(
            "purchase_time_at",
            sa.DateTime(timezone=False),
            nullable=True,
            comment="原订单下单时间：body.data.list[].purchaseTimeLocale。",
        ),
        sa.Column(
            "local_sku",
            sa.String(length=128),
            nullable=True,
            comment="接口 localSku，用于匹配产品管理表获取名称和成本。",
        ),
        sa.Column(
            "msku",
            sa.String(length=128),
            nullable=True,
            comment="接口 msku，用于 store_id + msku 匹配 Listing 获取 item_id 和图片。",
        ),
        sa.Column(
            "return_qty",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
            comment="退款数量，由 quantityDisplay 转为数值。",
        ),
        sa.Column(
            "quantity_display_raw",
            sa.String(length=64),
            nullable=True,
            comment="接口原始 quantityDisplay。",
        ),
        sa.Column(
            "return_reason_code",
            sa.String(length=128),
            nullable=True,
            comment="退款原因代码：items[].returnReason，用于原因分析。",
        ),
        sa.Column(
            "return_description",
            sa.Text(),
            nullable=True,
            comment="退款原因描述：items[].returnDescription。",
        ),
        sa.Column(
            "status_time",
            sa.DateTime(timezone=False),
            nullable=True,
            comment="接口 items[].statusTime，当前状态时间。",
        ),
        sa.Column(
            "current_refund_status",
            sa.String(length=64),
            nullable=True,
            comment="接口 currentRefundStatus，原始退款状态，保留用于追溯。",
        ),
        sa.Column(
            "refund_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否已完成退款：currentRefundStatus == REFUND_COMPLETED。",
        ),
        sa.Column(
            "refund_effective",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否计入退款损失；当前等同 refund_completed。",
        ),
        sa.Column(
            "refund_effective_date",
            sa.Date(),
            nullable=True,
            comment="有效退款日期；当前取 status_time 日期，缺失时兜底 return_order_at 日期。",
        ),
        sa.Column(
            "item_id",
            sa.String(length=128),
            nullable=True,
            comment="商品ID：通过 store_id + msku 匹配 Listing 得到。",
        ),
        sa.Column(
            "listing_image_url",
            sa.Text(),
            nullable=True,
            comment="Listing 图片：通过 store_id + msku 匹配 Listing 得到。",
        ),
        sa.Column(
            "listing_match_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="Listing 匹配状态：matched/unmatched/conflict/pending。",
        ),
        sa.Column(
            "product_name",
            sa.String(length=512),
            nullable=True,
            comment="产品名称：通过 local_sku 匹配产品管理表得到。",
        ),
        sa.Column(
            "product_match_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="产品匹配状态：matched/unmatched/conflict/pending。",
        ),
        sa.Column(
            "purchase_cost",
            sa.Numeric(18, 4),
            nullable=True,
            comment="采购成本快照。",
        ),
        sa.Column(
            "first_leg_cost",
            sa.Numeric(18, 4),
            nullable=True,
            comment="头程成本快照。",
        ),
        sa.Column(
            "wfs_fee",
            sa.Numeric(18, 4),
            nullable=True,
            comment="WFS费用快照。",
        ),
        sa.Column(
            "daily_storage_fee",
            sa.Numeric(18, 4),
            nullable=True,
            comment="单日仓储费快照。",
        ),
        sa.Column(
            "unit_total_cost",
            sa.Numeric(18, 4),
            nullable=True,
            comment="单件总成本：采购 + 头程 + WFS费用 + 单日仓储费。",
        ),
        sa.Column(
            "cost_match_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="成本匹配状态：matched/incomplete/unmatched/pending。",
        ),
        sa.Column(
            "refund_loss_amount",
            sa.Numeric(18, 4),
            nullable=True,
            comment="退款损失：仅已完成退款时，return_qty × unit_total_cost。",
        ),
        sa.Column(
            "source_item_hash",
            sa.String(length=64),
            nullable=False,
            comment="原始商品明细哈希，用于检测接口行变化。",
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="本行同步入库时间。",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="创建时间。",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="更新时间。",
        ),
        sa.CheckConstraint(
            "return_qty >= 0", name="ck_after_sales_refund_items_return_qty_non_negative"
        ),
        sa.UniqueConstraint(
            "source_account_ref",
            "return_order_id",
            "item_index",
            name="ux_after_sales_refund_items_return_item",
        ),
        comment=(
            "售后退款商品明细表：一条 returnOrder items 明细一行；"
            "Daily Sales 后续从本表 refund_effective=true 聚合退款损失。"
        ),
    )

    op.create_index(
        "ix_after_sales_refund_items_effective_date",
        "after_sales_refund_items",
        ["source_account_ref", "refund_effective_date"],
    )
    op.create_index(
        "ix_after_sales_refund_items_store_sku",
        "after_sales_refund_items",
        ["store_id", "local_sku"],
    )
    op.create_index(
        "ix_after_sales_refund_items_store_msku",
        "after_sales_refund_items",
        ["store_id", "msku"],
    )
    op.create_index(
        "ix_after_sales_refund_items_purchase_order",
        "after_sales_refund_items",
        ["purchase_order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_after_sales_refund_items_purchase_order", table_name="after_sales_refund_items"
    )
    op.drop_index("ix_after_sales_refund_items_store_msku", table_name="after_sales_refund_items")
    op.drop_index("ix_after_sales_refund_items_store_sku", table_name="after_sales_refund_items")
    op.drop_index(
        "ix_after_sales_refund_items_effective_date", table_name="after_sales_refund_items"
    )
    op.drop_table("after_sales_refund_items")
