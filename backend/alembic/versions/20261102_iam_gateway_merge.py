"""Join Walmart gateway ledger and Feishu IAM chains without replaying migrations."""

revision = "20261102_iam_gateway_merge"
down_revision = (
    "20261031_0069_walmart_gateway_ledger",
    "20261031_0070_feishu_org_snapshot",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Both parent chains must already be applied; no table or grant changes."""


def downgrade() -> None:
    """No schema changes; Alembic downgrades both ancestor branches normally."""
