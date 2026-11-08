"""WFS Clearance Center: versioned rules, per-Listing risks and manual approvals.

Revision ID: 20261108_0082_clearance_center
Revises: 20261105_0076_listing_product_tags

No production migration is run by the local patch installer. All business
history and approvals are durable; destructive downgrade is prohibited.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20261108_0082_clearance_center"
down_revision = "20261105_0081_finance_payoneer_statement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_clearance_rule_versions",
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("changed_by", sa.String(128), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version > 0", name="ck_clearance_rule_version_positive"),
    )
    op.create_table(
        "biz_clearance_risk_current",
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("reasons_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("signals_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_gaps_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_account_ref", "store_id", "item_id", name="pk_clearance_risk_identity"),
        sa.CheckConstraint("level IN ('high','medium','low','unknown')", name="ck_clearance_risk_level"),
    )
    op.create_index("ix_clearance_risk_level", "biz_clearance_risk_current", ["level", "calculated_at"])
    op.create_table(
        "biz_clearance_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("applicant_ref", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("methods_json", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("approved_qty", sa.Integer()),
        sa.Column("sold_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("risk_at_submission", sa.String(24), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_date_la", sa.Date()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("finished_by", sa.String(128)),
        sa.Column("finish_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("requested_qty > 0", name="ck_clearance_requested_positive"),
        sa.CheckConstraint("approved_qty IS NULL OR approved_qty > 0", name="ck_clearance_approved_positive"),
        sa.CheckConstraint("sold_qty >= 0", name="ck_clearance_sales_nonnegative"),
        sa.CheckConstraint("status IN ('pending','rejected','cancelled','running','done','stock_closed')", name="ck_clearance_status"),
        sa.CheckConstraint("risk_at_submission IN ('high','medium','low','unknown')", name="ck_clearance_submission_risk"),
    )
    op.create_index(
        "uq_clearance_one_active_identity", "biz_clearance_applications",
        ["source_account_ref", "store_id", "item_id"], unique=True,
        postgresql_where=sa.text("status IN ('pending','running')"),
    )
    op.create_index("ix_clearance_application_actor", "biz_clearance_applications", ["applicant_ref", "submitted_at"])
    op.create_table(
        "biz_clearance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("biz_clearance_applications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column("detail_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_clearance_events_history", "biz_clearance_events", ["application_id", "created_at"])
    op.create_table(
        "biz_clearance_daily_runs",
        sa.Column("business_date_la", sa.Date(), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="ck_clearance_daily_run_status"),
    )
    for key, name, kind, action in [
        ("action:products:clearance-center:request", "提交清货申请", "action", "request"),
        ("action:products:clearance-center:review", "审核清货申请", "action", "review"),
        ("action:products:clearance-center:manage-rules", "管理清货规则", "action", "manage_rules"),
        ("action:products:clearance-center:complete", "完成清货任务", "action", "complete"),
    ]:
        op.execute(sa.text("""
            INSERT INTO app_permissions
              (permission_key, name, group_key, description, permission_type,
               module_key, page_key, action_key, field_key, risk_level,
               sort_order, is_active, created_at, updated_at)
            VALUES
              (:key, :name, 'products', 'WFS清货中心专属业务权限', :kind,
               'products', 'products_clearance_center', :action, NULL, 'high',
               70, TRUE, now(), now())
            ON CONFLICT (permission_key) DO NOTHING
        """).bindparams(key=key, name=name, kind=kind, action=action))


def downgrade() -> None:
    raise RuntimeError("Clearance approval, event and rule histories are immutable; downgrade refused")
