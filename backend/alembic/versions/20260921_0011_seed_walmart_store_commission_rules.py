# ruff: noqa: E501
"""seed walmart store commission rules

Revision ID: 20260921_0011_store_commission_rules
Revises: 20260921_0010_add_listing_custom_tags
Create Date: 2026-09-21 12:49:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260921_0011_store_commission_rules"
down_revision: str | Sequence[str] | None = "20260921_0010_add_listing_custom_tags"
branch_labels = None
depends_on = None

RULE_VERSION = "store_commission_1200bp_19000101_initial"
REQUEST_ID = "owner-approved-store-commission-1200bp-all-dates-20260921"
STORE_ID_SQL = "('110687427724845056','110687428693128704')"


def upgrade() -> None:
    op.execute(
        f"""
        update ref_store_commission_rule_versions
        set is_active=false, updated_at=now()
        where platform_code='walmart'
          and store_id in {STORE_ID_SQL}
          and is_active=true
        """
    )

    op.execute(
        f"""
        with affected as (
            select distinct source_account_ref, store_id
            from dim_lingxing_stores
            where store_id in {STORE_ID_SQL}

            union

            select distinct source_account_ref, store_id
            from dim_walmart_listings
            where store_id in {STORE_ID_SQL}

            union

            select distinct source_account_ref, store_id
            from fact_walmart_sales_item_daily
            where store_id in {STORE_ID_SQL}

            union

            select distinct source_account_ref, store_id
            from ref_store_commission_rule_versions
            where platform_code='walmart'
              and store_id in {STORE_ID_SQL}
        )
        insert into ref_store_commission_rule_versions (
            id,
            source_account_ref,
            platform_code,
            store_id,
            commission_rate,
            effective_from,
            effective_to,
            is_active,
            rule_version,
            change_reason,
            approved_by,
            approved_at,
            request_id,
            created_at,
            updated_at
        )
        select
            gen_random_uuid(),
            affected.source_account_ref,
            'walmart',
            affected.store_id,
            0.12,
            date '1900-01-01',
            null,
            true,
            '{RULE_VERSION}',
            'Initial configurable commission rule: 12 percent for designated Walmart stores, all dates',
            'owner',
            now(),
            '{REQUEST_ID}',
            now(),
            now()
        from affected
        on conflict (source_account_ref, platform_code, store_id, rule_version)
        do update set
            commission_rate=excluded.commission_rate,
            effective_from=excluded.effective_from,
            effective_to=excluded.effective_to,
            is_active=excluded.is_active,
            change_reason=excluded.change_reason,
            approved_by=excluded.approved_by,
            approved_at=excluded.approved_at,
            request_id=excluded.request_id,
            updated_at=now()
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        delete from ref_store_commission_rule_versions
        where platform_code='walmart'
          and store_id in {STORE_ID_SQL}
          and rule_version='{RULE_VERSION}'
          and request_id='{REQUEST_ID}'
        """
    )
