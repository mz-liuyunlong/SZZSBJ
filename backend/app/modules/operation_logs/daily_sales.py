"""Read operation logs for a page of authorized Daily Sales MART rows.

This read-only enrichment never recalculates revenue, refunds or LPDS profit.
It skips missing formal tables while deployment/migration is staged.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.operation_logs.access import LogAccess, owns_sku_sql

if TYPE_CHECKING:
    from app.modules.data_pages.models import DailySalesItemDayMart

DailyKey = tuple[date, str, str, str, str]


def load_daily_sales_log_summaries(
    session: Session,
    rows: Sequence[DailySalesItemDayMart],
    access: LogAccess | None = None,
) -> dict[DailyKey, dict[str, object]]:
    if not rows or access is None:
        return {}

    present = session.execute(
        text("""
            select
                to_regclass('public.ops_system_operation_events') is not null,
                to_regclass('public.ops_manual_operation_logs') is not null
        """)
    ).one()
    if not all(present):
        return {}

    keys = json.dumps(
        [
            {
                "day": row.business_date_la.isoformat(),
                "account": row.source_account_ref,
                "store": row.store_id,
                "item": row.item_id,
                "msku": row.msku or "",
                "owner": row.owner_ref or "",
            }
            for row in rows
        ],
        ensure_ascii=False,
    )

    result = session.execute(
        text(f"""
        with selected as (
            select x.day::date as day, x.account, x.store, x.item, x.msku, x.owner
            from jsonb_to_recordset(cast(:keys as jsonb))
                as x(day text, account text, store text, item text, msku text, owner text)
        )
        select
            s.day, s.account, s.store, s.item, s.msku,
            coalesce(ev.event_text, '') as system_operation_log,
            coalesce(ev.highlight, false) as system_highlight,
            coalesce(man.log_content, '') as operation_log,
            coalesce(man.revision, 0) as revision,
            coalesce(man.status, 'draft') as status
        from selected s
        left join lateral (
            select string_agg(e.log_content, chr(10) order by e.legacy_id) as event_text,
                   bool_or(e.highlight) as highlight
            from ops_system_operation_events e
            where e.source_account_ref = s.account and e.event_date = s.day
              and e.store_id = s.store and e.item_id = s.item
              and e.msku = s.msku
              and (:is_admin or exists (
                  select 1 from mart_daily_sales_item_day d
                  where d.source_account_ref = s.account and d.store_id = s.store
                    and d.item_id = s.item and coalesce(d.msku, '') = s.msku
                    and d.business_date_la = s.day and {owns_sku_sql("d")}
              ))
        ) ev on true
        left join lateral (
            select m.log_content, m.revision, m.status
            from ops_manual_operation_logs m
            where m.source_account_ref = s.account and m.log_date = s.day
              and m.store_id = s.store and m.item_id = s.item
              and m.msku = s.msku
              and (:is_admin or m.created_by_user_id = :user_id
                   or (m.source_kind = 'legacy' and exists (
                      select 1 from mart_daily_sales_item_day d
                      where d.source_account_ref = s.account and d.store_id = s.store
                        and d.item_id = s.item and coalesce(d.msku, '') = s.msku
                        and d.business_date_la = s.day and {owns_sku_sql("d")}
                   )))
            order by (m.source_kind = 'manual') desc, m.id desc
            limit 1
        ) man on true
        """),
        {
            "keys": keys,
            "is_admin": access.is_admin,
            "user_id": access.user_id,
        },
    ).mappings()

    return {(r["day"], r["account"], r["store"], r["item"], r["msku"]): dict(r) for r in result}
