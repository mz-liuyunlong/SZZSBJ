"""extend store commission rule scope

Revision ID: 20260921_0012_extend_store_commission_rule_scope
Revises: 20260921_0011_store_commission_rules
Create Date: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0012_extend_store_commission_rule_scope"
down_revision: str | Sequence[str] | None = "20260921_0011_store_commission_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ref_store_commission_rule_versions",
        sa.Column("rule_scope", sa.Text(), nullable=False, server_default="store"),
    )
    op.add_column(
        "ref_store_commission_rule_versions",
        sa.Column("item_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "ref_store_commission_rule_versions",
        sa.Column("price_min_amount", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "ref_store_commission_rule_versions",
        sa.Column("price_max_amount", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "ref_store_commission_rule_versions",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )

    op.execute(
        """
        update ref_store_commission_rule_versions
        set rule_scope='store', priority=100
        where rule_scope is null or trim(rule_scope)=''
        """
    )

    op.create_check_constraint(
        "ck_ref_store_commission_rule_versions_rule_scope",
        "ref_store_commission_rule_versions",
        "rule_scope in ('store','item','price_range')",
    )
    op.create_check_constraint(
        "ck_ref_store_commission_rule_versions_item_scope_item_id",
        "ref_store_commission_rule_versions",
        "rule_scope <> 'item' or (item_id is not null and trim(item_id) <> '')",
    )
    op.create_check_constraint(
        "ck_ref_store_commission_rule_versions_price_range_has_bound",
        "ref_store_commission_rule_versions",
        (
            "rule_scope <> 'price_range' "
            "or price_min_amount is not null "
            "or price_max_amount is not null"
        ),
    )
    op.create_check_constraint(
        "ck_ref_store_commission_rule_versions_price_range_order",
        "ref_store_commission_rule_versions",
        (
            "price_min_amount is null "
            "or price_max_amount is null "
            "or price_min_amount < price_max_amount"
        ),
    )

    op.create_index(
        "ix_ref_store_commission_rule_scope_active",
        "ref_store_commission_rule_versions",
        ["source_account_ref", "platform_code", "store_id", "rule_scope", "is_active"],
    )
    op.create_index(
        "ix_ref_store_commission_rule_item_active",
        "ref_store_commission_rule_versions",
        ["source_account_ref", "platform_code", "store_id", "item_id", "is_active"],
    )
    op.create_index(
        "ix_ref_store_commission_rule_price_active",
        "ref_store_commission_rule_versions",
        [
            "source_account_ref",
            "platform_code",
            "store_id",
            "price_min_amount",
            "price_max_amount",
            "is_active",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ref_store_commission_rule_price_active",
        table_name="ref_store_commission_rule_versions",
    )
    op.drop_index(
        "ix_ref_store_commission_rule_item_active",
        table_name="ref_store_commission_rule_versions",
    )
    op.drop_index(
        "ix_ref_store_commission_rule_scope_active",
        table_name="ref_store_commission_rule_versions",
    )

    op.drop_constraint(
        "ck_ref_store_commission_rule_versions_price_range_order",
        "ref_store_commission_rule_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_ref_store_commission_rule_versions_price_range_has_bound",
        "ref_store_commission_rule_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_ref_store_commission_rule_versions_item_scope_item_id",
        "ref_store_commission_rule_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_ref_store_commission_rule_versions_rule_scope",
        "ref_store_commission_rule_versions",
        type_="check",
    )

    op.drop_column("ref_store_commission_rule_versions", "priority")
    op.drop_column("ref_store_commission_rule_versions", "price_max_amount")
    op.drop_column("ref_store_commission_rule_versions", "price_min_amount")
    op.drop_column("ref_store_commission_rule_versions", "item_id")
    op.drop_column("ref_store_commission_rule_versions", "rule_scope")
