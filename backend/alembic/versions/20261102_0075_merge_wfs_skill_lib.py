"""Merge main's AI Skill library chain (0070_ai_skill_soft_delete -> 0071_skill_lib) with the
WFS V2 + Walmart gateway merge (0074_merge_wfs_walmart_gateway). No application tables change."""

revision = "20261102_0075_merge_wfs_skill_lib"
down_revision = (
    "20261102_0074_merge_wfs_walmart_gateway",
    "20261102_0071_skill_lib",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
