"""Add the Lingxing L2 RAW evidence table.

Revision ID: 20260910_0002
Revises: 20260910_0001
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_0002"
down_revision: str | Sequence[str] | None = "20260910_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_lingxing_api",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("api_path", sa.Text(), nullable=False),
        sa.Column("request_method", sa.String(length=10), nullable=False),
        sa.Column("request_params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_body_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("is_success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("data_date", sa.Date(), nullable=True),
        sa.Column("pulled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Text(), nullable=True),
        sa.Column("store_name", sa.Text(), nullable=True),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("extra_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_system = 'lingxing'",
            name=op.f("ck_raw_lingxing_api_source_system"),
        ),
        sa.CheckConstraint(
            "request_method = 'POST'",
            name=op.f("ck_raw_lingxing_api_request_method"),
        ),
        sa.CheckConstraint(
            "api_path IN ("
            "'/basicOpen/multiplatform/walmart/list', "
            "'/basicOpen/platformStatisticsV2/saleStat/pageList', "
            "'/erp/sc/routing/data/local_inventory/batchGetProductInfo', "
            "'/pb/mp/shop/v2/getSellerList', "
            "'/basicOpen/multiplatform/profit/report/order'"
            ")",
            name=op.f("ck_raw_lingxing_api_api_path"),
        ),
        sa.CheckConstraint("attempt_no >= 1", name=op.f("ck_raw_lingxing_api_attempt_no")),
        sa.CheckConstraint(
            "page_no IS NULL OR page_no >= 1",
            name=op.f("ck_raw_lingxing_api_page_no"),
        ),
        sa.CheckConstraint(
            "page_size IS NULL OR page_size BETWEEN 1 AND 3",
            name=op.f("ck_raw_lingxing_api_page_size"),
        ),
        sa.CheckConstraint(
            "char_length(raw_hash) = 64",
            name=op.f("ck_raw_lingxing_api_raw_hash"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_lingxing_api")),
    )
    op.create_index(
        "ix_raw_lingxing_api_raw_hash",
        "raw_lingxing_api",
        ["raw_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("raw_lingxing_api")
