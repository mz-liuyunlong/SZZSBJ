"""Finance: Walmart bill lines (Lingxing statement/list) and per-store, per-bill periods.

Also registers the action permission for the "手动同步" button on 回款对账.
Chained after main's 0083 (finance_sem_unallocated_lines). PR #326's 0083_rbac_nav is
also based on 0082: whichever merges second re-points its down_revision and updates
the head assertion in tests/db/test_alembic_scaffold.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261108_0085_finance_walmart_bills"
down_revision: str | Sequence[str] | None = "20261109_0083_finance_sem_unallocated_lines"
branch_labels = None
depends_on = None

LINES = "ods_lingxing_walmart_bill_lines"
PERIODS = "mart_walmart_bill_periods"
PAGE_KEY = "page:finance:settlement-reconciliation:view"
SYNC_KEY = "action:finance:settlement-reconciliation:sync"


def upgrade() -> None:
    op.create_table(
        LINES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("line_key", sa.String(64), nullable=False),
        sa.Column("lx_line_id", sa.String(32), nullable=False),
        sa.Column("report_key", sa.String(64), nullable=False),
        sa.Column("report_id", sa.String(32)),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("period_start_date", sa.Date()),
        sa.Column("period_end_date", sa.Date()),
        sa.Column("posted_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("transaction_key", sa.String(128)),
        sa.Column("transaction_type", sa.String(128)),
        sa.Column("transaction_description", sa.Text()),
        sa.Column("transaction_reason_description", sa.Text()),
        sa.Column("amount_type", sa.String(128)),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("total_payable", sa.Numeric(18, 4)),
        sa.Column("ship_qty", sa.Integer()),
        sa.Column("customer_order_no", sa.String(64)),
        sa.Column("customer_order_line_no", sa.String(32)),
        sa.Column("purchase_order_no", sa.String(64)),
        sa.Column("purchase_order_line_no", sa.String(32)),
        sa.Column("partner_item_id", sa.String(64)),
        sa.Column("partner_gtin", sa.String(32)),
        sa.Column("fulfillment_type", sa.String(64)),
        sa.Column("unique_no", sa.String(64)),
        sa.Column("delete_flag", sa.SmallInteger(), nullable=False),
        sa.Column(
            "extra_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column(
            "raw_request_ref_id",
            sa.Uuid(),
            sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL"),
        ),
        sa.Column("first_seen_run_id", sa.Uuid()),
        sa.Column("last_seen_run_id", sa.Uuid()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_since", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "line_key",
            name="uq_ods_lingxing_walmart_bill_lines_line",
        ),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        sa.CheckConstraint("delete_flag IN (0, 1)", name="delete_flag"),
    )
    op.create_index("ix_walmart_bill_lines_store_posted", LINES, ["store_id", "posted_date"])
    op.create_index("ix_walmart_bill_lines_store_report", LINES, ["store_id", "report_key"])
    op.create_index("ix_walmart_bill_lines_store_lx_line", LINES, ["store_id", "lx_line_id"])

    op.create_table(
        PERIODS,
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(32), primary_key=True),
        sa.Column("report_key", sa.String(64), primary_key=True),
        sa.Column("store_name", sa.String(255)),
        sa.Column("report_id", sa.String(32)),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("period_start_date", sa.Date()),
        sa.Column("period_end_date", sa.Date()),
        sa.Column("first_posted_date", sa.Date()),
        sa.Column("last_posted_date", sa.Date()),
        sa.Column("currency_code", sa.String(8)),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("excluded_line_count", sa.Integer(), nullable=False),
        sa.Column("amount_sum", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_payable", sa.Numeric(18, 4)),
        sa.Column("payable_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "amounts_by_type",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_run_id", sa.Uuid()),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('normal', 'not_payable', 'voided')", name="status"),
    )
    op.create_index("ix_walmart_bill_periods_report_date", PERIODS, ["report_date"])

    bind = op.get_bind()
    for key, kind, action, name in (
        (PAGE_KEY, "page", None, "回款对账"),
        (SYNC_KEY, "action", "sync", "手动同步沃尔玛账单"),
    ):
        bind.execute(
            sa.text(
                """INSERT INTO app_permissions
         (permission_key,name,group_key,description,permission_type,module_key,page_key,
          action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
         VALUES (:key,:name,'finance',:name,:kind,'finance','finance_settlement_reconciliation',
          :action,NULL,'normal',70041,true,now(),now())
         ON CONFLICT(permission_key) DO NOTHING"""
            ),
            {"key": key, "name": name, "kind": kind, "action": action},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"select 1 from {LINES} limit 1")).first() is not None:
        raise RuntimeError(f"{LINES} has data; refusing to drop it")
    if bind.scalar(
        sa.text("SELECT count(*) FROM app_role_permissions WHERE permission_key=:key"),
        {"key": SYNC_KEY},
    ):
        raise RuntimeError("WALMART_BILL_SYNC_PERMISSION_IN_USE")
    bind.execute(
        sa.text("DELETE FROM app_permissions WHERE permission_key=:key"), {"key": SYNC_KEY}
    )
    op.drop_index("ix_walmart_bill_periods_report_date", table_name=PERIODS)
    op.drop_table(PERIODS)
    op.drop_index("ix_walmart_bill_lines_store_lx_line", table_name=LINES)
    op.drop_index("ix_walmart_bill_lines_store_report", table_name=LINES)
    op.drop_index("ix_walmart_bill_lines_store_posted", table_name=LINES)
    op.drop_table(LINES)
