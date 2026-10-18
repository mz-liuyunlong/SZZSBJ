"""Read-only, bounded, store-wide coverage audit for Walmart sample facts.

This does not infer actual samples from SaleStat or write business records.
Run only with an approved read-only database account on an approved snapshot.
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
MAX_DISPLAY = 50


def _scope_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:12]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--account", default=None)
    parser.add_argument("--limit", type=int, default=MAX_DISPLAY)
    arguments = parser.parse_args()
    if arguments.end < arguments.start or (arguments.end - arguments.start).days >= MAX_DAYS:
        parser.error("Date range must contain 1 to 31 inclusive business days")
    if not 1 <= arguments.limit <= MAX_DISPLAY:
        parser.error("Limit must be between 1 and 50")
    return arguments


def _report(rows: list[dict[str, Any]], limit: int) -> dict[str, object]:
    states: dict[str, int] = {}
    findings: list[dict[str, object]] = []
    for row in rows:
        captured = int(row["sample_captured"])
        valid_amount = Decimal(str(row["sample_qty"]))
        mart_amount = Decimal(str(row["mart_sample_qty"]))
        unverified = int(row.get("unverified_sample_lines") or 0)
        unresolved = int(row.get("unresolved_sample_lines") or 0)
        cancelled = int(row.get("cancelled_sample_lines") or 0)
        valid_qty = str(valid_amount)
        mart_qty = str(mart_amount)
        if valid_amount != mart_amount:
            state = "SAMPLE_FACT_MART_MISMATCH"
        elif unresolved:
            state = "UNRESOLVED_SAMPLE_IDENTITY"
        elif unverified:
            state = "UNVERIFIED_SAMPLE_CANDIDATES"
        elif cancelled:
            state = "CANCELLED_SAMPLE_CANDIDATES"
        elif captured == 0:
            state = "SAMPLE_NOT_OBSERVED_UNKNOWN_NOT_ZERO"
        else:
            state = "MATCHES_PERSISTED_SAMPLE_FACT"
        states[state] = states.get(state, 0) + 1
        if state != "MATCHES_PERSISTED_SAMPLE_FACT" and len(findings) < limit:
            findings.append(
                {
                    "day_us": row["day_us"].isoformat(),
                    "scope_hash": _scope_hash(
                        row["source_account_ref"],
                        row["store_id"],
                        row["item_id"],
                        row["msku"],
                    ),
                    "status": state,
                    "gross_qty": str(row["gross_qty"]),
                    "captured_sample_lines": captured,
                    "unverified_sample_lines": unverified,
                    "unresolved_sample_lines": unresolved,
                    "cancelled_sample_lines": cancelled,
                    "valid_sample_qty": valid_qty,
                    "mart_sample_qty": mart_qty,
                }
            )
    return {
        "audited_sku_days": len(rows),
        "status_counts": states,
        "sample_findings": findings,
        "truncated": sum(states.values()) - states.get("MATCHES_PERSISTED_SAMPLE_FACT", 0)
        > len(findings),
        "limitations": (
            "This audit cannot prove true sample quantity from absent provider rows. "
            "A persisted zero is not evidence that the provider had zero samples. "
            "Compare provider order-item records under the exact LA purchase-day window."
        ),
    }


def main() -> None:
    args = _parse_args()
    engine = create_engine(get_database_url(get_settings()))
    sql = text(
        """
        with sales as (
            select business_date_la day_us, source_account_ref, store_id,
                   item_id, trim(msku) msku,
                   sum(coalesce(gross_sales_qty,0)) gross_qty,
                   sum(coalesce(sample_qty,0)) mart_sample_qty
            from public.mart_daily_sales_item_day
            where business_date_la between :start and :end
              and (:account is null or source_account_ref=:account)
              and store_id is not null and item_id is not null
              and nullif(trim(msku),'') is not null
            group by 1,2,3,4,5
        ),
        samples as (
            select business_date_utc_minus_7 day_us, source_account_ref,
                   store_id, item_id, nullif(trim(msku),'') msku,
                   count(*) sample_captured,
                   sum(coalesce(quantity,0)) filter
                       (where is_valid_sample=true
                        and sample_rule_version='provider-verified-sample-v5'
                        and is_cancelled=false) sample_qty,
                   count(*) filter
                       (where is_cancelled=false and not (is_valid_sample=true
                        and sample_rule_version='provider-verified-sample-v5'))
                       unverified_sample_lines,
                   count(*) filter (where is_cancelled=true) cancelled_sample_lines,
                   count(*) filter
                       (where store_id is null or item_id is null
                        or nullif(trim(msku),'') is null) unresolved_sample_lines
            from public.fact_walmart_sample_order_items
            where business_date_utc_minus_7 between :start and :end
              and (:account is null or source_account_ref=:account)
            group by 1,2,3,4,5
        )
        select coalesce(s.day_us,f.day_us) day_us,
               coalesce(s.source_account_ref,f.source_account_ref) source_account_ref,
               coalesce(s.store_id,f.store_id) store_id,
               coalesce(s.item_id,f.item_id) item_id,
               coalesce(s.msku,f.msku) msku,
               coalesce(s.gross_qty,0) gross_qty,
               coalesce(f.sample_captured,0) sample_captured,
               coalesce(f.unverified_sample_lines,0) unverified_sample_lines,
               coalesce(f.unresolved_sample_lines,0) unresolved_sample_lines,
               coalesce(f.cancelled_sample_lines,0) cancelled_sample_lines,
               coalesce(f.sample_qty,0) sample_qty,
               coalesce(s.mart_sample_qty,0) mart_sample_qty
        from sales s full join samples f
          on f.day_us=s.day_us
         and f.source_account_ref=s.source_account_ref
         and f.store_id=s.store_id
         and f.item_id=s.item_id
         and f.msku=s.msku
        order by day_us, store_id, item_id, msku
        """
    )
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            data = (
                conn.execute(
                    sql,
                    {"start": args.start, "end": args.end, "account": args.account},
                )
                .mappings()
                .all()
            )
            rows = [dict(row) for row in data]
    print(json.dumps(_report(rows, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
