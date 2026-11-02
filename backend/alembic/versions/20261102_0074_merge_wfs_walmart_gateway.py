"""Merge main's Walmart gateway ledger (0069_walmart_gateway_ledger) with the WFS V2 chain
(... -> 0073_wfs_creation_manual_approval). No application tables change."""

revision = "20261102_0074_merge_wfs_walmart_gateway"
down_revision = (
    "20261031_0069_walmart_gateway_ledger",
    "20261101_0073_wfs_creation_manual_approval",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
