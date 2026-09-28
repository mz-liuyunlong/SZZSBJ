from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20260928_0025_listing_management_price_fulfillment"
down_revision: str | None = "20260928_0023_operation_plan_item_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text("""
        alter table mart_listing_management_current
            add column if not exists strike_price_amount numeric(18, 4),
            add column if not exists strike_price_currency_code varchar(3),
            add column if not exists fulfillment_type varchar(64),
            add column if not exists fulfillment_type_name varchar(128)
    """))

    bind.execute(text("""
        alter table dim_walmart_listings
            add column if not exists strike_price_amount numeric(18, 4),
            add column if not exists strike_price_currency_code varchar(3),
            add column if not exists sale_price_amount numeric(18, 4),
            add column if not exists sale_price_currency_code varchar(3)
    """))

    bind.execute(text("""
        update mart_listing_management_current m
        set
            strike_price_amount = coalesce(
                m.strike_price_amount,
                d.strike_price_amount,
                d.price_amount
            ),
            strike_price_currency_code = coalesce(
                m.strike_price_currency_code,
                d.strike_price_currency_code,
                d.price_currency_code
            ),
            sale_price_amount = coalesce(
                m.sale_price_amount,
                d.sale_price_amount,
                d.price_amount
            ),
            sale_price_currency_code = coalesce(
                m.sale_price_currency_code,
                d.sale_price_currency_code,
                d.price_currency_code
            ),
            fulfillment_type = coalesce(m.fulfillment_type, d.fulfillment_type),
            fulfillment_type_name = coalesce(
                m.fulfillment_type_name,
                d.fulfillment_type_name,
                d.fulfillment_type
            ),
            updated_at = now()
        from dim_walmart_listings d
        where d.source_account_ref = m.source_account_ref
          and d.store_id = m.store_id
          and d.item_id = m.item_id
    """))


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(text("""
        alter table mart_listing_management_current
            drop column if exists fulfillment_type_name,
            drop column if exists fulfillment_type
    """))

    bind.execute(text("""
        alter table dim_walmart_listings
            drop column if exists sale_price_currency_code,
            drop column if exists sale_price_amount,
            drop column if exists strike_price_currency_code,
            drop column if exists strike_price_amount
    """))
