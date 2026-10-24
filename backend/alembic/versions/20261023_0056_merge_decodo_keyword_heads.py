"""Merge Decodo and keyword V1.1 migration heads. Metadata only.

Do not confuse this graph merge with a database migration execution.
"""

from collections.abc import Sequence

revision: str = "20261023_0056_merge_decodo_keyword_heads"
down_revision: str | Sequence[str] | None = (
    "20261022_0048_decodo_config_usage",
    "20261023_0055_keyword_planning_core",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
