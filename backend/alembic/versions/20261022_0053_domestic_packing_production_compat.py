"""Allow formal production packing records and create the warehouse tables.

Schema only. Existing local verification rows stay in place and are not copied.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261022_0053_domestic_packing_production_compat"
down_revision = "20261021_0052_domestic_packing_manual"
branch_labels = None
depends_on = None

EVENT_KINDS = (
    "approve",
    "reject",
    "link",
    "void",
    "test",
    "boxes",
    "done",
    "customs",
    "note",
    "unpacked",
    "rebox",
    "ib",
    "sync",
)

PERMISSIONS = (
    ("packing-boxes-save", "保存仓库装箱", "保存仓库装箱", 100024),
    ("packing-done", "确认打包完成", "确认打包完成", 100025),
    ("packing-customs", "修改打包报关", "修改打包报关", 100026),
    ("packing-note", "填写打包延迟备注", "填写打包延迟备注", 100027),
    ("packing-unpacked-dispose", "处置未装数量", "中台处置未装数量，仓库无此权限", 100028),
    ("packing-rebox", "修改已完成装箱", "修改已完成装箱，须填写原因并重新校验", 100029),
    ("packing-supplement-ib", "登记超发补入库单", "中台独立授权：登记超发补入库单", 100030),
    ("packing-supplement-sync", "校验超发补入库数据", "中台独立授权：校验超发补入库数据", 100031),
)


def upgrade():
    bind = op.get_bind()
    _drop_forced_test_check(bind)
    _replace_event_kind_check(bind)
    _create_warehouse_tables()
    _insert_permissions(bind)


def downgrade():
    raise RuntimeError("PACKING_PRODUCTION_COMPAT_REQUIRES_VERIFIED_BACKUP_RESTORE")


def _drop_forced_test_check(bind):
    names = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.ops_domestic_packing_orders'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) ILIKE '%is_test%'
              AND pg_get_constraintdef(oid) NOT ILIKE '%business_test%'
            """
        )
    ).scalars()
    for name in names:
        op.drop_constraint(name, "ops_domestic_packing_orders", type_="check")


