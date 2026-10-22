"""Join the Walmart order-identity head with the domestic packing head.

Revision ID: 20261022_0054_merge_walmart_identity_and_domestic_packing
Revises: 20261020_0047_walmart_order_identity_guard,
          20261022_0053_domestic_packing_production_compat
Create Date: 2026-10-22

The merge keeps both existing revision ids. This revision also creates
ops_domestic_packing_extra_allocations. Databases already stamped here must
not rely on a later edit of this file.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261022_0054_merge_walmart_identity_and_domestic_packing"
down_revision: str | Sequence[str] | None = (
    "20261020_0047_walmart_order_identity_guard",
    "20261022_0053_domestic_packing_production_compat",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ops_domestic_packing_extra_allocations"
INDEX = "ix_packing_extra_source"
EXPECTED_TYPES = {
    "id": "uuid",
    "order_id": "uuid",
    "source_account_ref": "character varying(128)",
    "warehouse_id": "character varying(64)",
    "sku": "character varying(255)",
    "source_publication_id": "uuid",
    "source_board_id": "uuid",
    "qty": "integer",
    "created_at": "timestamp with time zone",
}
EXPECTED_FOREIGN_KEYS = {
    (("order_id",), "ops_domestic_packing_orders", ("id",), "r"),
    (
        ("source_publication_id", "source_board_id"),
        "mart_domestic_inbound_batch_board",
        ("publication_id", "id"),
        "r",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        _require_current_shape(bind)
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("warehouse_id", sa.String(64), nullable=False),
        sa.Column("sku", sa.String(255), nullable=False),
        sa.Column("source_publication_id", sa.Uuid(), nullable=False),
        sa.Column("source_board_id", sa.Uuid(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["ops_domestic_packing_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("order_id", "source_board_id", name="uq_packing_extra_order_board"),
        sa.CheckConstraint("qty>0", name="packing_extra_qty"),
    )
    op.create_index(
        INDEX,
        TABLE,
        ["source_account_ref", "warehouse_id", "source_board_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    occupied = bind.scalar(sa.text("SELECT count(*) FROM ops_domestic_packing_extra_allocations"))
    if occupied:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_NONEMPTY")
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)


def _require_current_shape(bind: sa.Connection) -> None:
    columns = {
        row.name: (row.formatted, row.required)
        for row in bind.execute(
            sa.text(
                """
                SELECT a.attname AS name,
                       format_type(a.atttypid, a.atttypmod) AS formatted,
                       a.attnotnull AS required
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = :table
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """
            ),
            {"table": TABLE},
        )
    }
    if columns.keys() != EXPECTED_TYPES.keys() or any(
        columns[name] != (EXPECTED_TYPES[name], True) for name in EXPECTED_TYPES
    ):
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_COLUMNS_MISMATCH")
    primary_key = bind.execute(
        sa.text(
            """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = :table AND i.indisprimary
            """
        ),
        {"table": TABLE},
    ).scalars()
    if list(primary_key) != ["id"]:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_PRIMARY_KEY_MISMATCH")
    foreign_keys = {
        (tuple(row.cols), row.ref_table, tuple(row.ref_cols), row.delete_action)
        for row in bind.execute(
            sa.text(
                """
                SELECT confrel.relname AS ref_table,
                       con.confdeltype AS delete_action,
                       (
                         SELECT array_agg(src.attname ORDER BY u.ord)
                         FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
                         JOIN pg_attribute src
                           ON src.attrelid = con.conrelid AND src.attnum = u.attnum
                       ) AS cols,
                       (
                         SELECT array_agg(dst.attname ORDER BY u.ord)
                         FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
                         JOIN pg_attribute dst
                           ON dst.attrelid = con.confrelid AND dst.attnum = u.attnum
                       ) AS ref_cols
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = rel.relnamespace
                JOIN pg_class confrel ON confrel.oid = con.confrelid
                WHERE ns.nspname = 'public' AND rel.relname = :table AND con.contype = 'f'
                """
            ),
            {"table": TABLE},
        )
    }
    if foreign_keys != EXPECTED_FOREIGN_KEYS:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_FOREIGN_KEY_MISMATCH")
    unique_keys = {
        tuple(row.cols)
        for row in bind.execute(
            sa.text(
                """
                SELECT (
                  SELECT array_agg(src.attname ORDER BY u.ord)
                  FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
                  JOIN pg_attribute src
                    ON src.attrelid = con.conrelid AND src.attnum = u.attnum
                ) AS cols
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = rel.relnamespace
                WHERE ns.nspname = 'public' AND rel.relname = :table AND con.contype = 'u'
                """
            ),
            {"table": TABLE},
        )
    }
    if unique_keys != {("order_id", "source_board_id")}:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_UNIQUE_MISMATCH")
    checks = {
        " ".join(row.definition.lower().split())
        for row in bind.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = rel.relnamespace
                WHERE ns.nspname = 'public' AND rel.relname = :table AND con.contype = 'c'
                """
            ),
            {"table": TABLE},
        )
    }
    if checks != {"check ((qty > 0))"}:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_CHECK_MISMATCH")
    index = bind.execute(
        sa.text(
            """
            SELECT pg_get_indexdef(ix.indexrelid)
            FROM pg_index ix
            JOIN pg_class idx ON idx.oid = ix.indexrelid
            JOIN pg_class tbl ON tbl.oid = ix.indrelid
            JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
            WHERE ns.nspname = 'public' AND tbl.relname = :table AND idx.relname = :index
            """
        ),
        {"table": TABLE, "index": INDEX},
    ).scalar()
    normalized = " ".join((index or "").lower().split())
    expected_index = (
        "create index ix_packing_extra_source on public.ops_domestic_packing_extra_allocations "
        "using btree (source_account_ref, warehouse_id, source_board_id)"
    )
    if normalized != expected_index:
        raise RuntimeError("PACKING_EXTRA_ALLOCATIONS_INDEX_MISMATCH")
