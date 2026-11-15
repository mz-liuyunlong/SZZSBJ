"""Only the nightly master calls this ad-only evidence publication phase.

Reuses the existing approved ad snapshot and protected persistence, but never
supplies an evaluation or writes a score/grade. No separate schedule or route.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine

from .models import NewProductRegistry
from .read_source import get_new_product_read_session
from .unified_ad_evidence import load_ad_snapshots, verified_campaign_map
from .unified_publish import _save_one

MAX_PRODUCTS = 5000
BATCH = 40
_WFS = text("""
WITH wanted AS (
 SELECT account,store,item FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,l.first_wfs_available_date_la AS start_day
FROM wanted w LEFT JOIN listing_wfs_first_stock_la_locked l
 ON l.source_account_ref=w.account AND l.store_id=w.store AND l.item_id=w.item
""")


# This source has ~1,027 advertiser-list RAW records; the entire RAW table is
# ~18 GB and has no usable created_at/payload text index. Do NOT search
# payload_json::text over all policies. Only select a bounded official scope.
_ADVERTISER_CATALOG = text("""
SELECT b.payload_json
FROM ods_api_raw_blobs b
WHERE b.retention_policy_id = (
    SELECT p.id FROM gov_raw_retention_policies p
    WHERE p.policy_key = 'lingxing-data-pages-walmart-advertiser-list-v1'
)
  AND b.created_at >= :since
  AND b.payload_json IS NOT NULL
  AND b.payload_bytes BETWEEN 1 AND :max_payload_bytes
ORDER BY b.created_at DESC
LIMIT :row_limit
""")


def load_scoped_campaign_catalog(source: Session, cutoff: date):
    """Return only explicitly labeled campaign identities; never infer type.

    Scanning 18-GB raw JSON for a text key is prohibited. Absence/truncation
    of source labels means that category evidence is unavailable, not zero.
    All advertising totals still come from the independent fact table.
    """
    from datetime import timedelta

    max_rows = 1500
    source_rows = list(
        source.execute(
            _ADVERTISER_CATALOG,
            {
                "since": cutoff - timedelta(days=180),
                "row_limit": max_rows + 1,
                "max_payload_bytes": 32768,
            },
        ).mappings()
    )
    if len(source_rows) > max_rows:
        # Do not accept a partial catalog as a complete classification source.
        return ({}, False), "SOURCE_SCOPE_TRUNCATED", len(source_rows)
    mapping, conflicts = verified_campaign_map(r["payload_json"] for r in source_rows)
    if conflicts:
        # Colliding campaign labels are never used; verified_campaign_map drops
        # all conflicting identities.
        status = "VERIFIED_LABELS_WITH_CONFLICTS" if mapping else "NO_VERIFIED_TYPES"
    else:
        status = "VERIFIED_LABELS" if mapping else "NO_VERIFIED_TYPES"
    return (mapping, False), status, len(source_rows)


def publish_daily_ads(*, cutoff: date, apply: bool = True) -> dict:
    """Ad DISPLAY only; dry_run reads source without any business-table write."""
    if not isinstance(cutoff, date):
        raise ValueError("CUTOFF_REQUIRED")
    results = Counter()
    gen = get_new_product_read_session()
    source = next(gen)
    try:
        with Session(get_engine(), autoflush=False, expire_on_commit=False) as target:
            r = NewProductRegistry
            rows = target.scalars(
                select(r)
                .where(r.is_currently_tagged.is_(True))
                .order_by(r.source_account_ref, r.store_id, r.item_id)
                .limit(MAX_PRODUCTS + 1)
            ).all()
            if len(rows) > MAX_PRODUCTS:
                raise RuntimeError("AD_PUBLISH_SCOPE_OVER_LIMIT")
            keys = [
                (str(row.source_account_ref), str(row.store_id), str(row.item_id)) for row in rows
            ]
            if not keys:
                return {"products": 0}
            # Initial SELECT opens an implicit Session transaction; close it
            # before using explicit one-batch-at-a-time write transactions.
            target.rollback()
            catalog, catalog_state, catalog_rows = load_scoped_campaign_catalog(source, cutoff)
            results["catalog_rows"] = catalog_rows
            results["catalog_verified_identities"] = len(catalog[0])
            for offset in range(0, len(keys), BATCH):
                batch = keys[offset : offset + BATCH]
                wanted = json.dumps(
                    [{"account": a, "store": s, "item": i} for a, s, i in batch],
                    separators=(",", ":"),
                )
                dates = {
                    (str(row["account"]), str(row["store"]), str(row["item"])): row["start_day"]
                    for row in source.execute(_WFS, {"wanted": wanted}).mappings()
                }
                snapshots = load_ad_snapshots(
                    source, batch, dates, cutoff, campaign_catalog=catalog
                )
                # Count evidence completeness even when publishing.
                for key in batch:
                    results["evidence_" + snapshots[key]["status"]] += 1
                if not apply:
                    continue
                with target.begin():
                    for key in batch:
                        outcome = _save_one(
                            target,
                            key,
                            snapshots[key],
                            {"evaluation": None, "rule_version": 0},
                            cutoff=cutoff,
                        )
                        results[outcome] += 1
            return {
                "products": len(keys),
                "catalog_state": catalog_state,
                **dict(sorted(results.items())),
            }
    finally:
        gen.close()
