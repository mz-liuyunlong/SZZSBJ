"""WFS pending-packing drafts (V1 draft path): drafts, items, box holds, immutable events.

These four tables were only ever created by ``scripts/wfs_pending_local_schema.py`` on
a developer database, while ``app.modules.pmc_wfs`` (list, summary, POST /drafts) reads
and writes them. Without this migration any database built from Alembic alone (CI,
staging, production) lacks them.

Explicit table definitions (no app model import) on a local MetaData with the project
naming convention, so constraint/index names equal what the ORM would emit;
``tests/modules/pmc_wfs/test_pending.py::test_migration_0072_matches_orm_metadata``
compares them. A database where the local script already created all four tables is
adopted unchanged (checked, not recreated); a partial set is refused. Downgrade refuses
once any row exists.
"""

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261101_0072_wfs_pending_drafts"
down_revision = "20261030_0071_wfs_lingxing_board"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
TABLES = (
    "ops_pmc_wfs_drafts",
    "ops_pmc_wfs_draft_items",
    "ops_pmc_wfs_box_allocations",
    "evt_pmc_wfs_draft_events",
)
J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _tables(metadata: sa.MetaData) -> list[sa.Table]:
    # Referenced domestic tables (already migrated); declared only so FK names resolve.
    sa.Table("ops_domestic_packing_orders", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    sa.Table(
        "ops_domestic_packing_box_lines", metadata, sa.Column("id", sa.Uuid(), primary_key=True)
    )
    drafts = sa.Table(
        "ops_pmc_wfs_drafts",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("number", sa.String(64), nullable=False, unique=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False, index=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("business_test", sa.Boolean(), nullable=False),
        sa.Column("payload", J, nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'pending'", name="wfs_pending_only"),
    )
    items = sa.Table(
        "ops_pmc_wfs_draft_items",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "draft_id",
            sa.Uuid(),
            sa.ForeignKey("ops_pmc_wfs_drafts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("sku", sa.String(255), nullable=False),
        sa.Column("gtin", sa.String(14), nullable=False),
        sa.Column("boxes", sa.Integer(), nullable=False),
        sa.Column("units_per_box", sa.Integer(), nullable=False),
        sa.Column("snapshot", J, nullable=False),
        sa.CheckConstraint("boxes>0 AND units_per_box>0", name="wfs_item_quantity"),
    )
    allocations = sa.Table(
        "ops_pmc_wfs_box_allocations",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "item_id", sa.Uuid(), sa.ForeignKey("ops_pmc_wfs_draft_items.id"), nullable=False
        ),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("ops_domestic_packing_orders.id"), nullable=False
        ),
        sa.Column(
            "box_line_id",
            sa.Uuid(),
            sa.ForeignKey("ops_domestic_packing_box_lines.id"),
            nullable=False,
        ),
        sa.Column("box_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", J, nullable=False),
        sa.UniqueConstraint("box_line_id"),
        sa.Index("ix_wfs_alloc_order", "order_id"),
    )
    events = sa.Table(
        "evt_pmc_wfs_draft_events",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_json", J, nullable=False),
        sa.Column("response_json", J, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_account_ref", "idempotency_key"),
    )
    return [drafts, items, allocations, events]


def _existing(bind) -> set[str]:
    return {t for t in TABLES if bind.execute(text("SELECT to_regclass(:n)"), {"n": t}).scalar()}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing(bind)
    if existing == set(TABLES):
        return  # created earlier by the local setup script; adopt as-is
    if existing:
        raise RuntimeError(f"partial WFS draft schema present: {sorted(existing)}; inspect first")
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    for table in _tables(metadata):
        table.create(bind=bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION prevent_pmc_wfs_event_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'WFS events are immutable'; END;
            $$ LANGUAGE plpgsql"""
        )
        op.execute(
            """CREATE TRIGGER pmc_wfs_events_immutable BEFORE UPDATE OR DELETE
            ON evt_pmc_wfs_draft_events FOR EACH ROW
            EXECUTE FUNCTION prevent_pmc_wfs_event_mutation()"""
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        if bind.execute(text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError(f"{table} has rows; refusing to drop evidence")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS pmc_wfs_events_immutable ON evt_pmc_wfs_draft_events")
        op.execute("DROP FUNCTION IF EXISTS prevent_pmc_wfs_event_mutation()")
    for table in reversed(TABLES):
        op.drop_table(table)
