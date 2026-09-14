"""Allow many source paths for one lineage target field.

Revision ID: 20260914_0008
Revises: 20260913_0007
Create Date: 2026-09-14

The replacement unique constraint identifies one exact lineage edge within a
RAW request. Upgrade and downgrade rebuild one unique index and may briefly
lock ``gov_data_lineage``; run only in an approved migration window after a
backup or snapshot. No rows are rewritten.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260914_0008"
down_revision: str | Sequence[str] | None = "20260913_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_gov_data_lineage_target",
        "gov_data_lineage",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_gov_data_lineage_target",
        "gov_data_lineage",
        [
            "raw_request_ref_id",
            "target_table",
            "target_record_id",
            "target_field",
            "source_path",
            "transform_key",
            "transform_version",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_gov_data_lineage_target",
        "gov_data_lineage",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_gov_data_lineage_target",
        "gov_data_lineage",
        [
            "raw_request_ref_id",
            "target_table",
            "target_record_id",
            "target_field",
            "source_path",
            "transform_version",
        ],
    )
