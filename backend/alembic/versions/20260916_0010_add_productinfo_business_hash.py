"""Add nullable deterministic ProductInfo business hashes.

Revision ID: 20260916_0010
Revises: 20260915_0009
Create Date: 2026-09-16

Historical rows remain NULL. This migration does not backfill data and does not
touch external services.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0010"
down_revision: str | Sequence[str] | None = "20260915_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dwd_lingxing_sku_product_info_snapshots",
        sa.Column("business_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_dwd_lingxing_sku_product_info_snapshots_business_hash_sha256",
        "dwd_lingxing_sku_product_info_snapshots",
        "business_hash IS NULL OR char_length(business_hash) = 64",
    )

    op.add_column(
        "dwd_lingxing_sku_product_info_current",
        sa.Column("business_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_dwd_lingxing_sku_product_info_current_business_hash_sha256",
        "dwd_lingxing_sku_product_info_current",
        "business_hash IS NULL OR char_length(business_hash) = 64",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_dwd_lingxing_sku_product_info_current_business_hash_sha256",
        "dwd_lingxing_sku_product_info_current",
        type_="check",
    )
    op.drop_column("dwd_lingxing_sku_product_info_current", "business_hash")

    op.drop_constraint(
        "ck_dwd_lingxing_sku_product_info_snapshots_business_hash_sha256",
        "dwd_lingxing_sku_product_info_snapshots",
        type_="check",
    )
    op.drop_column("dwd_lingxing_sku_product_info_snapshots", "business_hash")
