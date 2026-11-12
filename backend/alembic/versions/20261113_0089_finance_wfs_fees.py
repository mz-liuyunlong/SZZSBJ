"""Finance: WFS fee lines (WFS 费用明细) — one table for settlement-report service fees,
return processing fees, storage fees and inbound transportation fees, attributed to items;
plus uploaded report files, manual adjustments and the per-period check against Lingxing bills.

Also registers the page / import / sync / adjust permissions on 财务 → WFS 费用明细.
Tables start empty; history is loaded in production by the deploy ticket after launch.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261113_0089_finance_wfs_fees"
down_revision: str | Sequence[str] | None = "20261112_0088_new_product_tracking_foundation"
branch_labels = None
depends_on = None

FILES = "raw_walmart_wfs_fee_files"
LINES = "fact_walmart_wfs_fee_lines"
ADJUSTS = "manual_walmart_wfs_fee_adjustments"
CHECKS = "mart_walmart_wfs_fee_checks"
PAGE_KEY = "page:finance:wfs-fees:view"
ACTIONS = (
    ("action:finance:wfs-fees:import", "import", "导入 WFS 费用报表"),
    ("action:finance:wfs-fees:sync", "sync", "同步 WFS 费用报表（沃尔玛接口）"),
    ("action:finance:wfs-fees:adjust", "adjust", "调整 WFS 费用归属 / 标已核实"),
)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        FILES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("fee_source", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),  # upload / sync / history
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("declared_total", sa.Numeric(18, 4)),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),  # parsed / rejected / empty
        sa.Column("reject_reason", sa.Text()),
        sa.Column("sync_run_id", sa.Uuid()),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128)),
        _ts("created_at"),
        sa.CheckConstraint("fee_source IN ('settlement','storage','inbound')", name="fee_source"),
        sa.CheckConstraint("origin IN ('upload','sync','history')", name="origin"),
        sa.CheckConstraint("status IN ('parsed','rejected','empty')", name="status"),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
    )
    op.create_index(
        "ix_raw_walmart_wfs_fee_files_store", FILES, ["store_id", "fee_source", "period_end"]
    )
    op.create_index("ix_raw_walmart_wfs_fee_files_sha", FILES, ["sha256"])

    op.create_table(
        LINES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(32), nullable=False),
        sa.Column("fee_source", sa.String(16), nullable=False),
        sa.Column("fee_type", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("line_key", sa.String(64), nullable=False),  # sha256[:64] of source identity
        sa.Column("source_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("date_charged", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("report_key", sa.String(64)),
        sa.Column("report_date", sa.Date()),
        sa.Column("bill_match", sa.String(32), nullable=False, server_default=""),
        sa.Column("po_number", sa.String(64), nullable=False, server_default=""),
        sa.Column("partner_id", sa.String(32), nullable=False, server_default=""),
        sa.Column("gtin", sa.String(32), nullable=False, server_default=""),
        sa.Column("item_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("msku", sa.Text(), nullable=False, server_default=""),
        sa.Column("local_sku", sa.Text(), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(18, 4)),
        sa.Column("amount_usd", sa.Numeric(18, 4), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 4)),
        sa.Column("discount_savings", sa.Numeric(18, 4)),
        sa.Column("attribution", sa.String(24), nullable=False),
        sa.Column("allocation_basis", sa.Text(), nullable=False, server_default=""),
        sa.Column("parent_line_id", sa.Uuid(), sa.ForeignKey(f"{LINES}.id", ondelete="CASCADE")),
        sa.Column("extra", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_file_id", sa.Uuid(), sa.ForeignKey(f"{FILES}.id"), nullable=False),
        sa.Column("last_file_id", sa.Uuid(), sa.ForeignKey(f"{FILES}.id"), nullable=False),
        sa.Column("missing_since", sa.DateTime(timezone=True)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("fee_source IN ('settlement','storage','inbound')", name="fee_source"),
        sa.CheckConstraint(
            "attribution IN ('matched','unmatched','allocated','allocated_check',"
            "'unallocated','company')",
            name="attribution",
        ),
        sa.CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        sa.UniqueConstraint("source_account_ref", "store_id", "line_key", name="uq_wfs_fee_line"),
    )
    op.create_index(
        "ix_fact_walmart_wfs_fee_lines_period",
        LINES,
        ["source_account_ref", "store_id", "report_key", "fee_type"],
    )
    op.create_index(
        "ix_fact_walmart_wfs_fee_lines_item", LINES, ["store_id", "item_id", "date_charged"]
    )
    op.create_index("ix_fact_walmart_wfs_fee_lines_parent", LINES, ["parent_line_id"])

    op.create_table(
        ADJUSTS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "line_id", sa.Uuid(), sa.ForeignKey(f"{LINES}.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),  # realloc / company / verified
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128)),
        _ts("created_at"),
        sa.CheckConstraint("kind IN ('realloc','company','verified')", name="kind"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
    )
    op.create_index("ix_manual_walmart_wfs_fee_adjustments_line", ADJUSTS, ["line_id"])

    op.create_table(
        CHECKS,
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(32), primary_key=True),
        sa.Column("report_key", sa.String(64), primary_key=True),
        sa.Column("fee_type", sa.String(64), primary_key=True),
        sa.Column("report_date", sa.Date()),
        sa.Column("lingxing_amount", sa.Numeric(18, 4)),
        sa.Column("lingxing_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_amount", sa.Numeric(18, 4)),
        sa.Column("report_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),  # ok / diff / lx_only / report_only
        sa.Column("verified_reason", sa.Text()),
        sa.Column("verified_by", sa.String(255)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        _ts("refreshed_at"),
        sa.CheckConstraint("status IN ('ok','diff','lx_only','report_only')", name="status"),
    )

    bind = op.get_bind()
    rows = [(PAGE_KEY, "page", None, "WFS 费用明细", 70050)] + [
        (key, "action", action, name, 70051 + order)
        for order, (key, action, name) in enumerate(ACTIONS)
    ]
    for key, kind, action, name, sort in rows:
        bind.execute(
            sa.text(
                """INSERT INTO app_permissions
         (permission_key,name,group_key,description,permission_type,module_key,page_key,
          action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
         VALUES (:key,:name,'finance',:name,:kind,'finance','finance_wfs_fees',
          :action,NULL,'normal',:sort,true,now(),now())
         ON CONFLICT(permission_key) DO NOTHING"""
            ),
            {"key": key, "name": name, "kind": kind, "action": action, "sort": sort},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (LINES, FILES, ADJUSTS, CHECKS):
        if bind.execute(sa.text(f"select 1 from {table} limit 1")).first() is not None:
            raise RuntimeError(f"{table} has data; refusing to drop it")
    keys = [PAGE_KEY] + [key for key, _, _ in ACTIONS]
    if bind.scalar(
        sa.text("SELECT count(*) FROM app_role_permissions WHERE permission_key = ANY(:keys)"),
        {"keys": keys},
    ):
        raise RuntimeError("WFS_FEES_PERMISSION_IN_USE")
    bind.execute(
        sa.text("DELETE FROM app_permissions WHERE permission_key = ANY(:keys)"), {"keys": keys}
    )
    op.drop_table(CHECKS)
    op.drop_index("ix_manual_walmart_wfs_fee_adjustments_line", table_name=ADJUSTS)
    op.drop_table(ADJUSTS)
    op.drop_index("ix_fact_walmart_wfs_fee_lines_parent", table_name=LINES)
    op.drop_index("ix_fact_walmart_wfs_fee_lines_item", table_name=LINES)
    op.drop_index("ix_fact_walmart_wfs_fee_lines_period", table_name=LINES)
    op.drop_table(LINES)
    op.drop_index("ix_raw_walmart_wfs_fee_files_sha", table_name=FILES)
    op.drop_index("ix_raw_walmart_wfs_fee_files_store", table_name=FILES)
    op.drop_table(FILES)
