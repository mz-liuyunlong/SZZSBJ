"""Merge PMC packing and main's monitor chain without changing application tables."""

revision = "20261028_0067_merge_pmc_main"
down_revision = (
    "20261028_0062_packing_pending_edit",
    "20261028_0066_walmart_monitor_listing_projection",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
