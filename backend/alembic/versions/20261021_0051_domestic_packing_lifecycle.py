"""Extend local decisions without rewriting M1 history or dropping immutable audit."""

# ruff: noqa: E501
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261021_0051_domestic_packing_lifecycle"
down_revision = "20261020_0050_domestic_packing_approval"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for c in inspector.get_unique_constraints("ops_domestic_packing_orders"):
        if c["column_names"] == ["source_account_ref", "candidate_id"]:
            op.drop_constraint(c["name"], "ops_domestic_packing_orders", type_="unique")
    for table, suffixes in (
        ("ops_domestic_packing_orders", ("packing_status", "packing_decision_fields")),
        ("evt_domestic_packing_events", ("packing_event_kind",)),
    ):
        for c in inspector.get_check_constraints(table):
            legacy_names = {
                "ops_domestic_packing_orders_check",
                "ops_domestic_packing_orders_status_check",
                "evt_domestic_packing_events_event_kind_check",
            }
            if c["name"] in legacy_names or any(c["name"].endswith(x) for x in suffixes):
                op.drop_constraint(c["name"], table, type_="check")
    op.add_column(
        "ops_domestic_packing_orders", sa.Column("source_snapshot_json", postgresql.JSONB())
    )
    op.add_column("ops_domestic_packing_orders", sa.Column("final_identity_key", sa.String(64)))
    op.add_column(
        "ops_domestic_packing_orders",
        sa.Column("business_test", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("ops_domestic_packing_orders", sa.Column("voided_at", sa.DateTime(timezone=True)))
    op.add_column("ops_domestic_packing_orders", sa.Column("void_note", sa.String(500)))
    op.add_column(
        "ops_domestic_packing_allocations", sa.Column("released_at", sa.DateTime(timezone=True))
    )
    op.create_check_constraint(
        "packing_status",
        "ops_domestic_packing_orders",
        "status IN ('approved','rejected','voided')",
    )
    op.create_check_constraint(
        "packing_decision_fields",
        "ops_domestic_packing_orders",
        "(status IN ('approved','voided') AND pk IS NOT NULL AND qty BETWEEN 1 AND 1000000) OR (status='rejected' AND pk IS NULL AND qty IS NULL)",
    )
    op.create_check_constraint(
        "packing_event_kind",
        "evt_domestic_packing_events",
        "event_kind IN ('approve','reject','link','void','test')",
    )
    for name, cols in (
        ("uq_domestic_packing_candidate_active", ["source_account_ref", "candidate_id"]),
        ("uq_domestic_packing_identity_active", ["source_account_ref", "final_identity_key"]),
    ):
        op.create_index(
            name,
            "ops_domestic_packing_orders",
            cols,
            unique=True,
            postgresql_where=sa.text("status IN ('approved','rejected')"),
        )
    op.create_table(
        "ops_domestic_packing_ows_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("ows_no", sa.String(32), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_domestic_packing_ows_current",
        "ops_domestic_packing_ows_links",
        ["source_account_ref", "ows_no"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "uq_domestic_packing_order_link_current",
        "ops_domestic_packing_ows_links",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    for action, label in (
        ("packing-link", "关联打包单OWS"),
        ("packing-void", "作废打包单"),
        ("packing-test-flag", "修改打包单业务测试标记"),
    ):
        bind.execute(
            sa.text("""INSERT INTO app_permissions
        (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
        VALUES (:key,:label,'pmc',:label,'action','pmc','pmc_domestic_warehouse_board',:action,NULL,'normal',100022,true,now(),now())
        ON CONFLICT(permission_key) DO NOTHING"""),
            {
                "key": "action:pmc:domestic-warehouse-board:" + action,
                "label": label,
                "action": action,
            },
        )


def downgrade():
    raise RuntimeError("PACKING_LIFECYCLE_AUDIT_REQUIRES_VERIFIED_BACKUP_RESTORE")
