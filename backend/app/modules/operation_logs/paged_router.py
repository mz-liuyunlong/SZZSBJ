"""Paginated operation log listing with server-side ownership enforcement."""
from __future__ import annotations

from app.core.permissions import has_permission
from app.modules.data_pages.field_access import (
    ORDER_PROFIT_GROSS_PROFIT_PERMISSION,
)

from json import dumps

from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, success_response
from app.core.auth import Principal
from app.core.permissions import require_any_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.operation_logs.access import LogAccess, owns_sku_sql, require_log_access

router = APIRouter()

_SQL = f"""
with current_keys as (
  select l.source_account_ref, l.store_id, l.store_name, l.item_id,
         coalesce(l.msku, '') as msku, coalesce(l.local_sku, '') as sku,
         coalesce(l.title, '') as title, coalesce(l.owner_ref, '') as owner,
         l.sale_price_amount as price, dates.day::date as log_date
  from mart_listing_management_current l
  cross join generate_series(
    cast(:start as date), cast(:end as date), interval '1 day'
  ) dates(day)
  where l.source_account_ref = any(:accounts)
    and (:is_admin or {owns_sku_sql('l')} or exists (
      select 1 from ops_manual_operation_logs own
      where own.source_account_ref = l.source_account_ref
        and own.store_id = l.store_id and own.item_id = l.item_id
        and own.msku = coalesce(l.msku, '')
        and own.log_date = dates.day::date
        and own.created_by_user_id = :user_id
    ))
), history_keys as (
  select source_account_ref, store_id, item_id, msku, event_date as log_date
  from ops_system_operation_events
  where source_account_ref = any(:accounts)
    and event_date between :start and :end
  union
  select source_account_ref, store_id, item_id, msku, log_date
  from ops_manual_operation_logs
  where source_account_ref = any(:accounts)
    and log_date between :start and :end
), archived_keys as (
  select h.source_account_ref, h.store_id, h.store_id as store_name,
         h.item_id, h.msku, ''::text as sku, ''::text as title,
         ''::text as owner, null::numeric as price, h.log_date
  from history_keys h
  where not exists (
    select 1 from mart_listing_management_current l
    where l.source_account_ref = h.source_account_ref
      and l.store_id = h.store_id and l.item_id = h.item_id
      and coalesce(l.msku, '') = h.msku
  )
    and (:is_admin or exists (
      select 1 from mart_daily_sales_item_day d
      where d.source_account_ref = h.source_account_ref
        and d.store_id = h.store_id and d.item_id = h.item_id
        and coalesce(d.msku, '') = h.msku
        and d.business_date_la = h.log_date
        and {owns_sku_sql('d')}
    ) or exists (
      select 1 from ops_manual_operation_logs own
      where own.source_account_ref = h.source_account_ref
        and own.store_id = h.store_id and own.item_id = h.item_id
        and own.msku = h.msku and own.log_date = h.log_date
        and own.created_by_user_id = :user_id
    ))
), identities as (
  select * from current_keys
  union all
  select * from archived_keys
), annotated as (
  select i.*, coalesce(m.log_content, '') as manual_content,
         coalesce(m.revision, 0) as revision,
         coalesce(m.work_type, '其他') as work_type,
         coalesce(m.work_types_json, '[]'::jsonb) as work_types_json,
         m.observe_days, coalesce(m.status, 'draft') as edit_status
  from identities i
  left join lateral (
    select log_content, revision, work_type, work_types_json,
           observe_days, status
    from ops_manual_operation_logs m
    where m.source_account_ref = i.source_account_ref
      and m.created_by_user_id = :user_id
      and m.source_kind = 'manual'
      and m.log_date = i.log_date
      and m.store_id = i.store_id and m.item_id = i.item_id
      and m.msku = i.msku
    order by m.id desc limit 1
  ) m on true
), filtered as (
  select a.* from annotated a
  -- OPLOG_OWNER_SCOPED_ROWS_V1
  -- The list is scoped to the authenticated user's verified SKU owner mapping.
  -- Admin access does not automatically expand the personal work list.
  where (
    exists (
      select 1
      from mart_listing_management_current l
      where l.source_account_ref = a.source_account_ref
        and l.store_id = a.store_id
        and l.item_id = a.item_id
        and coalesce(l.msku, '') = a.msku
        and {owns_sku_sql("l")}
    )
    or (
      not exists (
        select 1
        from mart_listing_management_current current_l
        where current_l.source_account_ref = a.source_account_ref
          and current_l.store_id = a.store_id
          and current_l.item_id = a.item_id
          and coalesce(current_l.msku, '') = a.msku
      )
      and exists (
        select 1
        from mart_daily_sales_item_day d
        where d.source_account_ref = a.source_account_ref
          and d.store_id = a.store_id
          and d.item_id = a.item_id
          and coalesce(d.msku, '') = a.msku
          and d.business_date_la = a.log_date
          and {owns_sku_sql("d")}
      )
    )
  )
    and (:owners_empty or a.owner = any(:owners))
    -- OPLOG_DATED_WFS_SNAPSHOT_FILTER_V2
    -- Archive state remains the current Listing archive state.
    -- Historical WFS stock must come from its exact LA snapshot date.
    and exists (
        select 1
        from mart_listing_management_current listing_visible
        where listing_visible.source_account_ref = a.source_account_ref
          and listing_visible.store_id = a.store_id
          and listing_visible.item_id = a.item_id
          and coalesce(listing_visible.msku, '') = a.msku
          and not exists (
              select 1
              from listing_archive_states archive_state
              where archive_state.listing_id = listing_visible.id
                and archive_state.is_archived is true
          )
    )
    and not exists (
        select 1
        from fact_walmart_listing_inventory_daily inventory_day
        where inventory_day.source_account_ref = a.source_account_ref
          and inventory_day.store_id = a.store_id
          and inventory_day.item_id = a.item_id
          and inventory_day.snapshot_date_la = a.log_date
          and inventory_day.wfs_available_quantity = 0
    )
    and (:stores_empty or a.store_name = any(:stores))
    and (:works_empty or a.work_type = any(:works))
    and (
      :system_filter = 'all'
      or (:system_filter = 'has' and exists (
        select 1 from ops_system_operation_events e
        where e.source_account_ref = a.source_account_ref
          and e.event_date = a.log_date
          and e.store_id = a.store_id and e.item_id = a.item_id
          and e.msku = a.msku
      ))
      or (:system_filter = 'missing' and not exists (
        select 1 from ops_system_operation_events e
        where e.source_account_ref = a.source_account_ref
          and e.event_date = a.log_date
          and e.store_id = a.store_id and e.item_id = a.item_id
          and e.msku = a.msku
      ))
    )
    and (:keyword_empty or (case :search_field
      when 'productId' then a.item_id
      when 'sku' then a.sku
      when 'productName' then a.title
      when 'store' then a.store_name
      when 'owner' then a.owner
      when 'date' then a.log_date::text
      else a.item_id end) ilike :keyword)
    and (:batch_empty or exists (
      select 1 from unnest(cast(:batch_values as text[])) b(value)
      where a.item_id ilike '%' || b.value || '%'
         or a.sku ilike '%' || b.value || '%'
         or a.title ilike '%' || b.value || '%'
         or a.store_name ilike '%' || b.value || '%'
         or a.owner ilike '%' || b.value || '%'
         or a.log_date::text ilike '%' || b.value || '%'
    ))
)
"""

