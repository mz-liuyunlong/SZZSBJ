"""Add temporary selected legacy mirror tables.

Revision ID: 20261006_0029_legacy_selected_mirror_tables
Revises: 20260929_0028_listing_archive_reason
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261006_0029_legacy_selected_mirror_tables"
down_revision: str | Sequence[str] | None = "20260929_0028_listing_archive_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_SCHEMA = "legacy_mirror"
LEGACY_SCHEMA_COMMENT = (
    "Temporary mirror for selected legacy MySQL tables. This schema is not a "
    "new-system business model and may be removed by