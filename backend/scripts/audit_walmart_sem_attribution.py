"""Bounded, read-only audit of Walmart SEM CSV attribution for one explicit store.

The CSV mirror has no trusted account ownership column. Passing --account and
--store does not prove ownership; use separately verified provider evidence.
Never use this command to assign an unknown campaign to an Item ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_database_url, get_settings

MAX_DAYS = 31
MAX_FINDINGS = 50


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--account", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--limit", type=int, default=MAX_FINDINGS)
    args = parser.parse_args()
    if args.end < args.start or (args.end - args.start).days >= MAX_DAYS:
        parser.error("Date range must contain 1 to 31 inclusive days")
    if not 1 <= args.limit <= MAX_FINDINGS:
        parser.error("Limit must be between 1 and 50")
    if not args.account.strip() or not args.store.strip():
        parser.error("Both account and store must be nonblank")
    return args


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _report(rows: list[dict[str, Any]], limit: int) -> dict[str, object]:
    totals: dict[str, dict[str, object]] = {}
    findings: list[dict[str, object]] = []
    for row in rows:
        status = str(row["attribution_status"])
        spend = Decimal(str(row["spend_usd"]))
        if spend < 0:
            raise ValueError("Negative SEM credit requires a separate reconciliation")
        entry = totals.setdefault(status, {"campaign_rows": 0, "spend_usd": Decimal("0")})
        entry["campaign_rows"] = int(entry["campaign_rows"]) + 1
        entry["spend_usd"] = Decimal(str(entry["spend_usd"])) + spend
        if status != "ONE_LISTING_MATCH" and len(findings) < limit:
            findings.append({
                "business_date": row["business_date"].isoformat(),
                "scope_hash": _hash(row["store_id"]),
                "campaign_hash": _hash(row["campaign_id"], row["campaign_name"]),
                "status": status,
                "spend_usd": str(spend),
                "listing_matches": int(row["listing_matches"]),
            })
    total_spend = sum((Decimal(str(r["spend_usd"])) for r in rows), Decimal("0"))
    unallocated = sum((
        Decimal(str(r["spend_usd"])) for r in rows
        if r["attribution_status"] != "ONE_LISTING_MATCH"
    ), Decimal("0"))
    return {
        "campaign_rows": len(rows),
        "total_spend_usd": str(total_spend),
        "unallocated_spend_usd": str(unallocated),
        "by_status": {
            key: {"campaign_rows": int(value["campaign_rows"]),
                  "spend_usd": str(value["spend_usd"])}
            for key, value in sorted(totals.items())
        },
        "findings": findings,
        "truncated": sum(
            1 for row in rows if row["attribution_status"] != "ONE_LISTING_MATCH"
        ) > len(findings),
        "ownership_verification": "NOT_PROVEN_BY_CSV",
        "disclaimer": (
            "The mirror lacks trusted source-account ownership. Verify store ownership, "
            "provider currency and source campaign records independently. A unique "
            "historical name/Listing match is a candidate, not authorization to allocate."
        ),
        "write_performed": False,
    }


AUDIT_SQL = text(
    """
    WITH raw AS (
        SELECT task_id, created_at, row_index, store_id,
               nullif(row_json ->> 'Date','')::date business_date,
               nullif(row_json ->> 'Campaign ID','') campaign_id,
               row_json ->> 'Campaign Name' campaign_name,
               (regexp_match(row_json ->> 'Campaign Name',
                   '(^|[^0-9])([0-9]{11})([^0-9]|$)'))[2] parsed_item_id,
               coalesce(nullif(regexp_replace(coalesce(row_json ->> 'Spend',''),
                   '[^0-9.-]','','g'),'')::numeric,0) spend
        FROM legacy_mirror.raw_walmart_sem_csv
        WHERE csv_type='sem_daily' AND store_id=:store
          AND nullif(row_json ->> 'Date','')::date BETWEEN :start AND :end
    ),
    latest AS (
        SELECT DISTINCT ON (store_id,business_date)
               store_id,business_date,task_id
        FROM raw
        ORDER BY store_id,business_date,created_at DESC,task_id DESC
    ),
    history AS (
        SELECT store_id,
               nullif(row_json ->> 'Campaign ID','') campaign_id,
               (regexp_match(row_json ->> 'Campaign Name',
                   '(^|[^0-9])([0-9]{11})([^0-9]|$)'))[2] parsed_item_id
        FROM legacy_mirror.raw_walmart_sem_csv
        WHERE csv_type='sem_daily' AND store_id=:store
    ),
    history_map AS (
        SELECT store_id,campaign_id,min(parsed_item_id) mapped_item_id
        FROM history WHERE campaign_id IS NOT NULL
            AND parsed_item_id IS NOT NULL
        GROUP BY store_id,campaign_id
        HAVING count(DISTINCT parsed_item_id)=1
    ),
    selected AS (
        SELECT raw.business_date,raw.store_id,raw.campaign_id,
               raw.campaign_name,raw.spend,
               coalesce(raw.parsed_item_id,history_map.mapped_item_id) item_id
        FROM raw
        JOIN latest ON latest.store_id=raw.store_id
            AND latest.business_date=raw.business_date
            AND latest.task_id=raw.task_id
        LEFT JOIN history_map ON history_map.store_id=raw.store_id
            AND history_map.campaign_id=raw.campaign_id
    ),
    grouped AS (
        SELECT business_date,store_id,campaign_id,campaign_name,item_id,
               sum(spend) spend_usd
        FROM selected
        GROUP BY 1,2,3,4,5
    )
    SELECT grouped.business_date,grouped.store_id,grouped.campaign_id,
           grouped.campaign_name,grouped.spend_usd,
           coalesce(matches.listing_matches,0) listing_matches,
           CASE WHEN grouped.item_id IS NULL THEN 'ITEM_ID_UNRESOLVED'
                WHEN coalesce(matches.listing_matches,0)=0 THEN 'LISTING_NOT_FOUND'
                WHEN matches.listing_matches<>1 THEN 'LISTING_AMBIGUOUS'
                ELSE 'ONE_LISTING_MATCH'
           END attribution_status
    FROM grouped
    LEFT JOIN LATERAL (
        SELECT count(DISTINCT nullif(trim(msku),'')) listing_matches
        FROM dim_walmart_listings
        WHERE source_account_ref=:account
          AND store_id=grouped.store_id AND item_id=grouped.item_id
    ) matches ON TRUE
    ORDER BY grouped.business_date,grouped.store_id,grouped.campaign_id,
             grouped.campaign_name
    """
)


def main() -> None:
    args = _parse_args()
    engine = create_engine(get_database_url(get_settings()), hide_parameters=True)
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '20000ms'"))
                rows = [
                    dict(row)
                    for row in connection.execute(
                        AUDIT_SQL,
                        {
                            "start": args.start,
                            "end": args.end,
                            "account": args.account,
                            "store": args.store,
                        },
                    ).mappings().all()
                ]
        print(json.dumps(_report(rows, args.limit), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
