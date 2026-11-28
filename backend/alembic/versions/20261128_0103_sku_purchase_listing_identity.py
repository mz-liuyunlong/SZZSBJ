"""Listing-grain first purchase: preserve claims and map only proven historical identities."""

import sqlalchemy as sa

from alembic import op

revision = "20261128_0103_sku_purchase_listing_identity"

down_revision = "20261128_0102_woocommerce_store_config"

branch_labels = None
depends_on = None

TABLE = "biz_new_product_sku_purchase_plans"
ACTIVE = (
    "submission_status IN ('pending','submitting','unknown','submitted') "
    "AND cancellation_status IS DISTINCT FROM 'confirmed'"
)

# Match the actual existing durable attempt event, never today's Listing count.
# An ambiguous or duplicate historical mapping is intentionally left NULL.
BACKFILL = """
WITH verified AS (
    SELECT p.id,p.sku_progress_id,p.store_id,min(e.after_json->>'item_id') AS item_id
    FROM biz_new_product_sku_purchase_plans p
    JOIN biz_new_product_sku_progress_events e
      ON e.sku_progress_id=p.sku_progress_id
     AND e.event_key=p.id::text || chr(58) || 'attempt'
     AND e.event_type='purchase_attempt'
    GROUP BY p.id,p.sku_progress_id,p.store_id
    HAVING count(*)=1 AND bool_and(
        COALESCE(e.after_json->>'store_id'=p.store_id,false)
        AND COALESCE(e.after_json->>'item_id' ~ '^[0-9]{11}$',false)
    )
), unique_claims AS (
    SELECT v.*,count(*) OVER (PARTITION BY sku_progress_id,store_id,item_id) AS copies
    FROM verified v
)
UPDATE biz_new_product_sku_purchase_plans AS p SET item_id=v.item_id
FROM unique_claims v WHERE p.id=v.id AND v.copies=1
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    # Prevent old write paths from racing the identity upgrade; transaction-scoped.
    op.execute("LOCK TABLE biz_new_product_sku_purchase_plans IN ACCESS EXCLUSIVE MODE")
    op.add_column(TABLE, sa.Column("item_id", sa.String(128), nullable=True))
    op.execute(BACKFILL)
    op.drop_index("uq_sku_purchase_active_store", table_name=TABLE)
    op.create_index(
        "uq_sku_purchase_active_listing",
        TABLE,
        ["sku_progress_id", "store_id", "item_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE + " AND item_id IS NOT NULL"),
    )
    op.create_index(
        "uq_sku_purchase_active_legacy_store",
        TABLE,
        ["sku_progress_id", "store_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE + " AND item_id IS NULL"),
    )
    # NOT VALID preserves old unresolved rows but enforces exact identity on all
    # new writes. Old application code cannot insert a claim and then POST.
    op.execute(
        "ALTER TABLE biz_new_product_sku_purchase_plans ADD CONSTRAINT "
        "ck_sku_purchase_listing_identity CHECK "
        "(item_id IS NOT NULL AND item_id ~ '^[0-9]{11}$') NOT VALID"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("LOCK TABLE biz_new_product_sku_purchase_plans IN ACCESS EXCLUSIVE MODE")
    # Reverting a nonempty table would erase Listing attribution or recreate a
    # conflicting store-level uniqueness rule. Never discard purchase history.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM biz_new_product_sku_purchase_plans) THEN
        RAISE EXCEPTION 'SKU_PURCHASE_LISTING_DOWNGRADE_BLOCKED_NONEMPTY';
      END IF;
    END; $$""")
    op.drop_constraint("ck_sku_purchase_listing_identity", TABLE, type_="check")
    op.drop_index("uq_sku_purchase_active_listing", table_name=TABLE)
    op.drop_index("uq_sku_purchase_active_legacy_store", table_name=TABLE)
    op.create_index(
        "uq_sku_purchase_active_store",
        TABLE,
        ["sku_progress_id", "store_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.drop_column(TABLE, "item_id")
