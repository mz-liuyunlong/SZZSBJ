"""Unified Walmart gateway: call audit rows and write-idempotency ledger (handover 76.6).

Created from ORM metadata; no data, no permission grant. Downgrade refuses once rows exist.
"""

from sqlalchemy import text

from alembic import op
from app.modules.walmart_scf.persistence import WalmartCallAudit, WalmartWriteLedgerEntry

revision = "20261031_0069_walmart_gateway_ledger"
down_revision = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    WalmartCallAudit.__table__.create(bind=bind, checkfirst=False)
    WalmartWriteLedgerEntry.__table__.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("integration_walmart_write_ledger", "integration_walmart_calls"):
        if bind.execute(text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError(f"{table} has rows; refusing to drop evidence")
    WalmartWriteLedgerEntry.__table__.drop(bind=bind, checkfirst=False)
    WalmartCallAudit.__table__.drop(bind=bind, checkfirst=False)