def _replace_event_kind_check(bind):
    names = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.evt_domestic_packing_events'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%event_kind%'
            """
        )
    ).scalars()
    for name in names:
        op.drop_constraint(name, "evt_domestic_packing_events", type_="check")
    kinds = ", ".join(f"'{kind}'" for kind in EVENT_KINDS)
    op.create_check_constraint(
        "packing_event_kind",
        "evt_domestic_packing_events",
        f"event_kind IN ({kinds})",
    )


def _create_warehouse_tables():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("ops_domestic_packing_box_sets"):
        op.create_table(
            "ops_domestic_packing_box_sets",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("order_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("total_qty", sa.Integer(), nullable=False),
            sa.Column("approved_qty_snapshot", sa.Integer(), nullable=False),
            sa.Column("variance_reason", sa.String(500)),
            sa.Column("package_snapshot", postgresql.JSONB()),
            sa.Column("product_snapshot_id", sa.Uuid()),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("completed_by", sa.String(128)),
            sa.Column("actor_uid", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["product_snapshot_id"],
                ["dwd_lingxing_sku_product_info_snapshots.id"],
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("order_id"),
            sa.CheckConstraint("version>0", name="warehouse_box_version"),
            sa.CheckConstraint("total_qty BETWEEN 1 AND 1000000", name="warehouse_box_total"),
            sa.CheckConstraint(
                "approved_qty_snapshot BETWEEN 1 AND 1000000", name="warehouse_approved_qty"
            ),
            sa.CheckConstraint(
                "(completed_at IS NULL AND completed_by IS NULL) OR "
                "(completed_at IS NOT NULL AND completed_by IS NOT NULL)",
                name="warehouse_completion",
            ),
        )
    if not inspector.has_table("ops_domestic_packing_box_lines"):
        op.create_table(
            "ops_domestic_packing_box_lines",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("box_set_id", sa.Uuid(), nullable=False),
            sa.Column("line_no", sa.Integer(), nullable=False),
            sa.Column("box_type", sa.String(16), nullable=False),
            sa.Column("boxes", sa.Integer(), nullable=False),
            sa.Column("units_per_box", sa.Integer(), nullable=False),
            sa.Column("length_cm", sa.Numeric(12, 4), nullable=False),
            sa.Column("width_cm", sa.Numeric(12, 4), nullable=False),
            sa.Column("height_cm", sa.Numeric(12, 4), nullable=False),
            sa.Column("gross_weight_kg", sa.Numeric(12, 4), nullable=False),
            sa.ForeignKeyConstraint(
                ["box_set_id"], ["ops_domestic_packing_box_sets.id"], ondelete="RESTRICT"
            ),
            sa.UniqueConstraint("box_set_id", "line_no"),
            sa.CheckConstraint("line_no BETWEEN 1 AND 20", name="warehouse_line_no"),
            sa.CheckConstraint("box_type IN ('A','B','C','custom')", name="warehouse_box_type"),
            sa.CheckConstraint(
                "boxes BETWEEN 1 AND 9999 AND units_per_box BETWEEN 1 AND 100000",
                name="warehouse_line_quantity",
            ),
            sa.CheckConstraint(
                "length_cm BETWEEN 1 AND 300 AND width_cm BETWEEN 1 AND 300 "
                "AND height_cm BETWEEN 1 AND 300",
                name="warehouse_box_dimensions",
            ),
            sa.CheckConstraint("gross_weight_kg BETWEEN 0.01 AND 200", name="warehouse_box_weight"),
        )
    if not inspector.has_table("ops_domestic_packing_notes"):
        op.create_table(
            "ops_domestic_packing_notes",
            sa.Column("order_id", sa.Uuid(), primary_key=True),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("text", sa.String(500), nullable=False),
            sa.Column("resolved", sa.Boolean(), nullable=False),
            sa.Column("last_event_id", sa.Uuid(), nullable=False),
            sa.Column("actor_uid", sa.String(128), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["last_event_id"], ["evt_domestic_packing_events.id"], ondelete="RESTRICT"
            ),
            sa.CheckConstraint(
                "category IN ('arrival_incomplete','labels','materials','operations',"
                "'schedule','quality','other','resolved')",
                name="warehouse_note_category",
            ),
            sa.CheckConstraint(
                "category<>'other' OR length(trim(text))>=2", name="warehouse_note_text"
            ),
            sa.CheckConstraint("resolved=(category='resolved')", name="warehouse_note_resolution"),
        )
    if not inspector.has_table("ops_domestic_packing_variance_cases"):
        op.create_table(
            "ops_domestic_packing_variance_cases",
            sa.Column("order_id", sa.Uuid(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("gap_qty", sa.Integer()),
            sa.Column("reason_category", sa.String(32)),
            sa.Column("reason", sa.String(500)),
            sa.Column("supplemental_ib", sa.String(128)),
            sa.Column("evidence", postgresql.JSONB(), nullable=False),
            sa.Column("actor_uid", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
            ),
            sa.CheckConstraint("kind IN ('under','over')", name="packing_variance_kind"),
            sa.CheckConstraint(
                "state IN ('pending','blocked','ready','released','voided','resolved')",
                name="packing_variance_state",
            ),
            sa.CheckConstraint(
                "quantity>0 AND (gap_qty IS NULL OR gap_qty>=0)", name="packing_variance_qty"
            ),
        )
    if not inspector.has_table("ops_domestic_packing_notification_outbox"):
        op.create_table(
            "ops_domestic_packing_notification_outbox",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("order_id", sa.Uuid(), nullable=False),
            sa.Column("order_version", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
            ),
            sa.UniqueConstraint("order_id", "order_version", "kind"),
            sa.CheckConstraint(
                "state IN ('pending_configuration','cancelled','delivered','failed')",
                name="packing_notice_state",
            ),
        )


def _insert_permissions(bind):
    for action, name, description, sort_order in PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO app_permissions
                (permission_key,name,group_key,description,permission_type,module_key,page_key,
                 action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
                VALUES (:key,:name,'pmc',:description,'action','pmc','pmc_domestic_warehouse_board',
                        :action,NULL,'normal',:sort_order,true,now(),now())
                ON CONFLICT (permission_key) DO NOTHING
                """
            ),
            {
                "key": "action:pmc:domestic-warehouse-board:" + action,
                "name": name,
                "description": description,
                "action": action,
                "sort_order": sort_order,
            },
        )
