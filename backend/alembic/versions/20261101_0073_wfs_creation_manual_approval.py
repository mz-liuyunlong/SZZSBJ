"""WFS creation: written human approval before any Walmart write (red line).

Adds state AWAITING_APPROVAL (state widened to VARCHAR(24)) and the approval record
columns approval_ref / approved_by / approved_at on ops_wfs_creation_operations, plus
CHECK wfs_creation_manual_approval: a row may leave AWAITING_APPROVAL only with all
three set. The CHECK is added NOT VALID so rows written by earlier local/test builds
are kept as evidence; every new or updated row is checked. Downgrade refuses once any
row is awaiting or carries an approval (that evidence would be lost).
"""

from sqlalchemy import text

from alembic import op

revision = "20261101_0073_wfs_creation_manual_approval"
down_revision = "20261101_0072_wfs_pending_drafts"
branch_labels = None
depends_on = None

TABLE = "ops_wfs_creation_operations"
OLD_STATES = "'QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN','PARTIAL'"
NEW_STATES = "'AWAITING_APPROVAL'," + OLD_STATES


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN state TYPE VARCHAR(24)")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT wfs_creation_state")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT wfs_creation_state CHECK (state IN ({NEW_STATES}))"
    )
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN approval_ref VARCHAR(128)")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN approved_by VARCHAR(128)")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN approved_at TIMESTAMP WITH TIME ZONE")
    op.execute(
        f"""ALTER TABLE {TABLE} ADD CONSTRAINT wfs_creation_manual_approval CHECK (
            state = 'AWAITING_APPROVAL'
            OR (approval_ref IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        ) NOT VALID"""
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        text(
            f"SELECT EXISTS(SELECT 1 FROM {TABLE} WHERE state = 'AWAITING_APPROVAL'"
            " OR approval_ref IS NOT NULL OR approved_at IS NOT NULL)"
        )
    ).scalar():
        raise RuntimeError("WFS creation approvals exist; refusing to drop approval evidence")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT wfs_creation_manual_approval")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN approved_at")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN approved_by")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN approval_ref")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT wfs_creation_state")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT wfs_creation_state CHECK (state IN ({OLD_STATES}))"
    )
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN state TYPE VARCHAR(16)")
