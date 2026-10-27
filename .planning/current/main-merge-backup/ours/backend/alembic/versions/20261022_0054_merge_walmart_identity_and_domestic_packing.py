"""Join the Walmart order-identity head with the domestic packing head.

Revision ID: 20261022_0054_merge_walmart_identity_and_domestic_packing
Revises: 20261020_0047_walmart_order_identity_guard,
          20261022_0053_domestic_packing_production_compat
Create Date: 2026-10-22

No schema change. Existing revisions stay addressable for databases that
already applied one side.
"""

from collections.abc import Sequence

revision: str = "20261022_0054_merge_walmart_identity_and_domestic_packing"
down_revision: str | Sequence[str] | None = (
    "20261020_0047_walmart_order_identity_guard",
    "20261022_0053_domestic_packing_production_compat",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
