"""Lock the first WFS-positive Los Angeles business date per account/store/Item ID.

The existing daily inventory fact is append/upsert and can be revised or pruned;
the launch date must NOT be recomputed from mutable history once captured.
Historical positive observations are backfilled once on migration. Later
positive INSERT/UPDATE observations insert only if absent (ON CONFLICT DO NOTHING).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261104_0072_wfs_la_lock"
down_revision: str | Sequence[str] | None = "20261102_0071_skill_lib"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_wfs_first_stock_la_locked",
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("first_wfs_available_date_la", sa.Date(), nullable=False),
        sa.Column("first_observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("msku_at_first_stock", sa.Text(), nullable=True),
        sa.Column("date_source", sa.String(40), nullable=False),
        sa.Column(
            "locked_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            name="pk_listing_wfs_first_stock_la_locked",
        ),
    )

    # Backfill earliest known positive WFS inventory date per stable Listing.
    # NOTE: earliest recorded observation is not proof of stock before monitoring.
    op.execute("""
        INSERT INTO public.listing_wfs_first_stock_la_locked
          (source_account_ref, store_id, item_id,
           first_wfs_available_date_la, first_observed_at_utc,
           msku_at_first_stock, date_source)
        SELECT DISTINCT ON (f.source_account_ref, f.store_id, f.item_id)
          f.source_account_ref, f.store_id, f.item_id,
          f.snapshot_date_la, f.captured_at, f.msku,
          'historical_wfs_snapshot'
        FROM public.fact_walmart_listing_inventory_daily AS f
        WHERE f.wfs_available_quantity >= 1
        ORDER BY f.source_account_ref, f.store_id, f.item_id,
                 f.snapshot_date_la ASC, f.captured_at ASC
        ON CONFLICT (source_account_ref, store_id, item_id) DO NOTHING
    """)

    # SECURITY DEFINER lets the existing sync writer insert the immutable
    # registration even if it only holds DML rights on the inventory fact.
    # Fully-qualified tables and a fixed search_path prevent name substitution.
    op.execute("""
        CREATE FUNCTION public.capture_listing_wfs_first_stock_la_locked()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $capture$
        BEGIN
          IF NEW.wfs_available_quantity IS NOT NULL
             AND NEW.wfs_available_quantity >= 1 THEN
            INSERT INTO public.listing_wfs_first_stock_la_locked
              (source_account_ref, store_id, item_id,
               first_wfs_available_date_la, first_observed_at_utc,
               msku_at_first_stock, date_source)
            VALUES
              (NEW.source_account_ref, NEW.store_id, NEW.item_id,
               NEW.snapshot_date_la, NEW.captured_at,
               NEW.msku, 'wfs_daily_observation')
            ON CONFLICT (source_account_ref, store_id, item_id) DO NOTHING;
          END IF;
          RETURN NEW;
        END;
        $capture$
    """)
    op.execute("""
        CREATE TRIGGER trg_listing_wfs_first_stock_la_locked
        AFTER INSERT OR UPDATE OF wfs_available_quantity
        ON public.fact_walmart_listing_inventory_daily
        FOR EACH ROW
        EXECUTE FUNCTION public.capture_listing_wfs_first_stock_la_locked()
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_listing_wfs_first_stock_la_locked
        ON public.fact_walmart_listing_inventory_daily
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS public.capture_listing_wfs_first_stock_la_locked()
    """)
    op.drop_table("listing_wfs_first_stock_la_locked")
