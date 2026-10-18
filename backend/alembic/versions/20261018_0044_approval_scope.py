"""Add source account to active approval uniqueness.

Revision ID: 20261018_0044_approval_scope
Revises: 20261017_0043_approval_flow

No historical approval rows are modified or backfilled.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261018_0044_approval_scope"
down_revision: str | Sequence[str] | None = "20261017_0043_approval_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(text("drop index if exists uq_approval_active_business"))
    connection.execute(
        text("""
        create unique index uq_approval_active_business
        on app_approval_requests (approval_type, source_account_ref, business_ref)
        where status in ('submitted','info_required')
        """)
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.scalar(
        text("""
        select count(*) from (
          select approval_type, business_ref
          from app_approval_requests
          where status in ('submitted','info_required')
          group by approval_type, business_ref
          having count(*) > 1
        ) conflicts
        """)
    )
    if duplicates:
        raise RuntimeError("Cannot restore original unique index: cross-account requests exist")
    connection.execute(text("drop index if exists uq_approval_active_business"))
    connection.execute(
        text("""
        create unique index uq_approval_active_business
        on app_approval_requests (approval_type, business_ref)
        where status in ('submitted','info_required')
        """)
    )
