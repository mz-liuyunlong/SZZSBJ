"""Merge Listing tag scope and Walmart gateway ledger heads without schema changes."""

revision = "20261102_0071_merge_listing_tags_and_walmart_gateway"
down_revision = (
    "20261031_0070_listing_tag_account_scope",
    "20261031_0069_walmart_gateway_ledger",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
