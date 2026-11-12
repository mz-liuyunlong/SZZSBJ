"""PR337: new-product rules, market review, purchase applications, tracking decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261112_0087_new_product_performance"
down_revision: str | Sequence[str] | None = "20261111_0086_finance_journal_cny_alert_close"
branch_labels = None
depends_on = None


def ts():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def ident():
    return [
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
    ]


def upgrade():
    op.create_table(
        "biz_new_product_rule_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by", sa.String(128), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("kind", "version", name="uq_np_rule_kind_version"),
        sa.CheckConstraint("kind IN ('performance','tracking')", name="ck_np_rule_kind"),
        sa.CheckConstraint("version >= 1", name="ck_np_rule_version"),
    )
    op.create_table(
        "biz_new_product_market_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *ident(),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref", "store_id", "item_id", name="uq_np_market_identity"
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 10", name="ck_np_market_score"),
    )
    op.create_index(
        "ix_np_market_updated",
        "biz_new_product_market_scores",
        ["source_account_ref", "updated_at"],
    )
    op.create_table(
        "biz_new_product_purchase_applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *ident(),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("suggested_qty", sa.Integer(), nullable=False),
        sa.Column("request_reason", sa.Text(), nullable=False),
        sa.Column("score_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("score_rule_version", sa.Integer(), nullable=False),
        sa.Column("applicant_id", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        ts(),
        sa.CheckConstraint(
            "status IN ('submitted','approved','rejected')", name="ck_np_purchase_status"
        ),
        sa.CheckConstraint("requested_qty > 0 AND suggested_qty > 0", name="ck_np_purchase_qty"),
    )
    op.create_index(
        "ix_np_purchase_scope_status",
        "biz_new_product_purchase_applications",
        ["source_account_ref", "status", "created_at"],
    )
    op.create_index(
        "ix_np_purchase_item",
        "biz_new_product_purchase_applications",
        ["source_account_ref", "store_id", "item_id"],
    )
    op.create_index(
        "uq_np_purchase_pending",
        "biz_new_product_purchase_applications",
        ["source_account_ref", "store_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("status='submitted'"),
    )
    op.create_table(
        "biz_new_product_tracking_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *ident(),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("evaluated_facts", postgresql.JSONB(), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_ref", "store_id", "item_id", name="uq_np_tracking_identity"
        ),
        sa.CheckConstraint(
            "decision IN ('打品成功','继续观察','需要优化','打品失败')",
            name="ck_np_tracking_decision",
        ),
    )
    op.create_index(
        "ix_np_tracking_status",
        "biz_new_product_tracking_decisions",
        ["source_account_ref", "decision"],
    )
    op.create_table(
        "biz_new_product_action_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *ident(),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        ts(),
    )
    op.create_index(
        "ix_np_event_identity_time",
        "biz_new_product_action_events",
        ["source_account_ref", "store_id", "item_id", "created_at"],
    )


def downgrade():
    # Never silently destroy user decisions, approvals or rule history.
    for name in [
        "biz_new_product_action_events",
        "biz_new_product_tracking_decisions",
        "biz_new_product_purchase_applications",
        "biz_new_product_market_scores",
        "biz_new_product_rule_versions",
    ]:
        bind = op.get_bind()
        if bind.scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("REFUSE destructive downgrade: " + name + " contains business data")
    op.drop_table("biz_new_product_action_events")
    op.drop_table("biz_new_product_tracking_decisions")
    op.drop_table("biz_new_product_purchase_applications")
    op.drop_table("biz_new_product_market_scores")
    op.drop_table("biz_new_product_rule_versions")
