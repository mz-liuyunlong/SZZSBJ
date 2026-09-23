"""Add governed after-sales reason classification and responsibility dictionaries.

Revision ID: 20260923_0019_after_sales_reason_classification
Revises: 20260923_0018_merge_after_sales_pmc_heads
Create Date: 2026-09-23
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260923_0019_after_sales_reason_classification"
down_revision: str | None = "20260923_0018_merge_after_sales_pmc_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULE_VERSION = "walmart-v1"

RESPONSIBILITIES = [
    ("PRODUCT", "商品问题", "#FF4D4F", 10, "商品质量、结构、完整性等商品侧责任。"),
    ("LISTING", "Listing问题", "#FA8C16", 20, "页面描述、图片、尺寸或兼容性信息等 Listing 责任。"),
    ("FULFILLMENT", "仓库问题", "#722ED1", 30, "拣货、错发、漏发、发错门店等仓库履约责任。"),
    ("INVENTORY", "库存问题", "#EB2F96", 40, "缺货等库存供给责任。"),
    ("LOGISTICS", "物流问题", "#1677FF", 50, "运输丢失、延迟、无法投递、运输包装破损等物流责任。"),
    (
        "CUSTOMER",
        "客户原因",
        "#52C41A",
        60,
        "客户主动取消、不再需要、价格选择、取货超时等客户原因。",
    ),
    ("OPERATION", "运营问题", "#FAAD14", 70, "卖家主动退款等运营侧处理责任。"),
    ("PLATFORM_STORE", "平台/门店", "#13C2C2", 80, "Walmart 平台、门店、自提链路等责任。"),
    ("PENDING", "待判定", "#8C8C8C", 999, "现有数据不足以可靠定责，需要人工或后续证据。"),
]

REASONS = [
    ("CUSTOMER_NO_LONGER_WANTED", "不再需要", "CUSTOMER_CHOICE", "客户选择", "#52C41A", 10),
    ("NOT_AS_DESCRIBED", "与描述/图片不符", "LISTING", "Listing问题", "#FA8C16", 20),
    ("PRODUCT_DEFECTIVE", "商品故障/损坏", "PRODUCT_QUALITY", "商品质量", "#FF4D4F", 30),
    ("SETUP_OR_COMPATIBILITY", "安装困难/不兼容", "PRODUCT_EXPERIENCE", "商品体验", "#8C8C8C", 40),
    ("LOST_IN_TRANSIT", "运输途中丢失", "LOGISTICS", "物流问题", "#1677FF", 50),
    ("UNABLE_TO_DELIVER", "无法投递/退回", "LOGISTICS", "物流问题", "#1677FF", 60),
    ("LOST_AFTER_DELIVERY", "投递后丢失", "LOGISTICS", "物流问题", "#1677FF", 70),
    ("ITEM_ARRIVED_DAMAGED", "到货商品破损", "DAMAGE", "破损问题", "#8C8C8C", 80),
    ("WRONG_ITEM_RECEIVED", "收到错误商品", "FULFILLMENT", "仓库履约", "#722ED1", 90),
    ("MISSING_ITEMS_FROM_BOX", "箱内缺件", "FULFILLMENT", "仓库履约", "#722ED1", 100),
    ("BOUGHT_ELSEWHERE", "已在其他渠道购买", "CUSTOMER_CHOICE", "客户选择", "#52C41A", 110),
    (
        "MISSING_PARTS_INSTRUCTIONS",
        "缺少配件/说明书",
        "PRODUCT_COMPLETENESS",
        "商品完整性",
        "#FF4D4F",
        120,
    ),
    ("OUT_OF_STOCK", "缺货", "INVENTORY", "库存问题", "#EB2F96", 130),
    ("LOWER_PRICE", "找到更低价格", "CUSTOMER_CHOICE", "客户选择", "#52C41A", 140),
    (
        "STORE_CANCEL_POST_SHIPMENT",
        "发货后门店/自提取消",
        "PLATFORM_STORE",
        "平台/门店",
        "#13C2C2",
        150,
    ),
    ("SELLER_ISSUED_REFUND", "卖家主动退款", "OPERATION", "运营问题", "#FAAD14", 160),
    ("ARRIVED_LATE", "到货延迟", "LOGISTICS", "物流问题", "#1677FF", 170),
    ("WRONG_STORE", "发错门店", "FULFILLMENT", "仓库履约", "#722ED1", 180),
    ("AUTO_GENERIC_RETURN", "自动/通用退货", "PLATFORM_STORE", "平台/门店", "#13C2C2", 190),
    ("ITEM_AND_BOX_DAMAGED", "商品及运输箱破损", "LOGISTICS", "物流问题", "#1677FF", 200),
    ("SHIPPING_BOX_DAMAGED", "运输箱破损", "LOGISTICS", "物流问题", "#1677FF", 210),
    ("PICKUP_WINDOW_EXPIRED", "取货超时", "CUSTOMER", "客户原因", "#52C41A", 220),
    ("LOST_IN_STORE", "门店内丢失", "PLATFORM_STORE", "平台/门店", "#13C2C2", 230),
    ("CANCEL_ATTEMPT", "买家尝试取消", "CUSTOMER", "客户原因", "#52C41A", 240),
    ("SIZE_FIT", "尺寸不合适", "LISTING", "Listing问题", "#FA8C16", 250),
    ("UNCLASSIFIED", "未分类", "PENDING", "待判定", "#8C8C8C", 999),
]

EXACT_RULES = [
    ("NO_LONGER_WANTED", "No Longer Wanted", "CUSTOMER_NO_LONGER_WANTED", "CUSTOMER", "HIGH"),
    (
        "NOT_AS_DESCRIBED_PICTURED",
        "Not as described/pictured",
        "NOT_AS_DESCRIBED",
        "LISTING",
        "HIGH",
    ),
    ("DEFECTIVE", "Defective/Broken", "PRODUCT_DEFECTIVE", "PRODUCT", "HIGH"),
    (
        "DIFFICULT_TO_SETUP_NOT_COMPATIBLE",
        "Difficult to setup/not compatible",
        "SETUP_OR_COMPATIBILITY",
        "PENDING",
        "LOW",
    ),
    ("LOST_IN_TRANSIT", "Lost in Transit", "LOST_IN_TRANSIT", "LOGISTICS", "HIGH"),
    ("RETURN_TO_SENDER", "Unable to deliver", "UNABLE_TO_DELIVER", "LOGISTICS", "MEDIUM"),
    ("LOST_AFTER_DELIVERY", "Lost After Delivery", "LOST_AFTER_DELIVERY", "LOGISTICS", "MEDIUM"),
    ("DAMAGED", "Item arrived damaged", "ITEM_ARRIVED_DAMAGED", "PENDING", "LOW"),
    ("INCORRECT_ITEM", "Incorrect item received", "WRONG_ITEM_RECEIVED", "FULFILLMENT", "HIGH"),
    ("INCORRECT_ITEM", "Missing Items from Box", "MISSING_ITEMS_FROM_BOX", "FULFILLMENT", "HIGH"),
    ("BOUGHT_SOMEWHERE_ELSE", "Bought Somewhere Else", "BOUGHT_ELSEWHERE", "CUSTOMER", "HIGH"),
    (
        "DEFECTIVE",
        "Missing parts or instructions",
        "MISSING_PARTS_INSTRUCTIONS",
        "PRODUCT",
        "MEDIUM",
    ),
    ("OUT_OF_STOCK", "Out of Stock", "OUT_OF_STOCK", "INVENTORY", "HIGH"),
    ("LOWER_PRICE", "Lower Price", "LOWER_PRICE", "CUSTOMER", "HIGH"),
    (
        "OTHER",
        "S2S or PUT Cancellation post-Shipment",
        "STORE_CANCEL_POST_SHIPMENT",
        "PLATFORM_STORE",
        "MEDIUM",
    ),
    ("OTHER", "Seller Issued Refund", "SELLER_ISSUED_REFUND", "OPERATION", "MEDIUM"),
    ("ARRIVED_LATE", "Late to arrive", "ARRIVED_LATE", "LOGISTICS", "HIGH"),
    ("OTHER", "Shipped to Wrong Store", "WRONG_STORE", "FULFILLMENT", "MEDIUM"),
    ("OTHER", "Auto Return/ Generic return", "AUTO_GENERIC_RETURN", "PLATFORM_STORE", "MEDIUM"),
    ("DAMAGED", "Item and Shipping Box Damaged", "ITEM_AND_BOX_DAMAGED", "LOGISTICS", "HIGH"),
    ("SHIPPING_BOX_DAMAGED", "Shipping box damaged", "SHIPPING_BOX_DAMAGED", "LOGISTICS", "HIGH"),
    ("OTHER", "Shipping box damaged", "SHIPPING_BOX_DAMAGED", "LOGISTICS", "HIGH"),
    ("OTHER", "Pickup window expired", "PICKUP_WINDOW_EXPIRED", "CUSTOMER", "HIGH"),
    ("OTHER", "Lost in Store", "LOST_IN_STORE", "PLATFORM_STORE", "HIGH"),
    ("TRIED_TO_CANCEL", "Tried to Cancel", "CANCEL_ATTEMPT", "CUSTOMER", "HIGH"),
    ("OTHER", "Too small/short/tight", "SIZE_FIT", "LISTING", "MEDIUM"),
]

# Description-only rules are lower priority than exact code+description matches, but
# allow a known Walmart description to remain classified if the provider changes its raw code.
# Every duplicated description in the current sample maps to the same normalized result.
EXACT_DESCRIPTION_RULES = list(
    {
        (description, normalized, responsibility_code, confidence)
        for _, description, normalized, responsibility_code, confidence in EXACT_RULES
    }
)


KEYWORD_RULES = [
    (
        None,
        ["shipping", "box", "damaged"],
        [],
        [],
        "SHIPPING_BOX_DAMAGED",
        "LOGISTICS",
        "MEDIUM",
        700,
    ),
    (
        None,
        ["item", "shipping", "box", "damaged"],
        [],
        [],
        "ITEM_AND_BOX_DAMAGED",
        "LOGISTICS",
        "HIGH",
        710,
    ),
    (None, ["lost", "transit"], [], [], "LOST_IN_TRANSIT", "LOGISTICS", "HIGH", 720),
    (None, ["unable", "deliver"], [], [], "UNABLE_TO_DELIVER", "LOGISTICS", "MEDIUM", 730),
    (None, ["late"], ["arrive", "arrival"], [], "ARRIVED_LATE", "LOGISTICS", "MEDIUM", 740),
    (None, ["incorrect", "item"], [], [], "WRONG_ITEM_RECEIVED", "FULFILLMENT", "HIGH", 750),
    (
        None,
        ["missing"],
        ["item", "items"],
        ["parts", "instructions"],
        "MISSING_ITEMS_FROM_BOX",
        "FULFILLMENT",
        "MEDIUM",
        760,
    ),
    (
        None,
        ["missing"],
        ["parts", "instructions"],
        [],
        "MISSING_PARTS_INSTRUCTIONS",
        "PRODUCT",
        "MEDIUM",
        770,
    ),
    (None, ["not", "described"], [], [], "NOT_AS_DESCRIBED", "LISTING", "MEDIUM", 780),
    (None, [], ["defective", "broken"], [], "PRODUCT_DEFECTIVE", "PRODUCT", "MEDIUM", 790),
    (None, ["out", "stock"], [], [], "OUT_OF_STOCK", "INVENTORY", "HIGH", 800),
    (None, ["lower", "price"], [], [], "LOWER_PRICE", "CUSTOMER", "HIGH", 810),
    (None, ["pickup", "expired"], [], [], "PICKUP_WINDOW_EXPIRED", "CUSTOMER", "MEDIUM", 820),
    (None, ["wrong", "store"], [], [], "WRONG_STORE", "FULFILLMENT", "MEDIUM", 830),
    (None, ["seller", "refund"], [], [], "SELLER_ISSUED_REFUND", "OPERATION", "MEDIUM", 840),
    (None, [], ["too small", "too short", "too tight"], [], "SIZE_FIT", "LISTING", "MEDIUM", 850),
]

CODE_DEFAULTS = [
    ("NO_LONGER_WANTED", "CUSTOMER_NO_LONGER_WANTED", "CUSTOMER", "HIGH"),
    ("NOT_AS_DESCRIBED_PICTURED", "NOT_AS_DESCRIBED", "LISTING", "HIGH"),
    ("LOST_IN_TRANSIT", "LOST_IN_TRANSIT", "LOGISTICS", "HIGH"),
    ("RETURN_TO_SENDER", "UNABLE_TO_DELIVER", "LOGISTICS", "MEDIUM"),
    ("LOST_AFTER_DELIVERY", "LOST_AFTER_DELIVERY", "LOGISTICS", "MEDIUM"),
    ("BOUGHT_SOMEWHERE_ELSE", "BOUGHT_ELSEWHERE", "CUSTOMER", "HIGH"),
    ("OUT_OF_STOCK", "OUT_OF_STOCK", "INVENTORY", "HIGH"),
    ("LOWER_PRICE", "LOWER_PRICE", "CUSTOMER", "HIGH"),
    ("ARRIVED_LATE", "ARRIVED_LATE", "LOGISTICS", "HIGH"),
    ("SHIPPING_BOX_DAMAGED", "SHIPPING_BOX_DAMAGED", "LOGISTICS", "HIGH"),
    ("TRIED_TO_CANCEL", "CANCEL_ATTEMPT", "CUSTOMER", "HIGH"),
]


def _rule_id(match_type: str, code: str | None, match_value: str | None, reason: str) -> str:
    key = f"{RULE_VERSION}|{match_type}|{code or ''}|{match_value or ''}|{reason}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"szzsbj:after-sales:{key}"))


def upgrade() -> None:
    responsibility = op.create_table(
        "after_sales_responsibility_dict",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name_cn", sa.String(128), nullable=False),
        sa.Column("tag_color", sa.String(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        comment="售后责任归属字典；前端标签颜色由 tag_color 驱动。",
    )

    reason = op.create_table(
        "after_sales_reason_dict",
        sa.Column("reason_code", sa.String(64), primary_key=True),
        sa.Column("reason_name_cn", sa.String(128), nullable=False),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("category_name_cn", sa.String(128), nullable=False),
        sa.Column("tag_color", sa.String(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        comment="售后标准原因字典；保留 Walmart 原始原因，同时提供标准中文原因与标签颜色。",
    )

    rules = op.create_table(
        "after_sales_reason_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform_code", sa.String(32), nullable=False, server_default="walmart"),
        sa.Column("raw_reason_code", sa.String(128), nullable=True),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("match_value", sa.Text(), nullable=True),
        sa.Column(
            "keywords_all",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "keywords_any",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "keywords_exclude",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "normalized_reason_code",
            sa.String(64),
            sa.ForeignKey("after_sales_reason_dict.reason_code"),
            nullable=False,
        ),
        sa.Column(
            "responsibility_code",
            sa.String(64),
            sa.ForeignKey("after_sales_responsibility_dict.code"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "match_type in ('EXACT_PAIR','EXACT_DESCRIPTION','KEYWORD','CODE_DEFAULT')",
            name="ck_after_sales_reason_rules_match_type",
        ),
        sa.CheckConstraint(
            "confidence in ('HIGH','MEDIUM','LOW')",
            name="ck_after_sales_reason_rules_confidence",
        ),
        comment="Walmart 原因标准化与责任归属规则；精确规则优先于关键词和 Code 默认规则。",
    )

    op.create_index(
        "ix_after_sales_reason_rules_lookup",
        "after_sales_reason_rules",
        ["platform_code", "enabled", "match_type", "priority"],
    )
    op.create_index(
        "ix_after_sales_reason_rules_raw_code",
        "after_sales_reason_rules",
        ["platform_code", "raw_reason_code"],
    )

    op.add_column(
        "after_sales_refund_items",
        sa.Column("normalized_reason_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("reason_category_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("responsibility_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("classification_source", sa.String(32), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("classification_confidence", sa.String(16), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("classification_rule_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("classification_rule_version", sa.String(32), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("manual_reason_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "after_sales_refund_items",
        sa.Column("manual_responsibility_code", sa.String(64), nullable=True),
    )

    op.create_foreign_key(
        "fk_after_sales_refund_items_reason_code",
        "after_sales_refund_items",
        "after_sales_reason_dict",
        ["normalized_reason_code"],
        ["reason_code"],
    )
    op.create_foreign_key(
        "fk_after_sales_refund_items_responsibility_code",
        "after_sales_refund_items",
        "after_sales_responsibility_dict",
        ["responsibility_code"],
        ["code"],
    )
    op.create_foreign_key(
        "fk_after_sales_refund_items_classification_rule",
        "after_sales_refund_items",
        "after_sales_reason_rules",
        ["classification_rule_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_after_sales_refund_items_manual_reason",
        "after_sales_refund_items",
        "after_sales_reason_dict",
        ["manual_reason_code"],
        ["reason_code"],
    )
    op.create_foreign_key(
        "fk_after_sales_refund_items_manual_responsibility",
        "after_sales_refund_items",
        "after_sales_responsibility_dict",
        ["manual_responsibility_code"],
        ["code"],
    )

    op.execute(
        """
        create index ix_after_sales_refund_items_final_reason
        on after_sales_refund_items (
            source_account_ref,
            (coalesce(manual_reason_code, normalized_reason_code, 'UNCLASSIFIED')),
            return_order_at
        )
        """
    )
    op.execute(
        """
        create index ix_after_sales_refund_items_final_responsibility
        on after_sales_refund_items (
            source_account_ref,
            (coalesce(manual_responsibility_code, responsibility_code, 'PENDING')),
            return_order_at
        )
        """
    )

    op.bulk_insert(
        responsibility,
        [
            {
                "code": code,
                "name_cn": name,
                "tag_color": color,
                "sort_order": sort_order,
                "enabled": True,
                "description": description,
            }
            for code, name, color, sort_order, description in RESPONSIBILITIES
        ],
    )

    op.bulk_insert(
        reason,
        [
            {
                "reason_code": code,
                "reason_name_cn": name,
                "category_code": category_code,
                "category_name_cn": category_name,
                "tag_color": color,
                "sort_order": sort_order,
                "enabled": True,
                "description": None,
            }
            for code, name, category_code, category_name, color, sort_order in REASONS
        ],
    )

    rule_rows: list[dict[str, object]] = []
    for priority, (
        raw_code,
        description,
        normalized,
        responsibility_code,
        confidence,
    ) in enumerate(EXACT_RULES, start=1000):
        rule_rows.append(
            {
                "id": _rule_id("EXACT_PAIR", raw_code.upper(), description, normalized),
                "platform_code": "walmart",
                "raw_reason_code": raw_code.upper(),
                "match_type": "EXACT_PAIR",
                "match_value": description,
                "keywords_all": [],
                "keywords_any": [],
                "keywords_exclude": [],
                "normalized_reason_code": normalized,
                "responsibility_code": responsibility_code,
                "priority": priority,
                "confidence": confidence,
                "rule_version": RULE_VERSION,
                "enabled": True,
                "remark": "基于当前已确认 Walmart 售后原因样本的精确映射。",
            }
        )

    for priority, (description, normalized, responsibility_code, confidence) in enumerate(
        sorted(EXACT_DESCRIPTION_RULES),
        start=900,
    ):
        rule_rows.append(
            {
                "id": _rule_id("EXACT_DESCRIPTION", None, description, normalized),
                "platform_code": "walmart",
                "raw_reason_code": None,
                "match_type": "EXACT_DESCRIPTION",
                "match_value": description,
                "keywords_all": [],
                "keywords_any": [],
                "keywords_exclude": [],
                "normalized_reason_code": normalized,
                "responsibility_code": responsibility_code,
                "priority": priority,
                "confidence": confidence,
                "rule_version": RULE_VERSION,
                "enabled": True,
                "remark": "已知 Walmart 描述精确映射；低于 Code+Description 精确规则。",
            }
        )

    for (
        raw_code,
        all_words,
        any_words,
        excluded_words,
        normalized,
        responsibility_code,
        confidence,
        priority,
    ) in KEYWORD_RULES:
        rule_rows.append(
            {
                "id": _rule_id("KEYWORD", raw_code, "|".join(all_words + any_words), normalized),
                "platform_code": "walmart",
                "raw_reason_code": raw_code,
                "match_type": "KEYWORD",
                "match_value": None,
                "keywords_all": all_words,
                "keywords_any": any_words,
                "keywords_exclude": excluded_words,
                "normalized_reason_code": normalized,
                "responsibility_code": responsibility_code,
                "priority": priority,
                "confidence": confidence,
                "rule_version": RULE_VERSION,
                "enabled": True,
                "remark": "新描述 fallback；低于精确匹配优先级。",
            }
        )

    for offset, (raw_code, normalized, responsibility_code, confidence) in enumerate(CODE_DEFAULTS):
        priority = 300 - offset
        rule_rows.append(
            {
                "id": _rule_id("CODE_DEFAULT", raw_code, None, normalized),
                "platform_code": "walmart",
                "raw_reason_code": raw_code,
                "match_type": "CODE_DEFAULT",
                "match_value": None,
                "keywords_all": [],
                "keywords_any": [],
                "keywords_exclude": [],
                "normalized_reason_code": normalized,
                "responsibility_code": responsibility_code,
                "priority": priority,
                "confidence": confidence,
                "rule_version": RULE_VERSION,
                "enabled": True,
                "remark": "仅用于没有精确描述/关键词命中时的 Code 默认规则。",
            }
        )

    op.bulk_insert(rules, rule_rows)

    op.execute(
        """
        comment on column after_sales_refund_items.return_reason_code is
        'Walmart 原始原因代码：items[].returnReason；不得被标准化逻辑覆盖。'
        """
    )
    op.execute(
        """
        comment on column after_sales_refund_items.return_description is
        'Walmart 原始售后原因描述：items[].returnDescription；不得被标准化逻辑覆盖。'
        """
    )
    op.execute(
        """
        comment on column after_sales_refund_items.refund_loss_effective is
        '是否计入退款成本损失：NOT_REFUNDED/CANCELLED 已在入库前剔除，其余退款状态均为 true。'
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_after_sales_refund_items_final_responsibility")
    op.execute("drop index if exists ix_after_sales_refund_items_final_reason")

    op.drop_constraint(
        "fk_after_sales_refund_items_manual_responsibility",
        "after_sales_refund_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_after_sales_refund_items_manual_reason",
        "after_sales_refund_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_after_sales_refund_items_classification_rule",
        "after_sales_refund_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_after_sales_refund_items_responsibility_code",
        "after_sales_refund_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_after_sales_refund_items_reason_code",
        "after_sales_refund_items",
        type_="foreignkey",
    )

    for column in (
        "manual_responsibility_code",
        "manual_reason_code",
        "classified_at",
        "classification_rule_version",
        "classification_rule_id",
        "classification_confidence",
        "classification_source",
        "responsibility_code",
        "reason_category_code",
        "normalized_reason_code",
    ):
        op.drop_column("after_sales_refund_items", column)

    op.drop_index("ix_after_sales_reason_rules_raw_code", table_name="after_sales_reason_rules")
    op.drop_index("ix_after_sales_reason_rules_lookup", table_name="after_sales_reason_rules")
    op.drop_table("after_sales_reason_rules")
    op.drop_table("after_sales_reason_dict")
    op.drop_table("after_sales_responsibility_dict")
