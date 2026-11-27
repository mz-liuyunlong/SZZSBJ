"""SKU progress: separately refreshed source projection and shared read base.

Refresh only owns its MART. Business records are read at query time; no change
of manual status, remarks, purchasing or independent-site state is performed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

MART = "mart_new_product_sku_progress_current"
# Shared by refresh and strict purchase admission. Canonical current snapshot,
# not historical tags or an incomplete Listing tag projection.
ELIGIBLE = """
 SELECT c.source_account_ref, c.identity_id AS sku_identity_id,
        c.lingxing_sku_code AS sku, c.product_name, c.main_image_url,
        c.product_developer_name AS developer_name,
        c.product_developer_uid AS developer_uid
 FROM dwd_lingxing_sku_product_info_current c
 JOIN dwd_lingxing_sku_identity_index i ON i.id=c.identity_id
  AND i.source_account_ref=c.source_account_ref AND i.is_active
 WHERE c.provider='lingxing' AND c.lingxing_sku_code IS NOT NULL
   AND btrim(c.lingxing_sku_code)<>''
   AND EXISTS (SELECT 1 FROM dwd_lingxing_sku_global_tags t
     WHERE t.identity_id=c.identity_id AND t.source_snapshot_id=c.source_snapshot_id
       AND t.tag_name='小批量测品')
"""
# Ambiguous source SKU identities cannot be assigned Listing or purchasing.
REFRESH = text(f"""
WITH eligible AS MATERIALIZED ({ELIGIBLE}),
 candidates AS (
 SELECT e.*, (SELECT count(*) FROM dwd_lingxing_sku_identity_index i
  WHERE i.source_account_ref=e.source_account_ref AND i.provider='lingxing'
    AND i.is_active AND i.lingxing_sku_code=e.sku)=1 AS identity_verified
 FROM eligible e
 ), projected AS (
 SELECT e.*, s.source_created_at AS development_at,
 COALESCE(x.listings,'[]'::jsonb) AS listings_json
 FROM candidates e
 LEFT JOIN dwd_lingxing_sku_source_current sc ON sc.source_account_ref=e.source_account_ref
   AND sc.sku_identity_id=e.sku_identity_id AND sc.source_interface='productList'
 LEFT JOIN dwd_lingxing_sku_source_snapshots s ON s.id=sc.snapshot_id
 LEFT JOIN LATERAL (
 SELECT jsonb_agg(jsonb_build_object(
  'store_id', l.store_id,'store_name', l.store_name,'item_id',l.item_id,
  'msku',l.msku,'owner_ref',l.owner_ref,'gtin',l.gtin,
  'listing_status',l.listing_status,'launch_date_cn',fs.launch_date_cn,
  'strike_effect',CASE raw.payload_json #>> '{{final_observation,parsed_result,hasStrikethrough}}'
    WHEN 'true' THEN 'effective' WHEN 'false' THEN 'ineffective' ELSE NULL END,
  'strike_price',CASE WHEN
   raw.payload_json #>> '{{final_observation,parsed_result,hasStrikethrough}}'='false' THEN NULL
   ELSE COALESCE(mon.strike_price_amount,l.strike_price_amount)::text END,
  'strike_currency',COALESCE(mon.strike_price_currency_code,l.strike_price_currency_code),
  'sale_price',COALESCE(mon.sale_price_amount,l.sale_price_amount)::text,
  'sale_currency',COALESCE(mon.sale_price_currency_code,l.sale_price_currency_code),'ad_enabled',CASE
    WHEN a.source_observed_at BETWEEN now()-interval '48 hours' AND now()
      THEN a.ad_enabled ELSE NULL END,
  'ad_status_checked_at',a.ad_status_checked_at,'ad_source_observed_at',a.source_observed_at)
  ORDER BY l.store_id,l.item_id) AS listings
 FROM mart_listing_management_current l
 LEFT JOIN listing_wfs_first_stock fs ON fs.source_account_ref=l.source_account_ref
  AND fs.store_id=l.store_id AND fs.item_id=l.item_id AND fs.msku=l.msku
 LEFT JOIN mart_listing_ad_status_current a ON a.source_account_ref=l.source_account_ref
  AND a.store_id=l.store_id AND a.item_id=l.item_id
 LEFT JOIN mart_walmart_monitor_listing_current mon ON mon.source_account_ref=l.source_account_ref
  AND mon.store_id=l.store_id AND mon.item_id=l.item_id
 LEFT JOIN raw_walmart_monitor_events raw ON raw.id=mon.source_raw_event_id
 WHERE e.identity_verified AND l.source_account_ref=e.source_account_ref AND l.local_sku=e.sku
 ) x ON true
 )
INSERT INTO {MART} AS m
 (source_account_ref,sku_identity_id,sku,product_name,main_image_url,developer_name,
 developer_uid,identity_verified,development_at,listings_json,eligible,updated_at)
SELECT source_account_ref,sku_identity_id,sku,product_name,main_image_url,developer_name,
 developer_uid,identity_verified,development_at,listings_json,true,now() FROM projected
ON CONFLICT (source_account_ref,sku_identity_id) DO UPDATE SET
 sku=excluded.sku,product_name=excluded.product_name,main_image_url=excluded.main_image_url,
 developer_name=excluded.developer_name,developer_uid=excluded.developer_uid,
 identity_verified=excluded.identity_verified,development_at=excluded.development_at,
 listings_json=excluded.listings_json,eligible=true,updated_at=now()
WHERE (m.sku,m.product_name,m.main_image_url,m.developer_name,m.developer_uid,
 m.identity_verified,m.development_at,m.listings_json,m.eligible) IS DISTINCT FROM
 (excluded.sku,excluded.product_name,excluded.main_image_url,excluded.developer_name,
 excluded.developer_uid,excluded.identity_verified,excluded.development_at,
 excluded.listings_json,excluded.eligible)
""")
EXIT = text(f"""
WITH eligible AS MATERIALIZED ({ELIGIBLE})
UPDATE {MART} m SET eligible=false,updated_at=now()
WHERE m.eligible AND NOT EXISTS(SELECT 1 FROM eligible e
 WHERE e.source_account_ref=m.source_account_ref AND e.sku_identity_id=m.sku_identity_id)
""")


def refresh_sources(db: Session) -> dict[str, Any]:
    # Single-writer and consistent snapshot. No writes to authoritative tables.
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    db.execute(text("SET LOCAL statement_timeout='60s'"))
    db.execute(text("SET LOCAL lock_timeout='3s'"))
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(722601002)")):
        return {"status": "busy"}
    if not db.scalar(
        text("SELECT to_regclass('public.mart_new_product_sku_progress_current') IS NOT NULL")
    ):
        return {"status": "waiting_for_0100"}
    changed = db.execute(REFRESH).rowcount
    removed = db.execute(EXIT).rowcount
    return {"status": "complete", "changed": changed, "exited": removed}


BASE = f"""
SELECT m.*, p.id AS progress_id, COALESCE(p.progress_status,'in_progress') AS progress_status,
       p.remark,p.manual_locked,p.reason_type,p.exited_at,COALESCE(p.version,0) AS progress_version
FROM {MART} m LEFT JOIN biz_new_product_sku_progress p
 ON p.source_account_ref=m.source_account_ref AND p.sku_identity_id=m.sku_identity_id
WHERE m.eligible AND m.source_account_ref IN :accounts
"""
