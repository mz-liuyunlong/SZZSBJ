"""Manual drafts precede approval; retired system-management definitions are disabled."""

import sqlalchemy as sa

# ruff: noqa: E501
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261021_0052_domestic_packing_manual"
down_revision = "20261021_0051_domestic_packing_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM ops_domestic_packing_ows_links")):
        raise RuntimeError("OWS_LINK_HISTORY_PRESENT_DO_NOT_DROP")
    op.drop_table("ops_domestic_packing_ows_links")
    op.create_table(
        "ops_domestic_packing_manual_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("warehouse_id", sa.String(64), nullable=False),
        sa.Column("source_publication_id", sa.Uuid(), nullable=False),
        sa.Column("source_board_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("requested_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("customs", sa.String(16), nullable=False),
        sa.Column("rwh", sa.String(128)),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_json", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("source_account_ref", "idempotency_key"),
        sa.CheckConstraint("requested_qty BETWEEN 1 AND 1000000", name="manual_quantity"),
    )
    op.create_index(
        "ix_ops_domestic_packing_manual_requests_source_account_ref",
        "ops_domestic_packing_manual_requests",
        ["source_account_ref"],
    )
    bind = op.get_bind()
    bind.execute(
        sa.text("""INSERT INTO app_permissions
    (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
    VALUES ('action:pmc:domestic-warehouse-board:packing-manual-create','手工提交打包审批','pmc','选择入库单和同SKU商品后提交审批','action','pmc','pmc_domestic_warehouse_board','packing-manual-create',NULL,'normal',100023,true,now(),now())
    ON CONFLICT(permission_key) DO NOTHING""")
    )
    bind.execute(
        sa.text("""UPDATE app_permissions SET is_active=false,updated_at=now()
    WHERE permission_key IN ('action:pmc:domestic-warehouse-board:packing-link',
    'action:pmc:domestic-warehouse-board:packing-void','action:pmc:domestic-warehouse-board:packing-test-flag')""")
    )


def downgrade():
    raise RuntimeError("MANUAL_REQUESTS_REQUIRE_VERIFIED_BACKUP_RESTORE")
