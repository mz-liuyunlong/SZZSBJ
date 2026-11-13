"""Finance: WFS fee report sync (PR 2) — jobs that ask Walmart for SETTLEMENT / WFS_STORAGE_FEE
reports per store and bill period, follow them until downloaded and imported into
fact_walmart_wfs_fee_lines; plus the inbound shipment items (shipped / received units per
shipment and item) collected by the Walmart remote collection, used to split inbound
transportation fees by shipped units.

Both tables start empty. No permission changes (action:finance:wfs-fees:sync was added in 0089).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261113_0090_finance_wfs_fee_reports"
down_revision: str | Sequence[str] | None = "20261113_0089_finance_wfs_fees"
branch_labels = None
depends_on = None

JOBS = "ops_walmart_wfs_report_jobs"
ITEMS = "fact_walmart_wfs_inbound_items"


def _ts(name: str, nullable: bool = False) -> sa.Column:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True))
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        JOBS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(16), nullable=False),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),  # schedule / manual
        sa.Column("requested_by", sa.String(255), nullable=False),
        # queued → submitted → imported / empty；failed / pii_blocked 结束
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(80)),
        sa.Column("submit_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("polls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remote_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "file_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_run_id", sa.Uuid()),
        _ts("next_action_at"),
        _ts("submitted_at", nullable=True),
        _ts("finished_at", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "report_type IN ('SETTLEMENT','WFS_STORAGE_FEE')", name="report_type_whitelist"
        ),
        sa.CheckConstraint("origin IN ('schedule','manual')", name="origin"),
        sa.CheckConstraint(
            "status IN ('queued','submitted','imported','empty','failed','pii_blocked')",
            name="status",
        ),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        sa.CheckConstraint("period_end >= period_start", name="period_order"),
    )
    # 同一店同一类型同一期，进行中的只能有一条（定时和手动不会重复下单）
    op.create_index(
        "uq_ops_walmart_wfs_report_jobs_active",
        JOBS,
        ["source_account_ref", "store_id", "report_type", "period_start", "period_end"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','submitted')"),
    )
    op.create_index("ix_ops_walmart_wfs_report_jobs_due", JOBS, ["status", "next_action_at"])
    op.create_index("ix_ops_walmart_wfs_report_jobs_store", JOBS, ["store_id", "created_at"])

    op.create_table(
        ITEMS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("shipment_id", sa.String(64), nullable=False),
        sa.Column("gtin", sa.String(32), nullable=False, server_default=""),
        sa.Column("sku", sa.Text(), nullable=False, server_default=""),
        sa.Column("item_qty", sa.Numeric(18, 4)),
        sa.Column("received_qty", sa.Numeric(18, 4)),
        sa.Column("source_run_id", sa.String(80), nullable=False),
        _ts("observed_at"),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "shipment_id",
            "gtin",
            "sku",
            name="uq_wfs_inbound_item",
        ),
    )
    op.create_index(
        "ix_fact_walmart_wfs_inbound_items_shipment", ITEMS, ["store_id", "shipment_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (JOBS, ITEMS):
        if bind.execute(sa.text(f"select 1 from {table} limit 1")).first() is not None:
            raise RuntimeError(f"{table} has data; refusing to drop it")
    op.drop_index("ix_fact_walmart_wfs_inbound_items_shipment", table_name=ITEMS)
    op.drop_table(ITEMS)
    op.drop_index("ix_ops_walmart_wfs_report_jobs_store", table_name=JOBS)
    op.drop_index("ix_ops_walmart_wfs_report_jobs_due", table_name=JOBS)
    op.drop_index("uq_ops_walmart_wfs_report_jobs_active", table_name=JOBS)
    op.drop_table(JOBS)
