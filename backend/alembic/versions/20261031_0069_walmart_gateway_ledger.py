"""Unified Walmart gateway: call audit rows and write-idempotency ledger (handover 76.6).

Explicit DDL (no ORM import) so the migration is stable even when the models move on;
``tests/modules/walmart_scf/test_persistence.py::test_migration_0069_matches_orm_metadata``
checks it against the ORM metadata. No data, no permission grant. Downgrade refuses once
rows exist (evidence is never dropped).
"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "20261031_0069_walmart_gateway_ledger"
down_revision = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None

CALLS = "integration_walmart_calls"
LEDGER = "integration_walmart_write_ledger"


def upgrade() -> None:
    op.create_table(
        CALLS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_code", sa.String(16), nullable=False),
        sa.Column("operation_key", sa.String(128), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("approval_ref", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("contract_sha256", sa.String(64), nullable=True),
        sa.Column("registry_version", sa.String(32), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{CALLS}"),
    )
    for column in ("store_code", "operation_key", "idempotency_key", "outcome", "created_at"):
        op.create_index(f"ix_{CALLS}_{column}", CALLS, [column])

    op.create_table(
        LEDGER,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(16), nullable=False),
        sa.Column("operation_key", sa.String(128), nullable=False),
        sa.Column("actor_uid", sa.String(128), nullable=False),
        sa.Column("approval_ref", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{LEDGER}"),
        sa.UniqueConstraint("idempotency_key", name="uq_walmart_write_ledger_key"),
    )
    op.create_index(f"ix_{LEDGER}_outcome", LEDGER, ["outcome"])


def downgrade() -> None:
    bind = op.get_bind()
    for table in (LEDGER, CALLS):
        if bind.execute(text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError(f"{table} has rows; refusing to drop evidence")
    op.drop_index(f"ix_{LEDGER}_outcome", table_name=LEDGER)
    op.drop_table(LEDGER)
    for column in ("created_at", "outcome", "idempotency_key", "operation_key", "store_code"):
        op.drop_index(f"ix_{CALLS}_{column}", table_name=CALLS)
    op.drop_table(CALLS)
