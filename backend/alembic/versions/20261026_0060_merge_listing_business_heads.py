"""Merge Listing rule configuration and latest business connector migration heads.

Graph-only revision. This is not authorization to migrate any live database.
"""

from collections.abc import Sequence

revision: str = "20261026_0060_merge_listing_business_heads"
down_revision: str | Sequence[str] | None = (
    "20261025_0055_listing_grade_rule_versions",
    "20261025_0059_business_connector_control",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
