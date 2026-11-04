"""Daily LA-midnight clearance evaluations; idempotent, auditable, analysis-only.

A midnight evaluation uses the PREVIOUS completed Los Angeles sales day,
and current WFS inventory. Missing evidence is reported, never fabricated.
No applications, pricing, ads or Walmart operations are triggered here.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.clearance_center.repository import ClearanceReadRepository

LOS_ANGELES = ZoneInfo("America/Los_Angeles")
ADVISORY_LOCK = 2406110401
BATCH_SIZE = 100
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=20)
RECLAIM_AFTER = timedelta(minutes=45)


def daily_window(now: datetime) -> tuple[date, date]:
    """DST-safe local run date and last completed LA sales day."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Daily evaluation requires an aware instant")
    day = now.astimezone(LOS_ANGELES).date()
    return day, day - timedelta(days=1)


def is_midnight_window(now: datetime) -> bool:
    """Only the Los Angeles midnight hour can start scheduled evaluations."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Scheduler requires an aware instant")
    return now.astimezone(LOS_ANGELES).hour == 0


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _number(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _quality(evaluation: dict) -> str:
    warnings = evaluation.get("warnings", [])
    if "WFS_STOCK_UNAVAILABLE_OR_STALE" in warnings:
        return "stale"
    if "SALES_WINDOW_UNVERIFIED" in warnings:
        return "partial"
    return "complete" if not warnings else "partial"


class DailyClearanceEvaluation:
    """One durable run per LA calendar day, with bounded retries and pages."""

    def __init__(self, session: Session):
        self.session = session
        self.repository = ClearanceReadRepository(session)

    def _claim(self, run_date: date, as_of: date, now: datetime) -> str | None:
        row = self.session.execute(
            text("""select id::text id,status,attempt_count,started_at,next_retry_at
                 from ops_clearance_daily_runs
                where run_date_la=:day for update"""),
            {"day": run_date},
        ).mappings().first()
        if row:
            if row["status"] == "succeeded" or row["attempt_count"] >= MAX_ATTEMPTS:
                self.session.commit()
                return None
            if row["status"] == "running" and now - row["started_at"] < RECLAIM_AFTER:
                self.session.commit()
                return None
            if row["next_retry_at"] and now < row["next_retry_at"]:
                self.session.commit()
                return None
            run_id = str(row["id"])
            self.session.execute(
                text("""update ops_clearance_daily_runs
                       set status='running',started_at=:now,finished_at=null,
                           attempt_count=attempt_count+1,next_retry_at=null,error_code=null,
                           listing_count=0,auto_high_count=0,auto_medium_count=0,
                           review_required_count=0,quality_json='{}'::jsonb
                       where id=cast(:id as uuid)"""),
                {"id": run_id, "now": now},
            )
            self.session.execute(
                text("delete from ops_clearance_daily_evaluations where run_id=cast(:id as uuid)"),
                {"id": run_id},
            )
        else:
            run_id = str(uuid4())
            self.session.execute(
                text("""insert into ops_clearance_daily_runs
                        (id,run_date_la,as_of_date_la,status,started_at)
                        values(cast(:id as uuid),:day,:as_of,'running',:now)"""),
                {"id": run_id, "day": run_date, "as_of": as_of, "now": now},
            )
        self.session.commit()
        return run_id

    def _next_page(self, cursor: tuple[str, str, str] | None) -> list[dict]:
        sql = """select l.id::text id,l.source_account_ref,l.store_id,l.store_name,
                       l.item_id,l.local_sku,l.msku,l.title,l.picture_url,l.owner_ref,
                       l.listing_status,l.fulfillment_type,l.sale_price_amount,
                       l.sale_price_currency_code,l.wfs_available_quantity,
                       l.inbound_quantity,l.average_rating,l.review_count,
                       l.buybox_status,l.listing_start_at_utc,l.calculated_at,
                       snap.wfs_available_quantity snapshot_wfs_available,
                       snap.captured_at inventory_captured_at
                  from mart_listing_management_current l
                  left join lateral (
                    select i.wfs_available_quantity,i.captured_at
                      from fact_walmart_listing_inventory_daily i
                     where i.source_account_ref=l.source_account_ref
                       and i.store_id=l.store_id and i.item_id=l.item_id
                     order by i.snapshot_date_la desc,i.captured_at desc limit 1
                  ) snap on true
                 where (:account is null or
                        (l.source_account_ref,l.store_id,l.item_id) >
                        (:account,:store,:item))
                 order by l.source_account_ref,l.store_id,l.item_id
                 limit :limit"""
        params = {
            "account": cursor[0] if cursor else None,
            "store": cursor[1] if cursor else None,
            "item": cursor[2] if cursor else None,
            "limit": BATCH_SIZE,
        }
        return [dict(x) for x in self.session.execute(text(sql), params).mappings()]

    def _persist(self, run_id: str, listing: dict, evaluation: dict, version: int, now: datetime) -> None:
        numeric_keys = {
            "stock_capital_usd": evaluation.get("stock_capital_usd"),
            "coverage_days": evaluation.get("coverage_days"),
            "profit_30d_amount": evaluation.get("profit_30d_amount"),
            "refund_loss_30d": evaluation.get("refund_loss_30d"),
        }
        self.session.execute(
            text("""insert into ops_clearance_daily_evaluations
                    (id,run_id,listing_id,source_account_ref,store_id,item_id,
                     risk_level,candidate_status,stock_capital_usd,coverage_days,
                     profit_30d_amount,refund_loss_30d,quality_status,
                     rule_version,rule_config_version,evaluation_json,evaluated_at)
                    values(cast(:id as uuid),cast(:run_id as uuid),
                           cast(:listing_id as uuid),:account,:store,:item,
                           :risk,:candidate,:capital,:coverage,:profit,:refund_loss,:quality,
                           :rule,:version,cast(:payload as jsonb),:now)
                    on conflict(run_id,source_account_ref,store_id,item_id)
                    do update set risk_level=excluded.risk_level,
                       candidate_status=excluded.candidate_status,
                       stock_capital_usd=excluded.stock_capital_usd,
                       coverage_days=excluded.coverage_days,
                       profit_30d_amount=excluded.profit_30d_amount,
                       refund_loss_30d=excluded.refund_loss_30d,
                       quality_status=excluded.quality_status,
                       rule_version=excluded.rule_version,
                       rule_config_version=excluded.rule_config_version,
                       evaluation_json=excluded.evaluation_json,
                       evaluated_at=excluded.evaluated_at"""),
            {
                "id": str(uuid4()), "run_id": run_id, "listing_id": listing["id"],
                "account": listing["source_account_ref"], "store": listing["store_id"],
                "item": listing["item_id"], "risk": evaluation["risk_level"],
                "candidate": evaluation["candidate_status"],
                "capital": _number(numeric_keys["stock_capital_usd"]),
                "coverage": numeric_keys["coverage_days"],
                "profit": _number(numeric_keys["profit_30d_amount"]),
                "refund_loss": _number(numeric_keys["refund_loss_30d"]),
                "quality": _quality(evaluation), "rule": evaluation["rule_version"],
                "version": version, "payload": _json(evaluation), "now": now,
            },
        )

    def evaluate_day(self, *, now: datetime | None = None, scheduled: bool = True) -> dict:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        run_date, as_of = daily_window(current)
        if scheduled and not is_midnight_window(current):
            return {"status": "outside_midnight_window"}
        # The caller pins this session to one physical connection while holding
        # the advisory lock. Only the daily evaluator may acquire this key.
        locked = bool(self.session.scalar(text("select pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK}))
        if not locked:
            return {"status": "already_running"}
        run_id: str | None = None
        try:
            run_id = self._claim(run_date, as_of, current)
            if not run_id:
                return {"status": "already_recorded"}
            counts = {"total": 0, "high": 0, "medium": 0, "review": 0,
                      "missing_sales": 0, "missing_cost": 0, "missing_stock": 0}
            rules_cache: dict[str, tuple[dict, int]] = {}
            cursor: tuple[str, str, str] | None = None
            while True:
                page = self._next_page(cursor)
                if not page:
                    break
                evidence = self.repository.evidence(page, as_of=as_of)
                for listing in page:
                    account = listing["source_account_ref"]
                    if account not in rules_cache:
                        rules_cache[account] = self.repository.rules(account)
                    rules, version = rules_cache[account]
                    key = (str(account), str(listing["store_id"]), str(listing["item_id"]))
                    evaluation = self.repository.evaluated(listing, evidence[key], rules)
                    self._persist(run_id, listing, evaluation, version, current)
                    counts["total"] += 1
                    if evaluation["candidate_status"] == "auto":
                        if evaluation["risk_level"] == "high":
                            counts["high"] += 1
                        elif evaluation["risk_level"] == "medium":
                            counts["medium"] += 1
                    counts["review"] += int(evaluation["candidate_status"] == "review_required")
                    warnings = evaluation.get("warnings", [])
                    counts["missing_sales"] += int("SALES_WINDOW_UNVERIFIED" in warnings)
                    counts["missing_cost"] += int("PROFIT_COST_INCOMPLETE" in warnings)
                    counts["missing_stock"] += int("WFS_STOCK_UNAVAILABLE_OR_STALE" in warnings)
                last = page[-1]
                cursor = (str(last["source_account_ref"]), str(last["store_id"]), str(last["item_id"]))
                self.session.commit()
            self.session.execute(
                text("""update ops_clearance_daily_runs
                           set status='succeeded',finished_at=:now,
                               listing_count=:total,auto_high_count=:high,
                               auto_medium_count=:medium,review_required_count=:review,
                               quality_json=cast(:quality as jsonb)
                         where id=cast(:id as uuid)"""),
                {"id": run_id, "now": datetime.now(UTC),
                 "total": counts["total"], "high": counts["high"],
                 "medium": counts["medium"], "review": counts["review"],
                 "quality": _json(counts)},
            )
            self.session.commit()
            return {"status": "succeeded", "run_id": run_id, "as_of_date_la": as_of.isoformat(), **counts}
        except Exception:
            self.session.rollback()
            if run_id:
                self.session.execute(
                    text("""update ops_clearance_daily_runs
                               set status='failed',finished_at=:now,
                                   next_retry_at=:retry,error_code='EVALUATION_FAILED'
                             where id=cast(:id as uuid)"""),
                    {"id": run_id, "now": datetime.now(UTC),
                     "retry": datetime.now(UTC) + RETRY_DELAY},
                )
                self.session.commit()
            raise
        finally:
            self.session.execute(text("select pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK})
            self.session.commit()
