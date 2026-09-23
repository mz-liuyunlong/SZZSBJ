"""Backfill governed after-sales reason classification for an explicit date window.

Read-only by default. Add --write only after a reviewed dry run and explicit
production authorization. The script only updates classification fields; refund
quantities/amounts/losses are verified unchanged.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_database_url, get_settings  # noqa: E402
from app.modules.after_sales.classification import AfterSalesReasonClassifier  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-account-ref", default="primary")
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--only-unclassified",
        action="store_true",
        help="Only classify rows whose normalized_reason_code is currently null.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist classification results. Without this flag the run is read-only.",
    )
    return parser.parse_args()


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def main() -> int:
    args = parse_args()
    if args.to_date < args.from_date:
        raise SystemExit("--to-date must not be earlier than --from-date")

    engine = create_engine(get_database_url(get_settings()), pool_pre_ping=True)
    with engine.begin() as conn:
        classifier = AfterSalesReasonClassifier.from_executor(conn)
        where = [
            "source_account_ref = :source_account_ref",
            "platform_code = 'walmart'",
            "return_order_at is not null",
            "return_order_at::date between :from_date and :to_date",
        ]
        if args.only_unclassified:
            where.append("normalized_reason_code is null")

        params = {
            "source_account_ref": args.source_account_ref,
            "from_date": args.from_date,
            "to_date": args.to_date,
        }
        where_sql = " and ".join(where)

        rows = (
            conn.execute(
                text(
                    f"""
                    select
                        id::text as id,
                        return_reason_code,
                        return_description,
                        return_qty,
                        refund_amount,
                        refund_loss_amount
                    from after_sales_refund_items
                    where {where_sql}
                    order by return_order_at, id
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )

        before_qty = sum((_decimal(row["return_qty"]) for row in rows), Decimal("0"))
        before_amount = sum((_decimal(row["refund_amount"]) for row in rows), Decimal("0"))
        before_loss = sum((_decimal(row["refund_loss_amount"]) for row in rows), Decimal("0"))

        source_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        responsibility_counts: Counter[str] = Counter()
        updates: list[dict[str, Any]] = []

        for row in rows:
            result = classifier.classify(
                row["return_reason_code"],
                row["return_description"],
            )
            values = {"id": row["id"], **result.as_storage_values()}
            updates.append(values)
            source_counts[result.classification_source] += 1
            reason_counts[result.normalized_reason_code] += 1
            responsibility_counts[result.responsibility_code] += 1

        print("=== AFTER_SALES_CLASSIFICATION_BACKFILL ===")
        print("source_account_ref=", args.source_account_ref)
        print("from_date=", args.from_date.isoformat())
        print("to_date=", args.to_date.isoformat())
        print("rows=", len(rows))
        print("write=", args.write)
        print("classification_source_counts=", dict(sorted(source_counts.items())))
        print("reason_counts=", dict(sorted(reason_counts.items())))
        print("responsibility_counts=", dict(sorted(responsibility_counts.items())))
        print("pending_rows=", responsibility_counts.get("PENDING", 0))
        print("unclassified_rows=", reason_counts.get("UNCLASSIFIED", 0))

        if not args.write:
            print("BACKFILL_DRY_RUN=PASS")
            return 0

        if updates:
            conn.execute(
                text(
                    """
                    update after_sales_refund_items
                    set
                        normalized_reason_code = :normalized_reason_code,
                        reason_category_code = :reason_category_code,
                        responsibility_code = :responsibility_code,
                        classification_source = :classification_source,
                        classification_confidence = :classification_confidence,
                        classification_rule_id = :classification_rule_id,
                        classification_rule_version = :classification_rule_version,
                        classified_at = :classified_at,
                        updated_at = now()
                    where id = :id
                    """
                ),
                updates,
            )

        target_ids = [str(row["id"]) for row in rows]
        verification = (
            conn.execute(
                text(
                    """
                select
                    count(*) as rows,
                    coalesce(sum(return_qty),0) as refund_qty,
                    coalesce(sum(refund_amount),0) as refund_amount,
                    coalesce(sum(refund_loss_amount),0) as refund_loss_amount,
                    count(*) filter (where normalized_reason_code is null) as missing_reason,
                    count(*) filter (where responsibility_code is null) as missing_responsibility
                from after_sales_refund_items
                where id::text = any(:target_ids)
                """
                ),
                {"target_ids": target_ids},
            )
            .mappings()
            .one()
        )

        if int(verification["rows"]) != len(rows):
            raise RuntimeError("row count changed during classification backfill")
        if _decimal(verification["refund_qty"]) != before_qty:
            raise RuntimeError("refund quantity changed during classification backfill")
        if _decimal(verification["refund_amount"]) != before_amount:
            raise RuntimeError("refund amount changed during classification backfill")
        if _decimal(verification["refund_loss_amount"]) != before_loss:
            raise RuntimeError("refund loss changed during classification backfill")
        if int(verification["missing_reason"]) != 0:
            raise RuntimeError("classification left missing normalized_reason_code rows")
        if int(verification["missing_responsibility"]) != 0:
            raise RuntimeError("classification left missing responsibility_code rows")

        print("BACKFILL_WRITE_VERIFY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
