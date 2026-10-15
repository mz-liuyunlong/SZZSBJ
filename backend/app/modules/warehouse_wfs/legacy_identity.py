"""Read-only source-account reconciliation for legacy WFS fee cases.

Legacy mirror rows have no source_account_ref. Never infer it from only a
store name or pick an arbitrary row when two accounts claim one identity.
Both preflight and writer MUST use this same candidate-resolution query.
"""

LEGACY_IDENTITY_CTE = """
with legacy as (
  select l.*, trim(l.msku) normalized_msku,
    md5(concat_ws('|',
      l.id::text, l.status, l.manual_fee::text, l.actual_fee::text,
      l.total_units::text, l.est_recover::text, coalesce(l.case_nos,''),
      coalesce(l.follow_log,''), coalesce(l.reason,''), coalesce(l.remark,''),
      coalesce(l.claim_amount::text,''), coalesce(l.recovered_amount::text,''),
      coalesce(l.updated_at::text,'')
    )) sync_hash_value
  from legacy_mirror.event_wfs_fee_case l
  where l.platform = 'walmart'
), candidate_accounts as (
  select l.id legacy_case_id, m.source_account_ref
  from legacy l
  join mart_daily_sales_item_day m
    on m.store_id = l.store_id and m.item_id = l.item_id
   and trim(m.msku) = l.normalized_msku
  union
  select l.id legacy_case_id, d.source_account_ref
  from legacy l
  join dim_walmart_listings d
    on d.store_id = l.store_id and d.item_id = l.item_id
   and trim(d.msku) = l.normalized_msku
), account_counts as (
  select l.id legacy_case_id,
    count(distinct a.source_account_ref) matched_accounts,
    min(a.source_account_ref) source_account_ref
  from legacy l
  left join candidate_accounts a on a.legacy_case_id = l.id
  group by l.id
), resolved as (
  select l.*, a.matched_accounts, a.source_account_ref
  from legacy l
  join account_counts a on a.legacy_case_id = l.id
), enriched as (
  select l.*,
    m.owner_ref,
    coalesce(m.local_sku, d.local_sku) local_sku,
    coalesce(m.local_name, m.title, d.local_name, d.title) product_name
  from resolved l
  left join lateral (
    select m.owner_ref, m.local_sku, m.local_name, m.title
    from mart_daily_sales_item_day m
    where m.source_account_ref = l.source_account_ref
      and m.store_id = l.store_id and m.item_id = l.item_id
      and trim(m.msku) = l.normalized_msku
    order by m.business_date_la desc
    limit 1
  ) m on true
  left join lateral (
    select d.local_sku, d.local_name, d.title
    from dim_walmart_listings d
    where d.source_account_ref = l.source_account_ref
      and d.store_id = l.store_id and d.item_id = l.item_id
      and trim(d.msku) = l.normalized_msku
    limit 1
  ) d on true
  where l.matched_accounts = 1
)
"""

LEGACY_IDENTITY_PREFLIGHT_SQL = (
    LEGACY_IDENTITY_CTE
    + """
select
  (select count(*) from legacy) legacy_total,
  (select count(*) from resolved where matched_accounts = 1) matched_identities,
  (select count(*) from resolved where matched_accounts = 0) unmatched_identities,
  (select count(*) from resolved where matched_accounts > 1) ambiguous_identities,
  (select count(*) from (
    select source_account_ref, store_id, item_id, normalized_msku
    from enriched
    group by source_account_ref, store_id, item_id, normalized_msku
    having count(*) > 1
  ) duplicates) duplicate_identities,
  (select count(*) from legacy where
    trim(store_id) = '' or trim(item_id) = '' or normalized_msku = ''
    or manual_fee < 0 or actual_fee < 0 or total_units < 0
    or est_recover < 0 or coalesce(recovered_amount, 0) < 0
  ) invalid_values,
  coalesce((select jsonb_object_agg(status, amount) from (
    select status, count(*) amount from legacy group by status
  ) counts), '{}'::jsonb) status_breakdown
"""
)
