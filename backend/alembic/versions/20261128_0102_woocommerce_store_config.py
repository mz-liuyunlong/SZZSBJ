"""Add encrypted WooCommerce store connection configuration."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261128_0102_woocommerce_store_config"
down_revision: str | Sequence[str] | None = "20261127_0101_finance_order_review_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sys_woocommerce_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("store_url", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consumer_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("consumer_secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_code", sa.String(80), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 2 AND 100",
            name="ck_sys_woocommerce_stores_name",
        ),
        sa.CheckConstraint("store_url LIKE 'https://%'", name="ck_sys_woocommerce_stores_https"),
        sa.UniqueConstraint("store_url", name="uq_sys_woocommerce_stores_store_url"),
    )
    op.create_index(
        "ix_sys_woocommerce_stores_enabled_updated",
        "sys_woocommerce_stores",
        ["enabled", "updated_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_rows = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM sys_woocommerce_stores)")
    ).scalar_one()
    if has_rows:
        raise RuntimeError(
            "Refusing to drop sys_woocommerce_stores while encrypted store credentials exist"
        )
    op.drop_index(
        "ix_sys_woocommerce_stores_enabled_updated",
        table_name="sys_woocommerce_stores",
    )
    op.drop_table("sys_woocommerce_stores")
