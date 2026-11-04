"""Join IAM/Feishu and independent AI Skill migration histories.

Preserve immutable revision IDs and both branches. No DDL, no data mutation.
"""

revision = "20261102_iam_skill_merge"
down_revision = ("20261102_iam_gateway_merge", "20261102_0071_skill_lib")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Both parent branches must be applied before this merge revision."""


def downgrade() -> None:
    """This merge revision owns no schema changes."""
