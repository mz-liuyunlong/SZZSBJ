"""Explicit bounded replay of retained RAW only; never calls Lingxing or writes old tables."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa

from . import sku_ad_foundation_projection as p
from . import sku_ad_foundation_runtime as r

logger = logging.getLogger(__name__)


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError("Use an explicit timezone, e.g. 2026-11-01T00:00:00+08:00")
    return result.astimezone(UTC)


def ad_refs(session, *, after, before, cursor, limit):
    return session.execute(
        sa.text(
            "select b.id,b.received_at,p.policy_key from ods_api_raw_blobs b\n"
            "        join gov_raw_retention_policies p on p.id=b.retention_policy_id\n"
            "        where p.policy_key in ('lingxing-data-pages-walmart-ad-item-sp-lis"
            "t-v1','lingxing-data-pages-walmart-advertiser-list-v1')\n"
            "          and b.storage_mode='database' and b.payload_json is not null "
            "and b.received_at>=:after and b.received_at<:before\n"
            "          and (b.received_at,b.id)<(:cursor_at,:cursor_id)\n"
            "        order by b.received_at desc,b.id desc limit :limit"
        ),
        dict(after=after, before=before, cursor_at=cursor[0], cursor_id=cursor[1], limit=limit),
    ).all()


def replay_ad_blob(session, ref, seen, policy):
    # Only the immutable payload is requested; if RAW receipt changed, use the exact fetched
    # observation instead.
    blob = session.execute(
        sa.text("""select b.payload_json,b.received_at from ods_api_raw_blobs b
        join gov_raw_retention_policies p on p.id=b.retention_policy_id
        where b.id=:id and p.policy_key=:policy and b.storage_mode='database' """),
        {"id": ref, "policy": policy},
    ).one()
    kind = "walmart_ad_item_sp_list" if "ad-item-sp-list" in policy else "walmart_advertiser_list"
    rows = p.ad_payload_rows(blob[0])
    seen = blob[1]
    # A retained RAW blob has no request-date/account context. Do not invent either.
    r.save_ad_source_page(
        session, account=None, day=None, kind=kind, blob=ref, seen=seen, rows=rows
    )
    # No historical request account/date evidence. Never publish current config or
    # daily money under a guessed account or date. Live pulls populate those layers.
    return {"source_rows": len(rows), "account_verified": False, "business_date_verified": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", choices=["sku", "ads"], required=True)
    ap.add_argument(
        "--account",
        help=(
            "Required exact source account for SKU replay; ads retained blobs have no "
            "verified account"
        ),
    )
    ap.add_argument("--from", dest="start", type=parse_time, required=True)
    ap.add_argument("--until", dest="end", type=parse_time, required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--cursor-at", type=parse_time)
    ap.add_argument("--cursor-id", type=UUID)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.start >= args.end or not 1 <= args.limit <= 200 or not 1 <= args.max_pages <= 200:
        ap.error("invalid time window or batch limit")
    if (args.cursor_at is None) != (args.cursor_id is None):
        ap.error("provide both cursor components")
    if args.scope == "sku" and not args.account:
        ap.error("--account required for SKU")
    if args.scope == "ads" and args.account:
        ap.error("historical ad blobs are unscoped; account cannot be asserted")
    if args.apply and os.getenv("SZZSBJ_FOUNDATION_BACKFILL_APPROVED") != "1":
        ap.error("explicit backfill approval required")
    from app.db.session import get_session_factory

    counts = {"processed": 0, "failed": 0, "preview": not args.apply, "has_more": False}
    cursor = (args.cursor_at, args.cursor_id) if args.cursor_at else (args.end, UUID(int=0))
    with get_session_factory()() as session:
        # Preview and apply both select only bounded metadata. No full JSON scans.
        for _ in range(args.max_pages):
            session.execute(sa.text("set local statement_timeout='30s'"))
            if args.scope == "sku":
                refs = r.sku_refs(
                    session,
                    account=args.account,
                    after=args.start,
                    before=args.end,
                    cursor=cursor,
                    limit=args.limit,
                )
            else:
                refs = ad_refs(
                    session, after=args.start, before=args.end, cursor=cursor, limit=args.limit
                )
            session.rollback()
            if not refs:
                counts["has_more"] = False
                break
            for row in refs:
                if args.apply:
                    try:
                        session.execute(sa.text("set local lock_timeout='1s'"))
                        session.execute(sa.text("set local statement_timeout='30s'"))
                        if args.scope == "sku":
                            p.publish_sku_raw_page(session, row[0])
                        else:
                            replay_ad_blob(session, *row)
                        session.commit()
                    except Exception as exc:
                        session.rollback()
                        counts["failed"] += 1
                        logger.warning(
                            "foundation_replay_failed ref=%s error_type=%s",
                            row[0],
                            type(exc).__name__,
                        )
                        # Do not move cursor past a failed page; resume from the last successful
                        # one.
                        counts.update(
                            cursor_at=cursor[0].isoformat(), cursor_id=str(cursor[1]), has_more=True
                        )
                        print(json.dumps(counts))
                        return 1
                counts["processed"] += 1
                cursor = (row[1], row[0])
            counts["has_more"] = len(refs) == args.limit
            if not counts["has_more"]:
                break
    counts.update(cursor_at=cursor[0].isoformat(), cursor_id=str(cursor[1]))
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