@router.get("/rows/query")
def query_rows(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[
        Principal,
        Depends(require_any_permission(
            "page:operations:log:view",
            "page:sales:daily-sales:view",
        )),
    ],
    accounts: Annotated[
        frozenset[str], Depends(require_source_account_scope)
    ],
    access: Annotated[LogAccess, Depends(require_log_access)],
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    owner: list[str] | None = Query(None),
    store: list[str] | None = Query(None),
    work_type: list[str] | None = Query(None),
    system_log: Literal["all", "has", "missing"] = "all",
    search_field: Literal[
        "productId", "sku", "productName", "store", "owner", "date"
    ] = "productId",
    keyword: str = "",
    batch_value: list[str] | None = Query(None),
    include_events: bool = False,
):
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    start, end = start_date or today, end_date or today

    if start > end or (end - start).days > 30 or end > today:
        raise ApiError(
            code="OPERATION_LOG_DATE_RANGE_INVALID", status_code=422
        )

    allowed = list(access.accounts.intersection(accounts))
    if not allowed:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    if batch_value and len(batch_value) > 1000:
        raise ApiError(
            code="OPERATION_LOG_BATCH_SEARCH_TOO_LARGE",
            status_code=422,
        )

    params = {
        "accounts": allowed,
        "is_admin": access.is_admin,
        "user_id": access.user_id,
        "start": start,
        "end": end,
        "owners": owner or [],
        "stores": store or [],
        "works": work_type or [],
        "owners_empty": not bool(owner),
        "stores_empty": not bool(store),
        "works_empty": not bool(work_type),
        "system_filter": system_log,
        "keyword_empty": not bool(keyword.strip()),
        "search_field": search_field,
        "keyword": "%" + keyword.strip() + "%",
        "batch_empty": not bool(batch_value),
        "batch_values": [
            value.strip() for value in (batch_value or [])
            if value.strip()
        ],
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }

    results = session.execute(
        text(_SQL + """
        select f.*, count(*) over() as page_total,
          (select count(*) from ops_system_operation_events e
           where e.source_account_ref = f.source_account_ref
             and e.event_date = f.log_date
             and e.store_id = f.store_id and e.item_id = f.item_id
             and e.msku = f.msku) as system_count,
          (select count(*) from ops_manual_operation_logs m
           where m.source_account_ref = f.source_account_ref
             and m.log_date = f.log_date
             and m.store_id = f.store_id and m.item_id = f.item_id
             and m.msku = f.msku
             and (:is_admin or m.created_by_user_id = :user_id)
          ) as manual_count,
          (select k.entry_url from ops_operation_log_links k
           where k.source_account_ref = f.source_account_ref
             and k.store_id = f.store_id and k.item_id = f.item_id
             and k.entry_type = 'keyword') as keyword_url,
          (select k.entry_url from ops_operation_log_links k
           where k.source_account_ref = f.source_account_ref
             and k.store_id = f.store_id and k.item_id = f.item_id
             and k.entry_type = 'ad') as ad_url
        from filtered f
        order by f.log_date desc, f.source_account_ref,
                 f.store_id, f.item_id, f.msku
        limit :limit offset :offset
        """),
        params,
    ).mappings().all()

    # One query returns the selected page and its filtered total.
    # An empty page still requires a count query for correct pagination.
    total = (
        int(results[0]["page_total"])
        if results
        else int(
            session.scalar(
                text(_SQL + "select count(*) from filtered"), params
            ) or 0
        )
    )

    # LEGACY_HISTORY_PAGE_OVERLAY_V2
    # History is read-only, never copied into editable manualLog.
    history_by_key = {}

    if results:
        keys = [
            {
                "day": r["log_date"].isoformat(),
                "account": r["source_account_ref"],
                "store": r["store_id"],
                "item": r["item_id"],
                "msku": r["msku"],
            }
            for r in results
        ]

        historic = session.execute(
            text(f"""
                with selected as (
                    select x.day::date as day,
                           x.account, x.store, x.item, x.msku
                    from jsonb_to_recordset(cast(:keys as jsonb))
                    as x(
                        day text,
                        account text,
                        store text,
                        item text,
                        msku text
                    )
                ),
                authorized as (
                    select s.*
                    from selected s
                    where :is_admin
                       or exists (
                           select 1
                           from mart_listing_management_current l
                           where l.source_account_ref = s.account
                             and l.store_id = s.store
                             and l.item_id = s.item
                             and coalesce(l.msku, '') = s.msku
                             and {owns_sku_sql("l")}
                       )
                       or exists (
                           select 1
                           from mart_daily_sales_item_day d
                           where d.source_account_ref = s.account
                             and d.store_id = s.store
                             and d.item_id = s.item
                             and coalesce(d.msku, '') = s.msku
                             and d.business_date_la = s.day
                             and {owns_sku_sql("d")}
                       )
                )
                select
                    s.day, s.account, s.store, s.item, s.msku,
                    coalesce((
                        select m.log_content
                        from ops_manual_operation_logs m
                        where m.source_kind = 'legacy'
                          and m.source_account_ref = s.account
                          and m.log_date = s.day
                          and m.store_id = s.store
                          and m.item_id = s.item
                          and m.msku = s.msku
                          and nullif(btrim(m.log_content), '') is not null
                        order by m.id desc
                        limit 1
                    ), '') as legacy_content,
                    (
                        select count(*)
                        from ops_manual_operation_logs m
                        where m.source_kind = 'legacy'
                          and m.source_account_ref = s.account
                          and m.log_date = s.day
                          and m.store_id = s.store
                          and m.item_id = s.item
                          and m.msku = s.msku
                    ) as legacy_count
                from authorized s
            """),
            {
                "keys": dumps(keys, ensure_ascii=False),
                "is_admin": access.is_admin,
                "user_id": access.user_id,
            },
        ).mappings().all()

        history_by_key = {
            (
                h["day"], h["account"], h["store"],
                h["item"], h["msku"]
            ): {
                "content": h["legacy_content"],
                "count": int(h["legacy_count"]),
            }
            for h in historic
        }

    # OPLOG_PAGE_METRICS_V3
    # The seven-day window ends on each row's LA business day.
    # WFS inventory comes from the current listing snapshot.
    profit_allowed = has_permission(
        _,
        ORDER_PROFIT_GROSS_PROFIT_PERMISSION,
    )

    metric_keys = [
        {
            "day": r["log_date"].isoformat(),
            "account": r["source_account_ref"],
            "store": r["store_id"],
            "item": r["item_id"],
            "msku": r["msku"],
        }
        for r in results
    ]

    metrics_by_key = {}

    if metric_keys:
        metrics = session.execute(
            text("""
                WITH selected AS (
                    SELECT
                        x.day::date AS day,
                        x.account,
                        x.store,
                        x.item,
                        x.msku
                    FROM jsonb_to_recordset(
                        CAST(:metric_keys AS jsonb)
                    ) AS x(
                        day text,
                        account text,
                        store text,
                        item text,
                        msku text
                    )
                )
                SELECT
                    s.day,
                    s.account,
                    s.store,
                    s.item,
                    s.msku,
                    CASE
                        WHEN :profit_allowed
                         AND p.row_count > 0
                         AND p.missing_profit = 0
                         AND p.incomplete_cost = 0
                         AND p.non_usd_profit = 0
                        THEN p.profit_total
                        ELSE NULL
                    END AS profit_7d,
                    inventory_day.wfs_available_quantity AS wfs_available
                FROM selected s
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS row_count,
                        COUNT(*) FILTER (
                            WHERE d.gross_profit_amount IS NULL
                        ) AS missing_profit,
                        COUNT(*) FILTER (
                            WHERE d.cost_status <> 'complete'
                        ) AS incomplete_cost,
                        COUNT(*) FILTER (
                            WHERE COALESCE(
                                d.gross_profit_currency_code,
                                'USD'
                            ) <> 'USD'
                        ) AS non_usd_profit,
                        SUM(d.gross_profit_amount) AS profit_total
                    FROM mart_daily_sales_item_day d
                    WHERE d.source_account_ref = s.account
                      AND d.store_id = s.store
                      AND d.item_id = s.item
                      AND COALESCE(d.msku, '') = s.msku
                      AND d.business_date_la
                          BETWEEN (s.day - 6) AND s.day
                ) p ON TRUE
                LEFT JOIN fact_walmart_listing_inventory_daily inventory_day
                  ON inventory_day.source_account_ref = s.account
                 AND inventory_day.store_id = s.store
                 AND inventory_day.item_id = s.item
                 AND inventory_day.snapshot_date_la = s.day
            """),
            {
                "metric_keys": dumps(
                    metric_keys, ensure_ascii=False
                ),
                "profit_allowed": profit_allowed,
            },
        ).mappings().all()

        metrics_by_key = {
            (
                m["day"], m["account"], m["store"],
                m["item"], m["msku"]
            ): m
            for m in metrics
        }

    # OPLOG_VERIFIED_OWNER_DISPLAY_V1
    # Resolve display names through the authenticated UID mapping.
    # Never grant access by comparing a person's name.
    owner_keys = sorted({
        (str(r["source_account_ref"]), str(r["sku"]))
        for r in results
        if r["source_account_ref"] and r["sku"]
    })

    owner_names = {}

    if owner_keys:
        owner_rows = session.execute(
            text("""
                WITH identities AS (
                    SELECT DISTINCT
                        k.account,
                        k.sku
                    FROM jsonb_to_recordset(
                        CAST(:owner_keys AS jsonb)
                    ) AS k(account text, sku text)
                )
                SELECT
                    k.account,
                    k.sku,
                    CASE
                        WHEN COUNT(DISTINCT NULLIF(
                            btrim(pi.owner_uid), ''
                        )) = 1
                         AND COUNT(DISTINCT NULLIF(
                            btrim(pi.owner_name), ''
                        )) <= 1
                        THEN MAX(NULLIF(
                            btrim(pi.owner_name), ''
                        ))
                        ELSE NULL
                    END AS owner_name
                FROM identities k
                JOIN dwd_lingxing_sku_product_info_current pi
                  ON pi.source_account_ref = k.account
                 AND pi.lingxing_sku_code = k.sku
                JOIN ops_lingxing_owner_user_mappings m
                  ON m.source_account_ref = pi.source_account_ref
                 AND m.owner_uid = btrim(pi.owner_uid)
                 AND m.app_user_id = :user_id
                GROUP BY k.account, k.sku
            """),
            {
                "owner_keys": dumps([
                    {"account": account, "sku": sku}
                    for account, sku in owner_keys
                ], ensure_ascii=False),
                "user_id": access.user_id,
            },
        ).mappings().all()

        owner_names = {
            (str(row["account"]), str(row["sku"])):
                str(row["owner_name"]).strip()
            for row in owner_rows
            if row["owner_name"]
        }

    rows = []
    revisions = {}

    for r in results:
        row_id = "|".join((
            r["log_date"].isoformat(),
            r["source_account_ref"],
            r["store_id"],
            r["item_id"],
            r["msku"],
        ))

        revisions[row_id] = int(r["revision"])

        metric = metrics_by_key.get(
            (
                r["log_date"],
                r["source_account_ref"],
                r["store_id"],
                r["item_id"],
                r["msku"],
            ),
            {},
        )


        legacy = history_by_key.get(
            (
                r["log_date"],
                r["source_account_ref"],
                r["store_id"],
                r["item_id"],
                r["msku"],
            ),
            {"content": "", "count": 0},
        )

        rows.append({
            "id": row_id,
            "date": r["log_date"].isoformat(),
            "sourceAccountRef": r["source_account_ref"],
            "storeId": r["store_id"],
            "msku": r["msku"],
            "productId": r["item_id"],
            "sku": r["sku"],
            "productName": r["title"],
            "store": r["store_name"],
            "owner": (
                owner_names.get((
                    str(r["source_account_ref"]),
                    str(r["sku"]),
                ))
                or access.display_name
            ),
            "workType": r["work_type"],
            "workTypes": list(r["work_types_json"] or []),
            "observeDays": r["observe_days"],
            "conversionRate": None,
            "salePrice": float(r["price"]) if r["price"] is not None else None,
            "keywordEntryStatus": "ok" if r["keyword_url"] else "missing",
            "keywordUrl": r["keyword_url"],
            "adEntryStatus": "ok" if r["ad_url"] else "missing",
            "adUrl": r["ad_url"],
            "systemLogCount": int(r["system_count"]),
            "profit7d": (
                float(metric["profit_7d"])
                if metric.get("profit_7d") is not None
                else None
            ),
            "wfsAvailableInventory": (
                float(metric["wfs_available"])
                if metric.get("wfs_available") is not None
                else None
            ),
            "manualLog": r["manual_content"],
            "legacyManualLog": legacy["content"],
            "legacyManualCount": legacy["count"],
            "manualEntryCount": (
                int(r["manual_count"])
                + (0 if access.is_admin else legacy["count"])
            ),
            "status": (
                "已保存"
                if (
                    r["edit_status"] == "submitted"
                    or (
                        not r["manual_content"]
                        and bool(legacy["content"])
                    )
                )
                else "草稿" if r["manual_content"]
                else "缺记录"
            ),
        })

    events = []

    if include_events and any(
        int(r["system_count"]) > 0 for r in results
    ):
        event_targets = [
            r for r in results if int(r["system_count"]) > 0
        ]
        conditions = []

        for i, r in enumerate(event_targets):
            conditions.append(
                f"(e.source_account_ref=:ea{i} "
                f"and e.event_date=:ed{i} "
                f"and e.store_id=:es{i} "
                f"and e.item_id=:ei{i} "
                f"and e.msku=:em{i})"
            )
            params.update({
                f"ea{i}": r["source_account_ref"],
                f"ed{i}": r["log_date"],
                f"es{i}": r["store_id"],
                f"ei{i}": r["item_id"],
                f"em{i}": r["msku"],
            })

        records = session.execute(
            text("""
            select e.legacy_id, e.source_account_ref,
                   e.event_date, e.store_id, e.item_id, e.msku,
                   e.action_type, e.object_name, e.log_content
            from ops_system_operation_events e
            where """ + " or ".join(conditions) + """
            order by e.event_date desc, e.legacy_id
            limit 20001
            """),
            params,
        ).mappings().all()

        if len(records) > 20000:
            raise ApiError(
                code="OPERATION_LOG_EVENTS_TOO_LARGE",
                status_code=422,
            )

        events = [
            {
                "id": str(e["legacy_id"]),
                "time": e["event_date"].isoformat(),
                "date": e["event_date"].isoformat(),
                "sourceAccountRef": e["source_account_ref"],
                "storeId": e["store_id"],
                "msku": e["msku"],
                "productId": e["item_id"],
                "owner": "未确认",
                "type": e["action_type"],
                "object": e["object_name"],
                "before": "",
                "after": "",
                "source": "领星",
                "detail": e["log_content"],
            }
            for e in records
        ]

    return success_response(
        request,
        data={
            "rows": rows,
            "revisions": revisions,
            "systemRecords": events,
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
        meta=None,
    )
