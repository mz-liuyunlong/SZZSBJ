"""add listing archive reason

Revision ID: 20260929_0028_listing_archive_reason
Revises: 20260929_0027_listing_archive_state
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "20260929_0028_listing_archive_reason"
down_revision: str | Sequence[str] | None = "20260929_0027_listing_archive_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("listing_archive_states")}

    if "archive_reason" not in columns:
        op.add_column(
            "listing_archive_states",
            sa.Column("archive_reason", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("listing_archive_states")}

    if "archive_reason" in columns:
        op.drop_column("listing_archive_states", "archive_reason")
