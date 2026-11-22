"""Bounded, idempotent Walmart ad-item catalog ingestion.

Source: immutable Lingxing ad-item response blobs. Current projections are not
financial facts; fact_walmart_ad_item_sp_daily remains the money authority.
This module is called only by the existing nightly master or explicit CLI,
never on a read endpoint or at import time.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

POLICY = "lingxing-data-pages-walmart-ad-item-sp-list-v1"
SOURCE_KEY = "walmart_ad_item_sp_v1"
MAX_BATCH = 50

_BLOBS = text("""
SELECT b.id, b.received_at, b.payload_json
FROM ods_api_raw_blobs b
JOIN gov_raw_retention_policies p ON p.id=b.retention_policy_id
WHERE p.policy_key=:policy AND b.storage_mode='database'
  AND b.payload_json IS NOT NULL
  AND (b.received_at, b.id) > (:last_at, CAST(:last_id AS uuid))
ORDER BY b.received_at, b.id LIMIT :limit
""")

_LOCK = text("""
SELECT pg_advisory_xact_lock(940094)
""")

_INIT = text("""
INSERT INTO biz_walmart_ad_ingest_cursor
 (source_key, last_received_at, last_blob_id)
VALUES (:key, NULL, NULL)
ON CONFLICT (source_key) DO NOTHING
""")

_CURSOR = text("""
SELECT last_received_at, last_blob_id
FROM biz_walmart_ad_ingest_cursor
WHERE source_key=:key FOR UPDATE
""")

_HISTORY = text("""
INSERT INTO biz_walmart_ad_item_history (
 source_blob_id, source_ordinal, source_observed_at,
 advertiser_id, campaign_id, ad_group_id, ad_item_id, item_id,
 campaign_and_targeting_type, campaign_kind,
 entity_created_at_raw, add_date_raw, payload_json
) VALUES (
 :blob, :ordinal, :seen, :advertiser, :campaign, :group_id, :ad_item,
 :item, :type_label, :kind, :created, :add_date, CAST(:payload AS jsonb)
)
ON CONFLICT (source_blob_id, source_ordinal) DO NOTHING
""")

_CAMPAIGN = text("""
INSERT INTO biz_walmart_ad_campaign_catalog (
 advertiser_id, campaign_id, campaign_and_targeting_type, campaign_kind,
 classification_conflict, campaign_name, campaign_status,
 first_seen_at, last_seen_at, source_blob_id, payload_json
) VALUES (
 :advertiser, :campaign, :type_label, :kind, false,
 :campaign_name, :campaign_status, :seen, :seen, :blob,
 CAST(:payload AS jsonb)
)
ON CONFLICT (advertiser_id,campaign_id) DO UPDATE SET
 classification_conflict =
   biz_walmart_ad_campaign_catalog.classification_conflict
   OR (
     biz_walmart_ad_campaign_catalog.campaign_kind IS NOT NULL
     AND EXCLUDED.campaign_kind IS NOT NULL
     AND biz_walmart_ad_campaign_catalog.campaign_kind <> EXCLUDED.campaign_kind
   ),
 campaign_kind = CASE
   WHEN biz_walmart_ad_campaign_catalog.classification_conflict
     OR (
       biz_walmart_ad_campaign_catalog.campaign_kind IS NOT NULL
       AND EXCLUDED.campaign_kind IS NOT NULL
       AND biz_walmart_ad_campaign_catalog.campaign_kind <> EXCLUDED.campaign_kind
     ) THEN NULL
   WHEN EXCLUDED.campaign_kind IS NULL
     THEN biz_walmart_ad_campaign_catalog.campaign_kind
   ELSE EXCLUDED.campaign_kind
 END,
 first_seen_at = LEAST(biz_walmart_ad_campaign_catalog.first_seen_at, EXCLUDED.first_seen_at),
 last_seen_at = GREATEST(biz_walmart_ad_campaign_catalog.last_seen_at, EXCLUDED.last_seen_at),
 campaign_and_targeting_type = CASE
   WHEN EXCLUDED.last_seen_at >= biz_walmart_ad_campaign_catalog.last_seen_at
   THEN EXCLUDED.campaign_and_targeting_type
   ELSE biz_walmart_ad_campaign_catalog.campaign_and_targeting_type END,
 campaign_name = CASE WHEN EXCLUDED.last_seen_at >= biz_walmart_ad_campaign_catalog.last_seen_at
   THEN EXCLUDED.campaign_name ELSE biz_walmart_ad_campaign_catalog.campaign_name END,
 campaign_status = CASE WHEN EXCLUDED.last_seen_at >= biz_walmart_ad_campaign_catalog.last_seen_at
   THEN EXCLUDED.campaign_status ELSE biz_walmart_ad_campaign_catalog.campaign_status END,
 source_blob_id = CASE WHEN EXCLUDED.last_seen_at >= biz_walmart_ad_campaign_catalog.last_seen_at
   THEN EXCLUDED.source_blob_id ELSE biz_walmart_ad_campaign_catalog.source_blob_id END,
 payload_json = CASE WHEN EXCLUDED.last_seen_at >= biz_walmart_ad_campaign_catalog.last_seen_at
   THEN EXCLUDED.payload_json ELSE biz_walmart_ad_campaign_catalog.payload_json END
