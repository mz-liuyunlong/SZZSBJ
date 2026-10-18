"""Read-only preflight: inspect actual DB tables and Alembic version.

This script never executes DDL/DML or prints sensitive record payloads.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_database_url


def main() -> None:
    names = (
        "business_rule_operation_logs",
        "legacy_mirror.event_ops_action_log",
        "legacy_mirror.biz_product_operation_log",
        "ops_system_operation_events",
        "ops_manual_operation_logs",
        "ops_operation_log_links",
        "ops_lingxing_owner_user_mappings",
        "ops_lingxing_owner_mapping_audit",
        "dwd_lingxing_sku_product_info_current",
    )
    engine = create_engine(get_database_url())
    with engine.connect() as connection:
        connection.execute(text("set transaction read only"))
        for name in names:
            present = connection.scalar(
                text("select to_regclass(:name) is not null"), {"name": name}
            )
            print(f"{name}: {'exists' if present else 'missing'}")
        if connection.scalar(text("select to_regclass('public.alembic_version') is not null")):
            version = connection.scalar(text("select version_num from alembic_version"))
            print("alembic_version:", version)
        else:
            print("alembic_version: missing")
        required = (
            "public.ops_lingxing_owner_user_mappings",
            "public.dwd_lingxing_sku_product_info_current",
            "public.app_users",
        )
        if all(
            connection.scalar(text("select to_regclass(:name) is not null"), {"name": name})
            for name in required
        ):
            counts = connection.execute(text("""
                with owners as (
                    select p.source_account_ref, nullif(btrim(p.owner_uid), '') as uid,
                           count(distinct p.owner_uid) over (
                             partition by p.source_account_ref, p.lingxing_sku_code
                           ) as uid_variants
                    from dwd_lingxing_sku_product_info_current p
                    where p.lingxing_sku_code is not null
                )
                select
                    count(*) filter (where o.uid is null) as missing_uid,
                    count(*) filter (where o.uid is not null and m.id is null) as unmapped_uid,
                    count(*) filter (where o.uid_variants > 1) as conflicting_sku_uid,
                    count(*) filter (
                        where m.id is not null and u.id is null
                    ) as stale_user_mapping,
                    count(*) filter (
                        where m.id is not null and u.is_active <> 1
                    ) as inactive_user_mapping
                from owners o
                left join ops_lingxing_owner_user_mappings m
                  on m.source_account_ref = o.source_account_ref and m.owner_uid = o.uid
                left join app_users u on u.id = m.app_user_id
            """)).mappings().one()
            for key, value in counts.items():
                print("owner_mapping_" + key + ":", int(value or 0))
        else:
            print("owner_mapping_audit: skipped (required tables missing)")
        connection.rollback()


if __name__ == "__main__":
    main()
