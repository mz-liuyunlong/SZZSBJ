"""Preserve unresolved Walmart SEM CSV lines without attributing them to a guessed SKU.

The latest CSV task for each store/date is the source of truth.  Positive
expenses with no unique Listing identity and negative credits are reserved
in a separate, auditable ledger.  The item/day MART contains only reliably
attributed positive SEM expense.

This module does not edit raw provider data, classify sales orders, or
authorize a manual mapping.  All writes share the caller's MART transaction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

# Keep the latest-task and historical-campaign rules aligned with the
# business-rule runner.  Do not use a Listing from an unrelated store.
_RESERVE_SQL = text(
    """
    with raw_today as materialized (
        select r.store_id,r.task_id::text task_id,r.row_index,r.raw_hash,
               r.created_at,
               nullif(r.row_json ->> 'Campaign ID','') campaign_id,
               (regexp_match(r.row_json ->> 'Campaign Name',
                 '(^|[^0-9])([0-9]{11})([^0-9]|$)'))[2] parsed_item_id,
               coalesce(nullif(regexp_replace(coalesce(r.row_json ->> 'Spend',''),
                 '[^0-9.-]','','g'),'')::numeric,0) spend
        from legacy_mirror.raw_walmart_sem_csv r
        where r.csv_type='sem_daily' and r.row_json ->> 'Date'=cast(:day as text)
    ),
    latest_task as (
        select distinct on (store_id) store_id,task_id
        from (select distinct store_id,task_id,created_at from raw_today) t
        order by store_id,created_at desc,task_id desc
    ),
    selected as materialized (
        select r.* from raw_today r join latest_task lt
        on lt.store_id=r.store_id and lt.task_id=r.task_id
        where exists (
          select 1 from dim_walmart_listings l
          where l.source_account_ref=:account and l.store_id=r.store_id
        ) or exists (
          select 1 from dim_lingxing_stores s
          where s.source_account_ref=:account and s.store_id=r.store_id
        )
    ),
    campaigns as materialized (
        select distinct store_id,campaign_id from selected
        where campaign_id is not null
    ),
    historical as (
        select h.store_id,h.campaign_id,
               min(h.parsed_item_id) mapped_item_id,
               count(distinct h.parsed_item_id) candidate_count
        from (
          select store_id,
                 nullif(row_json ->> 'Campaign ID','') campaign_id,
                 (regexp_match(row_json ->> 'Campaign Name',
                  '(^|[^0-9])([0-9]{11})([^0-9]|$)'))[2] parsed_item_id
          from legacy_mirror.raw_walmart_sem_csv
          where csv_type='sem_daily'
        ) h
        join campaigns c on c.store_id=h.store_id
          and c.campaign_id=h.campaign_id
        where h.parsed_item_id is not null
        group by 1,2
    ),
    resolved as (
        select s.*,
               coalesce(s.parsed_item_id,
                 case when h.candidate_count=1 then h.mapped_item_id end) item_id,
               coalesce(h.candidate_count,0) historical_count
        from selected s left join historical h
        on h.store_id=s.store_id and h.campaign_id=s.campaign_id
    ),
    classified as (
        select r.*,
               coalesce(l.msku_count,0) msku_count,
               case
                 when r.spend<0 then 'NEGATIVE_CREDIT_REVIEW'
                 when r.item_id is null and r.historical_count>1
                   then 'CAMPAIGN_ID_AMBIGUOUS'
                 when r.item_id is null then 'ITEM_ID_UNRESOLVED'
                 when coalesce(l.msku_count,0)=0 then 'LISTING_NOT_FOUND'
                 when l.msku_count>1 then 'LISTING_IDENTITY_AMBIGUOUS'
                 else 'ATTRIBUTED'
               end reason_code
        from resolved r
        left join lateral (
          select count(distinct nullif(trim(msku),'')) msku_count
          from dim_walmart_listings l
          where l.source_account_ref=:account and l.store_id=r.store_id
            and l.item_id=r.item_id
        ) l on true
    )
    insert into biz_finance_unallocated_sem_lines
      (id,source_account_ref,business_date_la,store_id,task_id,row_index,
       raw_hash,campaign_id,candidate_item_id,spend_amount_usd,
       reason_code,status,is_current,created_at,last_seen_at)
    select gen_random_uuid(),:account,:day,store_id,task_id,row_index,
           raw_hash,campaign_id,item_id,spend,reason_code,
           'pending',true,now(),now()
    from classified
    where reason_code<>'ATTRIBUTED' and spend<>0
    on conflict (source_account_ref,business_date_la,store_id,task_id,row_index)
    do update set
      raw_hash=excluded.raw_hash,
      campaign_id=excluded.campaign_id,
      candidate_item_id=excluded.candidate_item_id,
      spend_amount_usd=excluded.spend_amount_usd,
      reason_code=excluded.reason_code,
      is_current=true,
      last_seen_at=now(),
      status=case
        when biz_finance_unallocated_sem_lines.status in ('resolved','dismissed')
        then 'pending'
        else biz_finance_unallocated_sem_lines.status
      end
    """
)


def reserve_unallocated_sem_lines(
    session: Session,
    *,
    source_account_ref: str,
    business_date: date,
) -> Decimal:
    """Reconcile the current unallocated SEM lines in the MART transaction.

    Prior lines are retained for manual review/audit; a no-longer-applicable
    line becomes inactive rather than being deleted.  A failed day rolls
    back both this ledger and the MART rows.
    """
    params = {"account": source_account_ref, "day": business_date}
    session.execute(
        text(
            "update biz_finance_unallocated_sem_lines set is_current=false "
            "where source_account_ref=:account and business_date_la=:day "
            "and is_current=true"
        ),
        params,
    )
    session.execute(_RESERVE_SQL, params)
    amount = session.execute(
        text(
            "select coalesce(sum(spend_amount_usd),0) "
            "from biz_finance_unallocated_sem_lines "
            "where source_account_ref=:account and business_date_la=:day "
            "and is_current=true"
        ),
        params,
    ).scalar_one()
    return Decimal(str(amount))


def reset_sample_dispute_current(
    session: Session,
    *,
    source_account_ref: str,
    business_date: date,
) -> None:
    """Retain old evidence, but mark it historical before rebuilding the day."""
    session.execute(
        text(
            "update biz_finance_sample_disputes set is_current=false "
            "where source_account_ref=:account and business_date_la=:day "
            "and is_current=true"
        ),
        {"account": source_account_ref, "day": business_date},
    )


def record_sample_dispute(
    session: Session,
    *,
    source_account_ref: str,
    business_date: date,
    store_id: str,
    item_id: str,
    msku: str,
    sample_qty: Decimal,
    sales_qty: Decimal,
    sample_amount: Decimal,
    sales_amount: Decimal,
) -> None:
    """Keep the exact disputed item/day identity without guessing bad orders."""
    session.execute(
        text(
            "insert into biz_finance_sample_disputes "
            "(id,source_account_ref,business_date_la,store_id,item_id,msku,"
            "sample_qty,sales_qty,sample_amount,sales_amount,status,is_current,"
            "created_at,last_seen_at) "
            "values (gen_random_uuid(),:account,:day,:store,:item,:msku,"
            ":sample_qty,:sales_qty,:sample_amount,:sales_amount,'pending',true,"
            "now(),now()) "
            "on conflict (source_account_ref,business_date_la,store_id,item_id,msku) "
            "do update set sample_qty=excluded.sample_qty,"
            "sales_qty=excluded.sales_qty,sample_amount=excluded.sample_amount,"
            "sales_amount=excluded.sales_amount,is_current=true,last_seen_at=now(),"
            "status=case when biz_finance_sample_disputes.status "
            "in ('resolved','dismissed') then 'pending' "
            "else biz_finance_sample_disputes.status end"
        ),
        {
            "account": source_account_ref,
            "day": business_date,
            "store": store_id,
            "item": item_id,
            "msku": msku,
            "sample_qty": sample_qty,
            "sales_qty": sales_qty,
            "sample_amount": sample_amount,
            "sales_amount": sales_amount,
        },
    )