""")

_CURRENT = text("""
INSERT INTO biz_walmart_ad_item_current (
 advertiser_id, campaign_id, ad_group_id, ad_item_id, item_id,
 campaign_kind, ad_group_name, ad_group_status, ad_status,
 entity_created_at_raw, add_date_raw,
 first_seen_at, last_seen_at, source_blob_id, payload_json
) VALUES (
 :advertiser, :campaign, :group_id, :ad_item, :item,
 :kind, :group_name, :group_status, :ad_status,
 :created, :add_date, :seen, :seen, :blob, CAST(:payload AS jsonb)
)
ON CONFLICT (advertiser_id,campaign_id,ad_group_id,ad_item_id,item_id)
DO UPDATE SET
 first_seen_at=LEAST(biz_walmart_ad_item_current.first_seen_at,EXCLUDED.first_seen_at),
 last_seen_at=GREATEST(biz_walmart_ad_item_current.last_seen_at,EXCLUDED.last_seen_at),
 campaign_kind=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.campaign_kind ELSE biz_walmart_ad_item_current.campaign_kind END,
 ad_group_name=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.ad_group_name ELSE biz_walmart_ad_item_current.ad_group_name END,
 ad_group_status=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.ad_group_status ELSE biz_walmart_ad_item_current.ad_group_status END,
 ad_status=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.ad_status ELSE biz_walmart_ad_item_current.ad_status END,
 entity_created_at_raw=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.entity_created_at_raw ELSE biz_walmart_ad_item_current.entity_created_at_raw END,
 add_date_raw=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.add_date_raw ELSE biz_walmart_ad_item_current.add_date_raw END,
 source_blob_id=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.source_blob_id ELSE biz_walmart_ad_item_current.source_blob_id END,
 payload_json=CASE WHEN EXCLUDED.last_seen_at>=biz_walmart_ad_item_current.last_seen_at
   THEN EXCLUDED.payload_json ELSE biz_walmart_ad_item_current.payload_json END
""")

_ADVANCE = text("""
UPDATE biz_walmart_ad_ingest_cursor SET
 last_received_at=:seen, last_blob_id=:blob,
 processed_blobs=processed_blobs+:blobs,
 processed_rows=processed_rows+:rows,
 updated_at=now()
