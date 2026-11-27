"""Copy Product Management source tags into Listing MART by exact account + SKU.

Never mix these provider tags with operator-owned custom Listing tags.
Caller controls the transaction: this module never commits.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

PRODUCT_TAG_SQL = """
WITH sku_candidates AS (
    SELECT p.source_account_ref,
           btrim(p.lingxing_sku_code) AS sku,
           COUNT(*) AS candidates,
           MIN(p.source_snapshot_id::text) AS snapshot_ref
      FROM dwd_lingxing_sku_product_info_current p
     WHERE p.source_account_ref = :account
       AND nullif(btrim(p.lingxing_sku_code), '') IS NOT NULL
     GROUP BY p.source_account_ref, btrim(p.lingxing_sku_code)
),
lookup AS (
    SELECT c.source_account_ref, c.sku, c.candidates,
           CASE WHEN c.candidates = 1 THEN
             COALESCE((
                 SELECT jsonb_agg(
                     jsonb_build_object(
                         'id', t.global_tag_id,
                         'label', btrim(t.tag_name),
                         'color', t.color
                     ) ORDER BY t.ordinal, t.id
                 )
                   FROM dwd_lingxing_sku_global_tags t
                  WHERE t.source_snapshot_id::text = c.snapshot_ref
                    AND nullif(btrim(t.tag_name), '') IS NOT NULL
             ), '[]'::jsonb)
           ELSE '[]'::jsonb END AS product_tags
      FROM sku_candidates c
),
resolved AS (
    SELECT l.id,
           COALESCE(s.product_tags, '[]'::jsonb) AS product_tags,
           CASE WHEN nullif(btrim(l.local_sku), '') IS NULL THEN 'no_sku'
                WHEN s.sku IS NULL THEN 'unmatched'
                WHEN s.candidates > 1 THEN 'ambiguous'
                ELSE 'matched' END AS match_status
      FROM mart_listing_management_current l
      LEFT JOIN lookup s
        ON s.source_account_ref = l.source_account_ref
       AND s.sku = btrim(l.local_sku)
     WHERE l.source_account_ref = :account
)
UPDATE mart_listing_management_current target
   SET product_tags_json = resolved.product_tags,
       product_tags_match_status = resolved.match_status
  FROM resolved
 WHERE target.id = resolved.id
   AND (target.product_tags_json IS DISTINCT FROM resolved.product_tags
        OR target.product_tags_match_status IS DISTINCT FROM resolved.match_status)
"""


def refresh_listing_product_tags(session: Session, source_account_ref: str) -> int:
    """Idempotent current-tag materialization for one account; no cross-account joins.

    Missing/ambiguous SKU matches never inherit tags from an unrelated product.
    If an existing product's tags were cleared, its Listing tags become [].
    """
    if not source_account_ref or not source_account_ref.strip():
        raise ValueError("source_account_ref is required")
    result = session.execute(text(PRODUCT_TAG_SQL), {"account": source_account_ref.strip()})
    return int(result.rowcount or 0)
