"""Independent, auditable D01-D08 rule review records.

Revision ID: 20261024_0057_keyword_rule_decisions
Revises: 20261023_0056_merge_decodo_keyword_heads
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0057_keyword_rule_decisions"
down_revision: str | Sequence[str] | None = "20261023_0056_merge_decodo_keyword_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_kw_rule_decision",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("ai_kw_rule_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision_key", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        sa.Column("decision_json", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_by", sa.String(255), nullable=False),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("rule_version_id", "decision_key"),
        sa.CheckConstraint(
            "decision_key IN ('D01','D02','D03','D04','D05','D06','D07','D08')",
            name="ck_ai_kw_rule_decision_key",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review','approved','rejected')",
            name="ck_ai_kw_rule_decision_status",
        ),
    )
    op.create_table(
        "ai_kw_rule_decision_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "decision_id",
            sa.Uuid(),
            sa.ForeignKey("ai_kw_rule_decision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("status_before", sa.String(16)),
        sa.Column("status_after", sa.String(16), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
    )
    op.execute("""
        CREATE FUNCTION kw_guard_rule_decision() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'KW_RULE_DECISION_DELETE_FORBIDDEN';
            END IF;
            IF EXISTS (
                SELECT 1 FROM ai_kw_rule_version
                WHERE id = NEW.rule_version_id AND status <> 'draft'
            ) THEN
                RAISE EXCEPTION 'KW_FINALIZED_RULE_DECISION_IMMUTABLE';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER trg_ai_kw_rule_decision_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON ai_kw_rule_decision "
        "FOR EACH ROW EXECUTE FUNCTION kw_guard_rule_decision()"
    )
    op.execute(
        "CREATE TRIGGER trg_ai_kw_rule_decision_event_immutable "
        "BEFORE UPDATE OR DELETE ON ai_kw_rule_decision_event "
        "FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable()"
    )


def downgrade() -> None:
    op.drop_table("ai_kw_rule_decision_event")
    op.drop_table("ai_kw_rule_decision")
    op.execute("DROP FUNCTION kw_guard_rule_decision()")
