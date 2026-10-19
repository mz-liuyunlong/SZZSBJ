"""Current listing-based operation log grid, backed only by formal new-system logs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_any_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.operation_logs.access import LogAccess, owns_sku_sql, require_log_access

router = APIRouter(prefix="/api/operations/logs", tags=["Operation Logs"])
db_dep = Annotated[Session, Depends(get_db_session)]
scope_dep = Annotated[frozenset[str], Depends(require_source_account_scope)]
access_dep = Annotated[LogAccess, Depends(require_log_access)]
read_dep = Annotated[
    Principal,
    Depends(require_any_permission("page:operations:log:view", "page:sales:daily-sales:view")),
]
errors: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


@router.get("/rows", response_model=SuccessEnvelope[dict[str, Any], Any], responses=errors)
def get_rows(
    request: Request,
    session: db_dep,
    _: read_dep,
    accounts: scope_dep,
    access: access_dep,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SuccessEnvelope[dict[str, Any], Any]:
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    start = start_date or today
    end = end_date or today
    if start > end or (end - start).days > 30 or end > today:
        raise ApiError(code="OPERATION_LOG_DATE_RANGE_INVALID", status_code=422)
    if not accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    base = dict(
        accounts=list(access.accounts.intersection(accounts)),
        start=start,
        end=end,
        is_admin=access.is_admin,
        user_id=access.user_id,
    )
    result = (
        session.execute(
            text(f"""
        with identities as (
            select l.source_account_ref, l.store_id, l.store_name, l.item_id,
                   coalesce(l.msku, '') as msku,
                   coalesce(l.local_sku, '') as sku, coalesce(l.title, '') as title,
                   coalesce(l.owner_ref, '') as owner,
                   l.sale_price_amount as price,
                   d.day::date as log_date
            from mart_listing_management_current l
            cross join generate_series(
                cast(:start as date), cast(:end as date), interval '1 day'
            ) as d(day)
            where l.source_account_ref = any(:accounts)
              and (:is_admin or {owns_sku_sql("l")}
                   or exists (
                     select 1 from ops_manual_operation_logs own
                     where own.source_account_ref = l.source_account_ref
                       and own.store_id = l.store_id and own.item_id = l.item_id
                       and own.msku = coalesce(l.msku, '')
                       and own.log_date = d.day::date and own.created_by_user_id = :user_id
                   ))
            order by d.day desc, l.store_id, l.item_id
            limit 5001
        )
        select i.*, coalesce(m.log_content, '') as manual_content,
               coalesce(m.revision, 0) as revision,
               coalesce(m.work_type, '其他') as work_type,
               coalesce(m.work_types_json, '[]'::jsonb) as work_types_json,
               m.observe_days as observe_days,
               coalesce(m.status, 'draft') as edit_status,
               (select count(*) from ops_manual_operation_logs other
                where other.source_account_ref = i.source_account_ref
                  and other.log_date = i.log_date and other.store_id = i.store_id
                  and other.item_id = i.item_id and other.msku = i.msku
                  and (:is_admin or other.created_by_user_id = :user_id)) as manual_count,
               (select count(*) from ops_system_operation_events e
                where e.source_account_ref = i.source_account_ref
                  and e.event_date = i.log_date and e.store_id = i.store_id
                  and e.item_id = i.item_id and e.msku = i.msku) as system_count,
               exists (
                  select 1 from ops_operation_log_links k
                  where k.source_account_ref = i.source_account_ref
                    and k.store_id = i.store_id and k.item_id = i.item_id
                    and k.entry_type = 'keyword'
               ) as keyword_link,
               (select k.entry_url from ops_operation_log_links k
                where k.source_account_ref = i.source_account_ref
                  and k.store_id = i.store_id and k.item_id = i.item_id
                  and k.entry_type = 'keyword') as keyword_url,
               exists (
                  select 1 from ops_operation_log_links k
                  where k.source_account_ref = i.source_account_ref
                    and k.store_id = i.store_id and k.item_id = i.item_id
                    and k.entry_type = 'ad'
               ) as ad_link,
               (select k.entry_url from ops_operation_log_links k
                where k.source_account_ref = i.source_account_ref
                  and k.store_id = i.store_id and k.item_id = i.item_id
                  and k.entry_type = 'ad') as ad_url
        from identities i
        left join lateral (
            select log_content, revision, work_type, work_types_json, observe_days, status
            from ops_manual_operation_logs m
            where m.source_account_ref = i.source_account_ref
              and m.created_by_user_id = :user_id
              and m.source_kind = 'manual'
              and m.log_date = i.log_date
              and m.store_id = i.store_id and m.item_id = i.item_id
              and m.msku = i.msku
            order by (m.source_kind = 'manual') desc, m.id desc
            limit 1
        ) m on true
    """),
            base,
        )
        .mappings()
        .all()
    )
    archived = (
        session.execute(
            text(f"""
        with historic_keys as (
            select source_account_ref, log_date as day, store_id, item_id, msku
            from ops_manual_operation_logs
            where source_account_ref = any(:accounts)
              and log_date between :start and :end
            union
            select source_account_ref, event_date as day, store_id, item_id, msku
            from ops_system_operation_events
            where source_account_ref = any(:accounts)
              and event_date between :start and :end
        )
        select h.source_account_ref, h.store_id,
               coalesce(l.store_name, h.store_id) as store_name,
               h.item_id, h.msku, coalesce(l.local_sku, '') as sku,
               coalesce(l.title, '') as title,
               coalesce(l.owner_ref, '') as owner,
               l.sale_price_amount as price, h.day as log_date,
               coalesce(m.log_content, '') as manual_content,
               coalesce(m.revision, 0) as revision,
               coalesce(m.work_type, '其他') as work_type,
               coalesce(m.work_types_json, '[]'::jsonb) as work_types_json,
               m.observe_days as observe_days,
               coalesce(m.status, 'draft') as edit_status,
               (select count(*) from ops_manual_operation_logs other
                where other.source_account_ref = h.source_account_ref
                  and other.log_date = h.day and other.store_id = h.store_id
                  and other.item_id = h.item_id and other.msku = h.msku
                  and (:is_admin or other.created_by_user_id = :user_id)) as manual_count,
               (select count(*) from ops_system_operation_events e
                where e.source_account_ref = h.source_account_ref
                  and e.event_date = h.day and e.store_id = h.store_id
                  and e.item_id = h.item_id and e.msku = h.msku) as system_count,
               exists (
                 select 1 from ops_operation_log_links k
                 where k.source_account_ref = h.source_account_ref
                   and k.store_id = h.store_id and k.item_id = h.item_id
                   and k.entry_type = 'keyword'
               ) as keyword_link,
               (select k.entry_url from ops_operation_log_links k
                where k.source_account_ref = h.source_account_ref
                  and k.store_id = h.store_id and k.item_id = h.item_id
                  and k.entry_type = 'keyword') as keyword_url,
               exists (
                 select 1 from ops_operation_log_links k
                 where k.source_account_ref = h.source_account_ref
                   and k.store_id = h.store_id and k.item_id = h.item_id
                   and k.entry_type = 'ad'
               ) as ad_link,
               (select k.entry_url from ops_operation_log_links k
                where k.source_account_ref = h.source_account_ref
                  and k.store_id = h.store_id and k.item_id = h.item_id
                  and k.entry_type = 'ad') as ad_url
        from historic_keys h
        left join lateral (
            select store_name, local_sku, title, owner_ref, sale_price_amount
            from mart_listing_management_current l
            where l.source_account_ref = h.source_account_ref
              and l.store_id = h.store_id and l.item_id = h.item_id
              and coalesce(l.msku, '') = h.msku
            limit 1
        ) l on true
        left join lateral (
            select log_content, revision, work_type, work_types_json, observe_days, status
            from ops_manual_operation_logs m
            where m.source_account_ref = h.source_account_ref
              and m.created_by_user_id = :user_id
              and m.source_kind = 'manual'
              and m.log_date = h.day and m.store_id = h.store_id
              and m.item_id = h.item_id and m.msku = h.msku
            order by (m.source_kind = 'manual') desc, m.id desc
            limit 1
        ) m on true
        where not exists (
            select 1 from mart_listing_management_current listed
            where listed.source_account_ref = h.source_account_ref
              and listed.store_id = h.store_id and listed.item_id = h.item_id
              and coalesce(listed.msku, '') = h.msku
        )
          and (:is_admin
               or exists (
                 select 1 from mart_daily_sales_item_day d
                 where d.source_account_ref = h.source_account_ref
                   and d.store_id = h.store_id and d.item_id = h.item_id
                   and coalesce(d.msku, '') = h.msku and d.business_date_la = h.day
                   and {owns_sku_sql("d")}
               )
               or exists (
                 select 1 from ops_manual_operation_logs own
                 where own.source_account_ref = h.source_account_ref
                   and own.store_id = h.store_id and own.item_id = h.item_id
                   and own.msku = h.msku and own.log_date = h.day
                   and own.created_by_user_id = :user_id
               ))
        order by h.day desc, h.store_id, h.item_id
        limit 5001
    """),
            base,
        )
        .mappings()
        .all()
    )
    result = list(result) + list(archived)
    if len(result) > 5000:
        raise ApiError(code="OPERATION_LOG_RESULT_TOO_LARGE", status_code=422)
    event_rows = (
        session.execute(
            text(f"""
        select e.legacy_id, e.source_account_ref, e.event_date, e.store_id,
               e.item_id, e.msku, e.action_type, e.object_name, e.log_content
        from ops_system_operation_events e
        where e.source_account_ref = any(:accounts)
          and e.event_date between :start and :end
          and (:is_admin
               or exists (
                 select 1 from mart_listing_management_current l
                 where l.source_account_ref = e.source_account_ref
                   and l.store_id = e.store_id and l.item_id = e.item_id
                   and coalesce(l.msku, '') = e.msku
                   and {owns_sku_sql("l")}
               )
               or exists (
                 select 1 from mart_daily_sales_item_day d
                 where d.source_account_ref = e.source_account_ref
                   and d.store_id = e.store_id and d.item_id = e.item_id
                   and coalesce(d.msku, '') = e.msku
                   and d.business_date_la = e.event_date
                   and {owns_sku_sql("d")}
               )
               or exists (
                 select 1 from ops_manual_operation_logs own
                 where own.source_account_ref = e.source_account_ref
                   and own.store_id = e.store_id and own.item_id = e.item_id
                   and own.msku = e.msku and own.log_date = e.event_date
                   and own.created_by_user_id = :user_id
               ))
        order by e.event_date desc, e.legacy_id
        limit 20001
    """),
            base,
        )
        .mappings()
        .all()
    )
    if len(event_rows) > 20000:
        raise ApiError(code="OPERATION_LOG_EVENTS_TOO_LARGE", status_code=422)
    system_records = [
        {
            "id": str(e["legacy_id"]),
            "time": e["event_date"].isoformat(),
            "sourceAccountRef": e["source_account_ref"],
            "date": e["event_date"].isoformat(),
            "storeId": e["store_id"],
            "productId": e["item_id"],
            "msku": e["msku"],
            "owner": "未确认",
            "type": e["action_type"],
            "object": e["object_name"],
            "before": "",
            "after": "",
            "source": "领星",
            "detail": e["log_content"],
        }
        for e in event_rows
    ]
    rows: list[dict[str, Any]] = []
    revisions: dict[str, int] = {}
    for r in result:
        row_id = "|".join(
            (
                r["log_date"].isoformat(),
                r["source_account_ref"],
                r["store_id"],
                r["item_id"],
                r["msku"],
            )
        )
        revisions[row_id] = int(r["revision"])
        rows.append(
            {
                "id": row_id,
                "date": r["log_date"].isoformat(),
                "sourceAccountRef": r["source_account_ref"],
                "storeId": r["store_id"],
                "msku": r["msku"],
                "productId": r["item_id"],
                "sku": r["sku"],
                "productName": r["title"],
                "store": r["store_name"] or r["store_id"],
                "owner": r["owner"],
                "workType": r["work_type"],
                "workTypes": list(r["work_types_json"] or []),
                "observeDays": r["observe_days"],
                "conversionRate": None,
                "salePrice": float(r["price"]) if r["price"] is not None else None,
                "keywordEntryStatus": "ok" if r["keyword_link"] else "missing",
                "keywordUrl": r["keyword_url"],
                "adEntryStatus": "ok" if r["ad_link"] else "missing",
                "adUrl": r["ad_url"],
                "systemLogCount": int(r["system_count"]),
                "manualLog": r["manual_content"],
                "manualEntryCount": int(r["manual_count"]),
                "status": (
                    "已保存"
                    if r["edit_status"] == "submitted"
                    else "草稿"
                    if r["manual_content"]
                    else "缺记录"
                ),
            }
        )
    return success_response(
        request,
        data={"rows": rows, "revisions": revisions, "systemRecords": system_records},
        meta=None,
    )
