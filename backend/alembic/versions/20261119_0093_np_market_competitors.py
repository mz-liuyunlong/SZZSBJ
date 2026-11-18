"""Persist manual competitor Item IDs on the market-score authority.

Revision ID: 20261119_0093_np_market_competitors
Revises: 20261115_0092_role_page_catalog_alignment
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261119_0093_np_market_competitors"
down_revision = "20261115_0092_role_page_catalog_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "biz_new_product_market_scores",
        sa.Column("competitor_ids", JSONB(), nullable=True),
    )
    op.add_column(
        "biz_new_product_market_scores",
        sa.Column("no_competitors", sa.Boolean(), nullable=True),
    )
    # Backfill previous V2 writes ONLY when its saved market_version matches
    # the authoritative score version, never from a stale or foreign item.
    op.execute(
        sa.text("""
        UPDATE biz_new_product_market_scores AS m
           SET competitor_ids = p.data_coverage_json #> '{market_competitors_v1,ids}',
               no_competitors = CASE
                 WHEN jsonb_typeof(
                   p.data_coverage_json #> '{market_competitors_v1,none}'
                 ) = 'boolean'
                 THEN (p.data_coverage_json #>> '{market_competitors_v1,none}')::boolean
                 ELSE NULL END
          FROM biz_new_product_registry AS r
          JOIN biz_new_product_performance_current AS p ON p.registry_id = r.id
         WHERE r.source_account_ref = m.source_account_ref
           AND r.store_id = m.store_id
           AND r.item_id = m.item_id
           AND jsonb_typeof(p.data_coverage_json #> '{market_competitors_v1,ids}') = 'array'
           AND jsonb_typeof(p.data_coverage_json #> '{market_competitors_v1,none}') = 'boolean'
           AND p.data_coverage_json #> '{market_competitors_v1,market_version}'
               = to_jsonb(m.version)
           AND m.competitor_ids IS NULL AND m.no_competitors IS NULL
    """)
    )


def downgrade() -> None:
    op.drop_column("biz_new_product_market_scores", "no_competitors")
    op.drop_column("biz_new_product_market_scores", "competitor_ids")
