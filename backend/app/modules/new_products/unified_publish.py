"""ONE PR337 performance result publisher, shared by daily and rule-apply triggers.

This module performs no work on import or Listing GET.  Read-only operational
source, local writable result table, and explicit publishing authorization are
separate.  Existing approved/frozen scores and existing 14-day business columns
are never silently overwritten.  Ads are one evidence group in this publisher,
not a second scheduler or a second calculation pipeline.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .unified_ad_evidence import load_ad_snapshots

LOG = logging.getLogger(__name__)
LA = ZoneInfo("America/Los_Angeles")
BATCH = 40
Key = tuple[str, str, str]


def permission_to_write() -> bool:
    """Production requires a second explicit authorization; local is opt-in."""
    env = os.getenv("APP_ENV", "").strip().lower()
    enabled = os.getenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "").strip().lower() in {
        "1",
        "yes",
        "true",
        "on",
    }
    if not enabled:
        return False
    if env in {"local", "dev", "development"}:
        return True
    return env == "production" and os.getenv(
        "SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", ""
    ).strip().lower() in {"1", "yes", "true", "on"}


def local_target_approved(database: str | None, host: str | None) -> bool:
    # The SZZSBJ production name is szzsbj_app. Never let a local flag turn
    # an SSH tunnel to production into a writable publication target.
    return database in {"szzsbj_hybrid", "szzsbj_dev"} and host in {"127.0.0.1", "localhost", "::1"}


def _eligible_rows(source: Session, item_ids: set[str] | None, limit: int) -> list[dict[str, Any]]:
    from .models import NewProductRegistry

    r = NewProductRegistry
    stmt = select(r).where(r.is_currently_tagged.is_(True))
    if item_ids is not None:
        stmt = stmt.where(r.item_id.in_(item_ids))
    if not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500")
    records = source.scalars(
        stmt.order_by(r.source_account_ref, r.store_id, r.item_id).limit(limit + 1)
    ).all()
    if len(records) > limit:
        raise ValueError("PUBLISH_SCOPE_OVER_LIMIT: explicit limit required")
    return [
        {"key": (str(r.source_account_ref), str(r.store_id), str(r.item_id)), "registry_id": r.id}
        for r in records
    ]


def _candidate_scores(
    source: Session,
    target: Session,
    keys: list[Key],
    cutoff: date,
) -> dict[Key, dict[str, Any]]:
    """Reuse existing 14-day evaluation, never create a second scoring formula."""
    from .bulk_read import load_read_snapshot
    from .models import MarketScore
    from .scoring import evaluate
    from .service import NewProductService
    from .testing_profit import load_testing_profit_page
    from .testing_profit_projection import attach_testing_profit_facts

    svc = NewProductService(target, read_session=source)
    config, version = svc._config()
    source_snap = load_read_snapshot(source, keys, cutoff)
    profit = load_testing_profit_page(source, keys, cutoff)
    markets = {
        (str(m.source_account_ref), str(m.store_id), str(m.item_id)): m
        for m in target.scalars(
            select(MarketScore).where(
                tuple_(
                    MarketScore.source_account_ref, MarketScore.store_id, MarketScore.item_id
                ).in_(keys)
            )
        ).all()
    }
    results = {}
    for key in keys:
        try:
            f = svc._facts(*key, market_score=markets.get(key), snapshot=source_snap)
            attach_testing_profit_facts(f, profit.get(key))
            real_profit = profit.get(key)
            expected_policy = "returns_ignored_samples_excluded_sample_ads_included"
            independent_ready = (
                isinstance(real_profit, dict)
                and real_profit.get("status") == "scored"
                and real_profit.get("policy") == expected_policy
                and not real_profit.get("missing")
            )
            # This is the ONLY authority for refund/sample/SEM-adjusted ROI.
            # A partial or missing independent result must never fall back to
            # daily MART gross_profit, even if _facts() could calculate one.
            if independent_ready:
                attach_testing_profit_facts(f, real_profit)
            else:
                f.update(
                    {
                        "roi": None,
                        "gross_margin_pct": None,
                        "profit_usd": None,
                        "profit_calc_status": "partial",
                        "profit_source": "new_products_testing_profit_full_history_v2",
                        "profit_calc_missing": (
                            list(real_profit.get("missing") or ["policy_unverified"])
                            if isinstance(real_profit, dict)
                            else ["independent_profit_missing"]
                        ),
                    }
                )
            # The first paid sale cannot be a sample-only day. If the
            # historical independent source disagrees with the 14-day order
            # evidence, retain the profit but block final grading.
            lineage_ok = True
            if independent_ready and real_profit.get("first_order_date"):
                first_wfs = f.get("first_wfs_available_date_la")
                if isinstance(first_wfs, date):
                    first_order = date.fromisoformat(real_profit["first_order_date"])
                    actual_day = (first_order - first_wfs).days + 1
                    saved_day = f.get("first_order_day")
                    if 1 <= actual_day <= 14 and (
                        saved_day is None or int(saved_day) != actual_day
                    ):
                        lineage_ok = False
            if not lineage_ok:
                f["profit_calc_missing"] = ["FIRST_PAID_ORDER_SOURCE_DISAGREEMENT"]
                f["roi"] = None
                f["gross_margin_pct"] = None
            ev = evaluate(f, config, version)
            results[key] = {"facts": f, "evaluation": ev, "rule_version": version}
            results[key].update(
                {
                    "profit": real_profit,
                    "profit_ready": independent_ready and lineage_ok,
                    "market_version": markets[key].version if key in markets else 0,
                }
            )
        except (ValueError, ArithmeticError, KeyError, TypeError) as exc:
            # A data-quality exception cannot silently become a publishable zero.
            LOG.warning(
                "pr337_unified_score_unavailable item=%s type=%s", key[2], type(exc).__name__
            )
            results[key] = {"facts": {}, "evaluation": None, "rule_version": version}
    return results


def _is_frozen(target: Session, key: Key, registry_id: Any) -> bool:
    from .models import NewProductTrackingCurrent, TrackingDecision

    current = target.get(NewProductTrackingCurrent, registry_id)
    if current is not None and current.final_result is not None:
        return True
    return (
        target.scalar(
            select(TrackingDecision.id)
            .where(
                TrackingDecision.source_account_ref == key[0],
                TrackingDecision.store_id == key[1],
                TrackingDecision.item_id == key[2],
                TrackingDecision.decision.in_(["打品成功", "打品失败"]),
            )
            .limit(1)
        )
        is not None
    )


def _save_one(
    target: Session,
    key: Key,
    ads: dict[str, Any],
    score: dict[str, Any],
    *,
    cutoff: date,
) -> str:
    """Single v2 write authority for non-approved/non-final new products.

    The upstream MART / FACT tables are strictly read-only.  Existing wrong
    snapshot fields are archived, not mistaken for current scoring evidence.
    Neither an old grade nor an old publisher provenance blocks a correction
    on a genuinely open, unapproved testing item.
    """
    from .models import (
        MarketScore,
        NewProductPerformanceCurrent,
        NewProductRegistry,
        NewProductTrackingCurrent,
        NewProductTrackingReviewApplication,
        PurchaseApplication,
        RuleVersion,
    )

    r = target.scalar(
        select(NewProductRegistry)
        .where(
            NewProductRegistry.source_account_ref == key[0],
            NewProductRegistry.store_id == key[1],
            NewProductRegistry.item_id == key[2],
            NewProductRegistry.is_currently_tagged.is_(True),
        )
        .limit(1)
    )
    if r is None:
        return "missing_local_registry"
    if _is_frozen(target, key, r.id):
        return "frozen"

    # Never rewrite an outcome that someone has already acted on.  Purchase,
    # tracking and review applications live in separate business tables.
    purchase_lock = target.scalar(
        select(PurchaseApplication.id)
        .where(
            PurchaseApplication.source_account_ref == key[0],
            PurchaseApplication.store_id == key[1],
            PurchaseApplication.item_id == key[2],
            PurchaseApplication.status.in_(["submitted", "approved"]),
        )
        .limit(1)
    )
    review_lock = target.scalar(
        select(NewProductTrackingReviewApplication.id)
        .where(
            NewProductTrackingReviewApplication.registry_id == r.id,
            NewProductTrackingReviewApplication.status.in_(["submitted", "approved"]),
        )
        .limit(1)
    )
    tracking = target.get(NewProductTrackingCurrent, r.id)
    if (
        purchase_lock is not None
        or review_lock is not None
        or (
            tracking is not None
            and (
                tracking.purchase_application_id is not None
                or tracking.purchase_status in {"submitted", "approved", "审核中", "已批准"}
                or tracking.purchase_approved_qty is not None
            )
        )
    ):
        return "protected_workflow"

    p = target.scalar(
        select(NewProductPerformanceCurrent)
        .where(NewProductPerformanceCurrent.registry_id == r.id)
        .with_for_update()
    )
    if p is None:
        p = NewProductPerformanceCurrent(registry_id=r.id)
        target.add(p)
    if p.process_status not in (
        None,
        "观察期",
        "待评分",
        "待评估",
        "未完成",
        "new",
        "active",
        "evaluating",
        "待计算",
        "数据待评估",
        "待市场评分",
        "待采购确认",
    ):
        return "protected_process_status"

    # The current LA-midnight master also invokes an AD-DISPLAY-ONLY stage.
    # It passes evaluation=None and must never touch profit/score/grade.
    # Keep this compatibility path so the newly merged scheduling pipeline
    # continues to publish independently verified campaign classifications.
    if score.get("evaluation") is None:
        current = p.data_coverage_json if isinstance(p.data_coverage_json, dict) else {}
        previous = current.get("ad_display_v1")
        if (
            isinstance(previous, dict)
            and previous.get("status") == "complete"
            and (ads.get("status") != "complete")
        ):
            return "unchanged"
        if previous == ads:
            return "unchanged"
        updated_ads = dict(current)
        updated_ads["ad_display_v1"] = ads
        p.data_coverage_json = updated_ads
        p.updated_at = datetime.now(UTC)
        return "ad_written"

    # Refuse to publish a snapshot whose manual score changed during the
    # calculation.  The next bounded batch can try again.
    latest_market = target.scalar(
        select(MarketScore)
        .where(
            MarketScore.source_account_ref == key[0],
            MarketScore.store_id == key[1],
            MarketScore.item_id == key[2],
        )
        .limit(1)
    )
    if (latest_market.version if latest_market is not None else 0) != score.get(
        "market_version", 0
    ):
        raise RuntimeError("MARKET_SCORE_CHANGED_DURING_PUBLISH")

    # Preserve configured score-version FK where available; never invent one.
    version_row = target.scalar(
        select(RuleVersion)
        .where(RuleVersion.kind == "performance")
        .order_by(RuleVersion.version.desc())
        .limit(1)
    )
    active_version = version_row.version if version_row is not None else 0
    if active_version != score.get("rule_version"):
        raise RuntimeError("RULE_VERSION_CHANGED_DURING_PUBLISH")

    old = p.data_coverage_json if isinstance(p.data_coverage_json, dict) else {}
    updated = dict(old)
    now = datetime.now(UTC)
    old_authority = old.get("new_products_authority_v2")
    proof = score.get("profit")
    proof_ready = (
        score.get("profit_ready") is True
        and isinstance(proof, dict)
        and proof.get("status") == "scored"
        and proof.get("policy") == "returns_ignored_samples_excluded_sample_ads_included"
        and not proof.get("missing")
    )
    ev = score.get("evaluation")
    facts = score.get("facts") or {}
    if not isinstance(ev, dict) or not isinstance(ev.get("dimensions"), dict):
        return "unverified"

    # Keep the FIRST legacy state for audit and reconciliation.  The complete
    # table is backed up separately before a production --apply run.
    if "new_products_legacy_before_authority_v2" not in updated:
        updated["new_products_legacy_before_authority_v2"] = {
            "score": str(p.score) if p.score is not None else None,
            "grade": p.grade,
            "profit_usd": str(p.profit_usd) if p.profit_usd is not None else None,
            "roi": str(p.roi) if p.roi is not None else None,
            "profit_margin_pct": (
                str(p.profit_margin_pct) if p.profit_margin_pct is not None else None
            ),
            "auto_dimension_scores": old.get("auto_dimension_scores"),
            "first_repaired_at": now.isoformat(),
        }

    # This block is the authoritative persisted evidence on list/detail GET.
    # 85% is a coverage denominator for displaying automatic /10, not an
    # additional factor applied to evaluate().total.
    dims = ev["dimensions"]
    weights = (version_row.config_json or {}).get("weights") if version_row else None
    if not isinstance(weights, dict):
        from .rules import DEFAULT_WEIGHTS

        weights = DEFAULT_WEIGHTS
    points = sum(
        (
            Decimal(str(dims[k])) * Decimal(str(weights[k])) / 100
            for k in ("speed", "ad", "profit", "trust")
            if dims.get(k) is not None
        ),
        Decimal(0),
    )
    covered = sum(
        (
            Decimal(str(weights[k]))
            for k in ("speed", "ad", "profit", "trust")
            if dims.get(k) is not None
        ),
        Decimal(0),
    )
    updated["auto_dimension_scores"] = {
        "source": "new_products_authority_v2",
        "rule_version": active_version,
        "dimensions": {k: dims.get(k) for k in ("speed", "ad", "profit", "trust")},
        "automatic_points": str(points),
        "automatic_weighted_points": str(points),
        "covered_weight_pct": str(covered),
        "missing": list(ev.get("missing") or []),
        "calculated_cutoff_la": cutoff.isoformat(),
    }
    # Full-history revenue, order and ad amounts live in a dedicated, clearly
    # named evidence block.  The performance table's sales_orders/sales_units
    # remain FIRST-14-DAY fields for speed/trust, not lifetime totals.
    updated["new_products_testing_profit_v2"] = {
        **dict(proof or {}),
        "source": "new_products_testing_profit_full_history_v2",
        "through_la": cutoff.isoformat(),
    }
    # Bind the four dimension scores to their actual 14-day facts, so the
    # detail drawer cannot show stale pre-repair figures alongside a new grade.
    saved_fact_fields = (
        "first_wfs_available_date_la",
        "observation_end_la",
        "first_order_day",
        "first_order_date",
        "elapsed_days",
        "effective_orders_14d",
        "valid_orders_14d",
        "valid_units_14d",
        "single_unit_orders_14d",
        "ad_status",
        "ad_spend_usd",
        "ad_clicks",
        "ad_orders",
        "ad_revenue_usd",
        "market_score",
        "roi",
        "gross_margin_pct",
        "profit_usd",
        "sales_amount_usd",
        "sales_units",
        "sales_orders",
        "sp_ad_spend_usd",
        "sem_ad_spend_usd",
        "data_cutoff_la",
        "profit_source",
        "profit_calc_status",
        "profit_calc_missing",
    )
    updated["new_products_score_facts_v2"] = {
        k: (
            facts[k].isoformat()
            if isinstance(facts[k], (date, datetime))
            else str(facts[k])
            if isinstance(facts[k], Decimal)
            else facts[k]
        )
        for k in saved_fact_fields
        if k in facts
    }
    ready = (
        proof_ready
        and ev.get("total") is not None
        and ev.get("grade") in {"S", "A", "B", "C", "D", "Pass"}
    )
    updated["new_products_authority_v2"] = {
        "source": "new_products.testing_profit+scoring.evaluate",
        "policy": "returns_ignored_samples_excluded_sample_ads_included",
        "cutoff_la": cutoff.isoformat(),
        "rule_version": active_version,
        "market_version": score.get("market_version", 0),
        "status": "ready" if ready else "blocked",
        "missing": list(ev.get("missing") or [])
        if proof_ready
        else list(facts.get("profit_calc_missing") or ["profit_unverified"]),
    }
    # Advertising display may be usable while profit/grade is blocked.
    prior_ad = old.get("ad_display_v1")
    if not (isinstance(prior_ad, dict) and prior_ad.get("status") == "complete") or (
        ads.get("status") == "complete"
    ):
        updated["ad_display_v1"] = ads

    # Only independent *normal-sales* profit may populate business SQL fields.
    # The old daily MART ROI is NEVER eligible to be stored as a final ROI.
    p.sample_units = (
        Decimal(str(proof["sample_units"]))
        if isinstance(proof, dict) and proof.get("sample_units") is not None
        else None
    )
    p.profit_usd = Decimal(str(proof["profit_usd"])) if proof_ready else None
    p.roi = Decimal(str(proof["roi"])) if proof_ready else None
    p.profit_margin_pct = Decimal(str(proof["gross_margin_pct"])) if proof_ready else None
    if proof_ready and proof.get("first_order_date"):
        p.first_order_date_la = date.fromisoformat(proof["first_order_date"])
    # The SQL ad_spend_usd now corresponds to full historical SP+SEM cost; its
    # exact window and components are recorded in the authority evidence.
    p.ad_spend_usd = (
        Decimal(str(proof["ad_spend_usd"]))
        if isinstance(proof, dict) and proof.get("ad_spend_usd") is not None
        else None
    )
    if ready:
        total = Decimal(str(ev["total"]))
        if not total.is_finite() or not Decimal(0) <= total <= Decimal(10):
            raise ValueError("AUTHORITATIVE_SCORE_OUT_OF_RANGE")
        p.score = total
        p.grade = ev["grade"]
    else:
        # Quarantine an unverified historical grade: never show it as A/B/S
        # or allow it to authorize a fresh purchase.
        p.score = None
        p.grade = None
    p.rule_version_id = version_row.id if version_row else None
    p.data_status = "available" if ready else "partial"
    p.data_coverage_json = updated
    p.calculated_at = now
    p.updated_at = now
    if p.first_wfs_available_date_la is None and isinstance(
        facts.get("first_wfs_available_date_la"), date
    ):
        p.first_wfs_available_date_la = facts["first_wfs_available_date_la"]
    if p.metric_window_start_la is None and isinstance(
        facts.get("first_wfs_available_date_la"), date
    ):
        p.metric_window_start_la = facts["first_wfs_available_date_la"]
    if p.metric_window_end_la is None and isinstance(facts.get("observation_end_la"), date):
        p.metric_window_end_la = min(facts["observation_end_la"], cutoff)
    return "written" if old_authority is None else "reconciled"


def publish_unified(
    source: Session,
    target: Session,
    *,
    item_ids: set[str] | None = None,
    limit: int = 500,
    cutoff: date | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """One publication plan; used by rule apply, daily tick and local CLI alike.

    Fail-closed if requested results are non-local or explicit permission missing.
    The operations/source session must be read-only; caller opens it accordingly.
    """
    if apply and not permission_to_write():
        raise PermissionError("PR337_UNIFIED_PUBLISH_NOT_AUTHORIZED")
    cutoff = cutoff or (datetime.now(LA).date() - timedelta(days=1))
    product_rows = _eligible_rows(source, item_ids, limit)
    keys = [r["key"] for r in product_rows]
    summary: dict[str, Any] = {
        "dry_run": not apply,
        "cutoff_la": cutoff.isoformat(),
        "products": len(keys),
        "written": 0,
        "frozen": 0,
        "missing_local_registry": 0,
        "incomplete_ads": 0,
        "unverified": 0,
        "samples": [],
    }
    if not keys:
        return summary
    if not apply:
        from .models import NewProductRegistry

        r = NewProductRegistry
        present = {
            (str(x.source_account_ref), str(x.store_id), str(x.item_id))
            for x in target.scalars(
                select(r).where(tuple_(r.source_account_ref, r.store_id, r.item_id).in_(keys))
            ).all()
        }
        summary["missing_local_registry"] = sum(key not in present for key in keys)
    # Reuse the bounded, official-source catalog already used by daily ad evidence.
    # Import inside the function: pr337_daily_pipeline imports _save_one from this module.
    from .pr337_daily_pipeline import load_scoped_campaign_catalog

    catalog, catalog_state, catalog_rows = load_scoped_campaign_catalog(source, cutoff)
    summary["catalog_state"] = catalog_state
    summary["catalog_rows"] = catalog_rows
    for at in range(0, len(keys), BATCH):
        batch = keys[at : at + BATCH]
        score_map = _candidate_scores(source, target, batch, cutoff)
        # WFS start date comes from authoritative locked WFS evidence, not from
        # an assumed listing created timestamp.
        first_dates = {
            key: score_map[key]["facts"].get("first_wfs_available_date_la") for key in batch
        }
        snapshots = load_ad_snapshots(source, batch, first_dates, cutoff, campaign_catalog=catalog)
        for key in batch:
            proof = snapshots[key]
            if proof["status"] != "complete":
                summary["incomplete_ads"] += 1
            if score_map[key]["evaluation"] is None:
                summary["unverified"] += 1
            if not apply and len(keys) <= 4:
                displayed = proof.get("facts") or {}
                summary["samples"].append(
                    {
                        "item_id": key[2],
                        "ad_status": proof["status"],
                        "ad_total_spend_usd": displayed.get("ad_total_spend_usd"),
                        "auto_ad_spend_usd": displayed.get("auto_ad_spend_usd"),
                        "manual_ad_spend_usd": displayed.get("manual_ad_spend_usd"),
                        "score_grade": (score_map[key]["evaluation"] or {}).get("grade"),
                    }
                )
            if apply:
                outcome = _save_one(target, key, proof, score_map[key], cutoff=cutoff)
                summary[outcome] = summary.get(outcome, 0) + 1
        if apply:
            # Commit each bounded batch only after its full computation succeeds;
            # one bad batch never silently publishes half of that batch.
            target.commit()
    return summary


def execute_unified_job(
    *, item_ids: set[str] | None = None, limit: int = 500, apply: bool = False
) -> dict[str, Any]:
    """Open existing source/read and decision/write sessions, no new database."""
    from app.db.session import get_engine

    from .read_source import get_new_product_read_session

    if os.getenv("APP_ENV", "").strip().lower() not in {
        "local",
        "dev",
        "development",
        "production",
    }:
        raise RuntimeError("PR337_APP_ENV_REQUIRED: source/write identity cannot be verified")
    engine = get_engine()
    if apply and os.getenv("APP_ENV", "").strip().lower() in {"local", "dev", "development"}:
        if not local_target_approved(engine.url.database, engine.url.host):
            raise PermissionError("PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID")
    gen = get_new_product_read_session()
    source = next(gen)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as target:
            try:
                return publish_unified(source, target, item_ids=item_ids, limit=limit, apply=apply)
            except Exception:
                target.rollback()
                raise
    finally:
        gen.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified new-product performance publication")
    parser.add_argument(
        "--apply", action="store_true", help="Local write only with explicit feature flag"
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--item-ids", default="", help="Comma-separated Walmart Item IDs")
    args = parser.parse_args()
    item_ids = set(args.item_ids.split(",")) if args.item_ids else None
    if item_ids and any(not x or not x.isdigit() for x in item_ids):
        parser.error("Item IDs must be nonempty digits")
    import json

    print(
        json.dumps(
            execute_unified_job(item_ids=item_ids, limit=args.limit, apply=args.apply),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
