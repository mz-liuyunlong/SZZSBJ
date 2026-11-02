"""Merge the WFS V2 chain (0068_wfs_creation -> 0069_wfs_exception_center) with main's
0068_walmart_remote_jobs. No application tables change."""

revision = "20261030_0070_merge_wfs_walmart_remote"
down_revision = (
    "20261029_0068_walmart_remote_jobs",
    "20261029_0069_wfs_exception_center",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
