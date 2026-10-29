"""Join local purchase draft numbers with the main business migration chain.

Both predecessor revisions remain intact for databases on either branch.
This revision changes only migration ancestry, not database tables.
"""

revision = "20261027_0061_merge_purchase_main"
down_revision = (
    "20261026_0055_purchase_board_draft_no",
    "20261026_0060_merge_listing_business_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
