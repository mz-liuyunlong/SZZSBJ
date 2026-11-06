"""Lingxing monthly FX rate table: the single exchange-rate source.

Revision ID: 20261105_0079_lingxing_fx_rate
Revises: 20261105_0078_finance_journal_edit_split
"""

import sqlalchemy as sa

from alembic import op

revision = "20261105_0079_lingxing_fx_rate"
down_revision = "20261105_0078_finance_journal_edit_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_lingxing_fx_rate",
        sa.Column("rate_month", sa.String(7), primary_key=True),
        sa.Column("currency_code", sa.String(8), primary_key=True),
        sa.Column("currency_name", sa.String(64)),
        sa.Column("rate_org", sa.Numeric(18, 10)),
        sa.Column("my_rate", sa.Numeric(18, 10)),
        sa.Column("lx_update_time", sa.String(32)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "raw_request_ref_id",
            sa.Uuid(),
            sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("rate_month ~ '^[0-9]{4}-[0-9]{2}$'", name="rate_month_format"),
        sa.CheckConstraint("rate_org IS NULL OR rate_org > 0", name="rate_org_positive"),
        sa.CheckConstraint("my_rate IS NULL OR my_rate > 0", name="my_rate_positive"),
        sa.CheckConstraint("source IN ('sync', 'seed')", name="source"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_rows = bind.execute(sa.text("select 1 from fact_lingxing_fx_rate limit 1")).first()
    if has_rows is not None:
        raise RuntimeError("fact_lingxing_fx_rate has data; refusing to drop it")
    op.drop_table("fact_lingxing_fx_rate")
