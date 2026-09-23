# ruff: noqa: E501
"""repair after sales refund items schema

Revision ID: 20260922_0016_after_sales_refund_items_schema_repair
Revises: 20260922_0015_add_after_sales_refund_loss_date
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260922_0016_after_sales_refund_items_schema_repair"
down_revision: str | None = "20260922_0015_add_after_sales_refund_loss_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add columns defensively because 0014 was created while importer was still evolving.
    op.execute("alter table after_sales_refund_items add column if not exists raw_site_code text")
    op.execute(
        "alter table after_sales_refund_items add column if not exists return_order_date timestamp with time zone"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists refund_loss_effective boolean not null default false"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists refund_loss_date date"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists listing_image_url text"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists quantity_display_raw text"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists return_reason_category text"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists daily_storage_fee numeric(18, 6)"
    )
    op.execute(
        "alter table after_sales_refund_items add column if not exists missing_cost_codes jsonb not null default '[]'::jsonb"
    )

    op.execute(
        """
        create unique index if not exists ux_after_sales_refund_items_source_order_item
        on after_sales_refund_items (
            source_account_ref,
            platform_code,
            return_order_id,
            item_index
        )
        """
    )

    op.execute(
        """
        create index if not exists ix_after_sales_refund_items_loss_date
        on after_sales_refund_items (
            source_account_ref,
            platform_code,
            refund_loss_date
        )
        """
    )

    op.execute(
        """
        create index if not exists ix_after_sales_refund_items_store_msku
        on after_sales_refund_items (
            source_account_ref,
            platform_code,
            store_id,
            msku
        )
        """
    )

    op.execute(
        """
        create index if not exists ix_after_sales_refund_items_local_sku
        on after_sales_refund_items (
            source_account_ref,
            platform_code,
            local_sku
        )
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_after_sales_refund_items_local_sku")
    op.execute("drop index if exists ix_after_sales_refund_items_store_msku")
    op.execute("drop index if exists ix_after_sales_refund_items_loss_date")
    op.execute("drop index if exists ux_after_sales_refund_items_source_order_item")
    op.execute("alter table after_sales_refund_items drop column if exists missing_cost_codes")
    op.execute("alter table after_sales_refund_items drop column if exists daily_storage_fee")
    op.execute("alter table after_sales_refund_items drop column if exists return_reason_category")
    op.execute("alter table after_sales_refund_items drop column if exists quantity_display_raw")
    op.execute("alter table after_sales_refund_items drop column if exists listing_image_url")
    op.execute("alter table after_sales_refund_items drop column if exists refund_loss_date")
    op.execute("alter table after_sales_refund_items drop column if exists refund_loss_effective")
    op.execute("alter table after_sales_refund_items drop column if exists return_order_date")
    op.execute("alter table after_sales_refund_items drop column if exists raw_site_code")
