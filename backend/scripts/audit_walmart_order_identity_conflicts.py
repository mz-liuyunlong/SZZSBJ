"""Read-only preview of legacy Walmart order-line identity duplicates.

The output contains hashed scopes, counts, and differing field names only. It
never deletes rows or prints order, store, SKU, payload, or credential values.
Run only with an approved read-only database account or an isolated snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_database_url, get_settings

MAX_DAYS = 31
MAX_DISPLAY = 100


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--account", required=True)
    parser.add_argument("--limit", type=int, default=50)
    arguments = parser.parse_args()
    if arguments.end < arguments.start or (arguments.end - arguments.start).days >= MAX_DAYS:
        parser.error("Date range must contain 1 to 31 inclusive business days")
    if not 1 <= arguments.limit <= MAX_DISPLAY:
        parser.error("Limit must be between 1 and 100")
    return arguments


def _scope_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]


def _report(rows: list[dict[str, Any]], limit: int) -> dict[str, object]:
    groups = []
    for row in rows[:limit]:
        groups.append(
            {
                "scope_hash": _scope_hash(
                    row["source_account_ref"],
                    row["store_id"],
                    row["source_order_id"],
                    row["source_order_line_id"],
                ),
                "business_date": row["business_date"].isoformat(),
                "physical_versions": int(row["physical_versions"]),
                "current_versions": int(row["current_versions"]),
                "quantity_versions": int(row["quantity_versions"]),
                "amount_versions": int(row["amount_versions"]),
                "item_versions": int(row["item_versions"]),
                "status_versions": int(row["status_versions"]),
                "repair_action": "OWNER_REVIEW_REQUIRED_NO_AUTOMATIC_DELETE",
            }
        )
    return {
        "duplicate_identity_groups": len(rows),
        "preview": groups,
        "truncated": len(rows) > limit,
        "write_performed": False,
        "limitations": (
            "This preview identifies physical versions under one provider identity. "
            "It does not select a business winner or authorize deletion/backfill."
        ),
    }


def main() -> None:
    args = _parse_args()
    engine = create_engine(get_database_url(get_settings()))
    with engine.connect() as connection:
        has_current_marker = bool(
            connection.scalar(
                text(
                    "select exists (select 1 from information_schema.columns "
                    "where table_schema='public' and table_name='fact_walmart_order_items' "
                    "and column_name='is_identity_current')"
                )
            )
        )
    current_count = (
        "count(*) filter (where is_identity_current=true)" if has_current_marker else "0::bigint"
    )
    sql = text(
        f"""
        select source_account_ref,store_id,source_order_id,source_order_line_id,
               min(business_date_la) business_date,
               count(*) physical_versions,
               {current_count} current_versions,
               count(distinct quantity) quantity_versions,
               count(distinct sales_revenue_amount) amount_versions,
               count(distinct item_id) item_versions,
               count(distinct (order_status_raw,order_sub_status_raw,flow_node_raw)) status_versions
        from public.fact_walmart_order_items
        where source_account_ref=:account
          and business_date_la between :start and :end
          and store_id is not null
          and source_order_line_id is not null
        group by source_account_ref,store_id,source_order_id,source_order_line_id
        having count(*) > 1
        order by min(business_date_la),count(*) desc
        """
    )
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            data = (
                connection.execute(
                    sql,
                    {"account": args.account, "start": args.start, "end": args.end},
                )
                .mappings()
                .all()
            )
    print(
        json.dumps(_report([dict(row) for row in data], args.limit), ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