WHERE source_key=:key
""")


def _string(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _kind(value: Any) -> str | None:
    from .unified_ad_evidence import campaign_kind

    return campaign_kind(value)


def _items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        return []
    items = data["list"]
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("AD_CATALOG_INVALID_ITEM_SHAPE")
    return items


def ingest_batch(
    source: Session, target: Session, *, limit: int = MAX_BATCH, apply: bool = False
) -> dict:
    """One bounded source page and atomic checkpoint; caller owns transactions.

    Never read raw table by payload text or process without deterministic cursor.
    For preview, target must have the 0094 schema but no business rows are written.
    """
    if not 1 <= limit <= MAX_BATCH:
        raise ValueError("AD_CATALOG_BATCH_LIMIT")
    # The caller must guard target against production write without approval.
    if apply:
        target.execute(_LOCK)
        target.execute(_INIT, {"key": SOURCE_KEY})
        cursor = target.execute(_CURSOR, {"key": SOURCE_KEY}).mappings().one()
    else:
        cursor = (
            target.execute(
                text(
                    "SELECT last_received_at,last_blob_id "
                    "FROM biz_walmart_ad_ingest_cursor WHERE source_key=:key"
                ),
                {"key": SOURCE_KEY},
            )
            .mappings()
            .first()
        )
    from datetime import UTC
    from uuid import UUID

    last_at = (
        cursor["last_received_at"]
        if cursor and cursor["last_received_at"]
        else datetime(1970, 1, 1, tzinfo=UTC)
    )
    last_id = str(cursor["last_blob_id"]) if cursor and cursor["last_blob_id"] else str(UUID(int=0))
    blobs = list(
        source.execute(
            _BLOBS, {"policy": POLICY, "last_at": last_at, "last_id": last_id, "limit": limit}
        ).mappings()
    )
    counts = Counter()
    for blob in blobs:
        items = _items(blob["payload_json"])
        if not items and isinstance(blob["payload_json"], dict):
            # Empty list is valid but missing/invalid structure fails closed.
            data = blob["payload_json"].get("data")
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                raise ValueError("AD_CATALOG_SOURCE_SHAPE_UNVERIFIED")
        for ordinal, item in enumerate(items):
            counts["history_rows"] += 1
            advertiser = _string(item.get("advertiserId"))
            campaign = _string(item.get("campaignId"))
            group_id = _string(item.get("adGroupId"))
            ad_item = _string(item.get("adItemId"))
            product = _string(item.get("itemId"))
            kind = _kind(item.get("campaignAndTargetingType"))
            shared = {
                "blob": blob["id"],
                "ordinal": ordinal,
                "seen": blob["received_at"],
                "advertiser": advertiser,
                "campaign": campaign,
                "group_id": group_id,
                "ad_item": ad_item,
                "item": product,
                "kind": kind,
                "type_label": _string(item.get("campaignAndTargetingType")),
                "created": _string(item.get("entityCreateAt")),
                "add_date": _string(item.get("addDate")),
                "payload": __import__("json").dumps(item, ensure_ascii=False),
            }
            if apply:
                target.execute(_HISTORY, shared)
            if advertiser and campaign:
                campaign_row = {
                    **shared,
                    "campaign_name": _string(item.get("campaignName")),
                    "campaign_status": _string(item.get("campaignStatus")),
                }
                if apply:
                    target.execute(_CAMPAIGN, campaign_row)
                counts["campaign_evidence"] += 1
            if all((advertiser, campaign, group_id, ad_item, product)):
                current_row = {
                    **shared,
                    "group_name": _string(item.get("adGroupName")),
                    "group_status": _string(item.get("adGroupStatus")),
                    "ad_status": _string(item.get("adStatus")),
                }
                if apply:
                    target.execute(_CURRENT, current_row)
                counts["item_evidence"] += 1
            else:
                counts["incomplete_identities"] += 1
    if apply and blobs:
        target.execute(
            _ADVANCE,
            {
                "key": SOURCE_KEY,
                "seen": blobs[-1]["received_at"],
                "blob": blobs[-1]["id"],
                "blobs": len(blobs),
                "rows": counts["history_rows"],
            },
        )
    return {
        "blobs": len(blobs),
        "has_more": len(blobs) == limit,
        "last_received_at": blobs[-1]["received_at"].isoformat() if blobs else None,
        **dict(counts),
        "applied": apply,
    }


def sync_catalog(*, limit: int = MAX_BATCH, pages: int = 1, apply: bool = False) -> dict:
    """Guarded source-to-target ingestion; separate source and transaction target."""
    import os

    if pages < 1 or pages > 2000:
        raise ValueError("AD_CATALOG_PAGES_OUT_OF_RANGE")
    env = os.getenv("APP_ENV", "").strip().lower()
    if apply:
        if env == "production":
            if os.getenv("SZZSBJ_AD_CATALOG_PRODUCTION_WRITE_APPROVED") != "1":
                raise PermissionError("AD_CATALOG_PRODUCTION_WRITE_NOT_APPROVED")
        elif env in {"local", "dev", "development"}:
            from app.db.session import get_engine

            from .unified_publish import local_target_approved

            engine = get_engine()
            if not local_target_approved(engine.url.database, engine.url.host):
                raise PermissionError("AD_CATALOG_NONLOCAL_TARGET")
        else:
            raise PermissionError("AD_CATALOG_WRITE_ENV_NOT_APPROVED")

    from app.db.session import get_engine

    from .read_source import get_new_product_read_session

    source_gen = get_new_product_read_session()
    source = next(source_gen)
    total = Counter()
    last = None
    try:
        for _ in range(pages):
            with Session(get_engine(), autoflush=False, expire_on_commit=False) as target:
                with target.begin():
                    last = ingest_batch(source, target, limit=limit, apply=apply)
            for name in (
                "blobs",
                "history_rows",
                "campaign_evidence",
                "item_evidence",
                "incomplete_identities",
            ):
                total[name] += last.get(name, 0)
            if not last["has_more"] or not apply:
                break
        return {**dict(total), "has_more": last["has_more"] if last else False, "applied": apply}
    finally:
        source_gen.close()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--limit", type=int, default=MAX_BATCH)
    args = parser.parse_args()
    print(
        json.dumps(
            sync_catalog(pages=args.pages, limit=args.limit, apply=args.apply), ensure_ascii=False
        )
    )
