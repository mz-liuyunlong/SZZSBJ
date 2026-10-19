"""Adopt domestic warehouse Lingxing ODS tables (four append-only snapshots).

Revision ID: 20261019_0047_domestic_warehouse_ods
Revises: 20261019_0046_operation_logs

Production may already contain these tables from
``docs/delivery/domestic-warehouse-ods-tables.sql``. This revision verifies shape
against ORM metadata or creates the tables on empty databases. It never truncates
or replaces existing rows.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261019_0047_domestic_warehouse_ods"
down_revision: str | Sequence[str] | None = "20261019_0046_operation_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    import app.modules.pmc_domestic.models  # noqa: F401  # Register ORM metadata.

    from app.db.domestic_ods_adopt import adopt_domestic_ods_tables

    adopt_domestic_ods_tables(op.get_bind())


def downgrade() -> None:
    # Adoption is not reversed automatically; dropping would destroy append-only ODS history.
    raise NotImplementedError(
        "20261019_0047_domestic_warehouse_ods is not auto-reversed; file a dedicated migration."
    )
