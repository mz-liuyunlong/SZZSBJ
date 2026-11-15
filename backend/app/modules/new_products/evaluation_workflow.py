"""New-product evaluation gate, single-item requests and audited review approvals.

Never writes source FACT/MART, never substitutes NULL with zero, and never changes
finished tracking or purchase records. All writes are to new-product snapshots,
existing new-product snapshot and approval/event tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.api import ApiError

from .evaluation_policy import day, eligible, evaluation_status
from .models import (
    ActionEvent,
    MarketScore,
    NewProductPerformanceCurrent,
    NewProductRegistry,
    RuleVersion,
)
from .scoring import evaluate
from .service import NewProductService

LA = ZoneInfo("America/Los_Angeles")
REVIEW_TYPE = "new_product_evaluation_review"


def _now():
    return datetime.now(UTC)


def _cutoff():
    return datetime.now(LA).date() - timedelta(days=1)


def _error(code: str, status: int, message: str):
    raise ApiError(code=code, status_code=status, message=message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _key(account, store, item):
    return ":".join((str(account), str(store), str(item)))


def _lock(session: Session, account: str, store: str, item: str):
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": "NP_EVALUATION_" + _key(account, store, item)},
    )


def _registry(session, account, store, item, *, lock=False):
    stmt = select(NewProductRegistry).where(
        NewProductRegistry.source_account_ref == account,
        NewProductRegistry.store_id == store,
        NewProductRegistry.item_id == item,
    )
    return session.scalar(stmt.with_for_update() if lock else stmt)


def _performance(session, reg, *, lock=False):
    stmt = select(NewProductPerformanceCurrent).where(
        NewProductPerformanceCurrent.registry_id == reg.id
    )
    return session.scalar(stmt.with_for_update() if lock else stmt)


def _protected(session, reg):
    if reg is None:
        return False
    # A completed tracking or purchase decision always takes precedence.
    return bool(
        session.scalar(
            text("""
        SELECT EXISTS (
          SELECT 1 FROM biz_new_product_tracking_current t
           WHERE t.registry_id=CAST(:id AS uuid) AND t.final_result IS NOT NULL
        ) OR EXISTS (
          SELECT 1 FROM biz_new_product_purchase_applications p
           WHERE p.source_account_ref=:a AND p.store_id=:s AND p.item_id=:i
             AND p.status IN ('submitted','approved')
        ) OR EXISTS (
          SELECT 1 FROM biz_new_product_tracking_decisions d
           WHERE d.source_account_ref=:a AND d.store_id=:s AND d.item_id=:i
             AND d.decision IN ('打品成功','打品失败')
        )
    """),
            {"id": str(reg.id), "a": reg.source_account_ref, "s": reg.store_id, "i": reg.item_id},
        )
    )


def _config(session):
    # Read the exact latest applied version, not a draft rule.
    return NewProductService(session)._config()


def _facts_from_proof(proof: dict, market_score: int | None):
    n = proof.get("orders")
    units = proof.get("units")
    singles = proof.get("singles") if proof.get("trust_proven") else None
    return {
        "first_order_day": proof.get("first_order_day"),
        "effective_orders_14d": n,
        "elapsed_days": proof.get("window_days"),
        "valid_orders_14d": n if proof.get("trust_proven") else None,
        "valid_units_14d": units if proof.get("trust_proven") else None,
        "single_unit_orders_14d": singles,
        "ad_status": proof.get("ad_status") or "unknown",
        "ad_spend_usd": proof.get("ad_spend_usd"),
        "ad_clicks": proof.get("ad_clicks"),
        "ad_orders": proof.get("ad_orders"),
        "ad_revenue_usd": proof.get("ad_sales_usd"),
        "roi": proof.get("roi"),
        "gross_margin_pct": proof.get("margin_pct"),
        "market_score": market_score,
    }


def _verified_proof(perf):
    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    proof = coverage.get("pr337_daily_verified_v1")
    block = coverage.get("auto_dimension_scores")
    if not isinstance(proof, dict) or not isinstance(block, dict):
        return None
    if proof.get("window_start_la") != str(perf.metric_window_start_la):
        return None
    if proof.get("window_end_la") != str(perf.metric_window_end_la):
        return None
    if proof.get("orders") != perf.sales_orders:
        return None
    if str(proof.get("units")) != str(perf.sales_units):
        try:
            if Decimal(str(proof.get("units"))) != perf.sales_units:
                return None
        except (ValueError, TypeError, ArithmeticError):
            return None
    return proof


def _assess(proof: dict, config: dict, version: int, market: int):
    return evaluate(_facts_from_proof(proof, market), config, version)


def _ready(proof, config, version):
    # A test market score does not get persisted; this checks the complete
    # automatic evidence while retaining the existing score algorithm.
    check = _assess(proof, config, version, 0)
    return (
        check.get("grade") is not None and check.get("total") is not None,
        check.get("missing") or [],
    )


def _set_formal(perf, *, source, cutoff, proof, actor):
    coverage = dict(perf.data_coverage_json or {})
    if coverage.get("evaluation_formal_trigger"):
        return False
    coverage["evaluation_formal_trigger"] = {
        "status": "completed",
        "source": source,
        "cutoff_la": str(cutoff),
        "proof_hash": _sha(proof),
        "actor": actor,
        "confirmed_at": _now().isoformat(),
        "rule_version": proof.get("rule_version"),
    }
    perf.data_coverage_json = coverage
    perf.updated_at = _now()
    return True


def publish_after_market(session: Session, account: str, store: str, item: str, market_score: int):
    """Publish a formal result inside the same transaction as the market score.

    Returns False if the product has not completed the automatic evaluation.
    """
    reg = _registry(session, account, store, item, lock=True)
    if reg is None:
        _error("NP_EVAL_NO_REGISTRY", 409, "尚未建立真实新品记录")
    perf = _performance(session, reg, lock=True)
    if perf is None:
        _error("NP_EVAL_NO_EVIDENCE", 409, "暂无已保存的自动评分证据")
    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    trigger = coverage.get("evaluation_formal_trigger")
    if not isinstance(trigger, dict) or trigger.get("status") != "completed":
        _error("NP_EVAL_BEFORE_TRIGGER", 409, "未达到正式测评条件，请先完成自动测评")
    proof = _verified_proof(perf)
    if proof is None or trigger.get("proof_hash") != _sha(proof):
        _error("NP_EVAL_EVIDENCE_CHANGED", 409, "评分证据已变更，需要重新核实")
    if _protected(session, reg):
        _error("NP_EVAL_FROZEN", 409, "商品存在已审批或已冻结的业务结果")
    if perf.grade is not None or perf.score is not None:
        _error("NP_EVAL_RESULT_FROZEN", 409, "已有正式测评结果，须走复核通道")
    config, version = _config(session)
    if trigger.get("rule_version") != proof.get("rule_version"):
        _error("NP_EVAL_RULE_STALE", 409, "自动评分规则版本不一致")
    ev = _assess(proof, config, version, market_score)
    if ev.get("grade") is None or ev.get("total") is None:
        _error(
            "NP_EVAL_INSUFFICIENT_EVIDENCE",
            409,
            "真实指标尚不足以形成完整评级：" + "、".join(ev.get("missing") or []),
        )
    perf.score = Decimal(str(ev["total"]))
    perf.grade = ev["grade"]
    perf.process_status = "assessment_complete"
    coverage = dict(coverage)
    coverage["evaluation_final_snapshot"] = {
        "grade": ev["grade"],
        "total": ev["total"],
        "dimensions": ev["dimensions"],
        "rule_version": version,
        "proof_hash": _sha(proof),
        "market_score": market_score,
        "published_at": _now().isoformat(),
    }
    perf.data_coverage_json = coverage
    perf.updated_at = _now()
    return ev


def _sold_out_proof(session: Session, reg, first: date, cutoff: date):
    """Conservative first-batch sale-out witness, limited to day 1..13.

    Requires consecutive historical positive-to-zero WFS snapshots, no inbound
    increase, and real MART sold units at least as large as the initial batch.
    It deliberately does not interpret a solitary zero-stock snapshot as sold out.
    """
    if first > cutoff or (cutoff - first).days >= 13:
        return None
    rows = (
        session.execute(
            text("""
      SELECT snapshot_date_la AS day, wfs_available_quantity AS qty
        FROM fact_walmart_listing_inventory_daily
       WHERE source_account_ref=:a AND store_id=:s AND item_id=:i
         AND snapshot_date_la BETWEEN :first AND :cutoff
       ORDER BY snapshot_date_la LIMIT 16
    """),
            {
                "a": reg.source_account_ref,
                "s": reg.store_id,
                "i": reg.item_id,
                "first": first,
                "cutoff": cutoff,
            },
        )
        .mappings()
        .all()
    )
    if not rows or rows[0]["day"] != first or rows[0]["qty"] is None:
        return None
    initial = rows[0]["qty"]
    if initial <= 0:
        return None
    prev = initial
    sold = None
    for pos, row in enumerate(rows):
        if row["day"] != first + timedelta(days=pos):
            return None
        qty = row["qty"]
        if qty is None or qty < 0 or qty > prev:
            return None
        prev = qty
        if qty == 0:
            sold = row["day"]
            break
    if sold is None:
        return None
    actual = session.scalar(
        text("""
      SELECT SUM(sales_qty) FROM mart_daily_sales_item_day
       WHERE source_account_ref=:a AND store_id=:s AND item_id=:i
         AND business_date_la BETWEEN :first AND :sold
    """),
        {
            "a": reg.source_account_ref,
            "s": reg.store_id,
            "i": reg.item_id,
            "first": first,
            "sold": sold,
        },
    )
    if actual is None or actual < initial:
        return None
    return {
        "first_quantity": str(initial),
        "sold_day": sold.isoformat(),
        "sold_units": str(actual),
        "source": "WFS_DAILY_HISTORY_AND_MART",
        "days": (sold - first).days + 1,
    }


def finalize_automatic(session: Session, cutoff: date | None = None) -> dict:
    """Run once *inside existing PR337 master task* after evidence publication.

    No second scheduler. A completed trigger freezes its first published window.
    """
    cutoff = cutoff or _cutoff()
    config, version = _config(session)
    rows = session.execute(
        select(NewProductRegistry, NewProductPerformanceCurrent)
        .join(
            NewProductPerformanceCurrent,
            NewProductPerformanceCurrent.registry_id == NewProductRegistry.id,
        )
        .where(NewProductRegistry.is_currently_tagged.is_(True))
        .limit(5000)
    ).all()
    counts = {"checked": 0, "published": 0, "incomplete": 0, "sold_out_verified": 0}
    for reg, perf in rows:
        if perf.grade is not None or perf.score is not None or _protected(session, reg):
            continue
        coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
        if coverage.get("evaluation_formal_trigger"):
            continue
        first = day(perf.first_wfs_available_date_la)
        if not first or first > cutoff:
            continue
        counts["checked"] += 1
        if not (perf.sold_out_evidence_status == "verified" and perf.first_batch_sold_out_date_la):
            witness = _sold_out_proof(session, reg, first, cutoff)
            if witness:
                perf.first_batch_sold_out_date_la = day(witness["sold_day"])
                perf.sold_out_evidence_status = "verified"
                perf.sold_out_evidence_json = witness
                counts["sold_out_verified"] += 1
        ok, source = eligible(
            first_wfs=first,
            cutoff=cutoff,
            sold_status=perf.sold_out_evidence_status,
            sold_day=perf.first_batch_sold_out_date_la,
        )
        if not ok:
            continue
        proof = _verified_proof(perf)
        if not proof:
            counts["incomplete"] += 1
            continue
        # The calendar trigger does not authorize publishing a 1..13-day
        # snapshot merely because 14 calendar dates have now elapsed.
        if source == "auto_14d" and day(proof.get("window_end_la")) != first + timedelta(days=13):
            counts["incomplete"] += 1
            continue
        if source == "auto_sold_out" and day(proof.get("window_end_la")) < day(
            perf.first_batch_sold_out_date_la
        ):
            counts["incomplete"] += 1
            continue
        valid, _missing = _ready(proof, config, version)
        if not valid:
            counts["incomplete"] += 1
            continue
        if _set_formal(perf, source=source, cutoff=cutoff, proof=proof, actor="system"):
            # Market score may have been recorded during an older workflow.
            # Promote it only after all auto evidence is formally verified.
            market = session.scalar(
                select(MarketScore).where(
                    MarketScore.source_account_ref == reg.source_account_ref,
                    MarketScore.store_id == reg.store_id,
                    MarketScore.item_id == reg.item_id,
                )
            )
            if market is not None:
                publish_after_market(
                    session, reg.source_account_ref, reg.store_id, reg.item_id, market.score
                )
            counts["published"] += 1
    # Caller owns transaction; never commit from inside the daily task pipeline.
    return counts


def calculate_once(
    session: Session, account: str, store: str, item: str, actor: str, listing
) -> dict:
    """One synchronous, bounded PR337 calculation for one Item ID. No job table.

    Persist only existing snapshot and audit rows; a proven-but-incomplete
    calculation is reported as incomplete, never as a fabricated final score.
    """
    from .pr337_daily_db import run_daily

    cutoff = _cutoff()
    first = day(getattr(listing, "first_wfs_available_date_la", None))
    if first is None:
        _error("NP_EVAL_FIRST_WFS_REQUIRED", 409, "商品尚未有WFS首次可售日期")
    if first > cutoff:
        _error("NP_EVAL_WINDOW_PENDING", 409, "尚无完整洛杉矶业务日；请次日计算")
    _lock(session, account, store, item)
    reg = _registry(session, account, store, item, lock=True)
    if _protected(session, reg):
        _error("NP_EVAL_FROZEN", 409, "商品已进入采购或打品流程，不允许重新评分")
    if reg is not None:
        perf = _performance(session, reg, lock=True)
        if perf is not None:
            if perf.grade is not None or perf.score is not None:
                _error("NP_EVAL_RESULT_FROZEN", 409, "已有最终评级，请走测评复核")
            cov = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
            if cov.get("evaluation_formal_trigger"):
                _error("NP_EVAL_ALREADY_COMPLETE", 409, "自动评分已完成，请进行市场评分")
    # The exact identity is constrained in the SQL candidate query, before LIMIT.
    outcome = run_daily(
        session, apply=True, cutoff_la=cutoff, identity_filter=(account, store, item)
    )
    # The PR337 publisher uses SQL text updates. Refresh identity-map snapshots
    # so the same request evaluates the just-persisted evidence, not stale ORM state.
    session.expire_all()
    reg = _registry(session, account, store, item, lock=True)
    perf = _performance(session, reg, lock=True) if reg else None
    if perf is None or _protected(session, reg):
        raise ValueError("NP_EVAL_SNAPSHOT_UNAVAILABLE")
    proof = _verified_proof(perf)
    outcomes = outcome.get("outcomes", {})
    succeeded = int(outcomes.get("written", 0)) + int(outcomes.get("unchanged", 0)) == 1
    if not succeeded:
        # Never approve a stale saved proof when today's MART watermark, stock,
        # FACT or the guarded persistence writer rejected this invocation.
        missing = [
            str(k)
            for k, v in outcomes.items()
            if v and k not in {"registry_created", "performance_created", "retagged"}
        ] or ["SOURCE_NOT_READY"]
    elif proof is None:
        missing = ["MART_WFS_EVIDENCE_NOT_VERIFIED"]
    else:
        config, version = _config(session)
        valid, missing = _ready(proof, config, version)
    status = "incomplete"
    if succeeded and proof is not None and valid:
        if _set_formal(perf, source="manual", cutoff=cutoff, proof=proof, actor=actor):
            market = session.scalar(
                select(MarketScore).where(
                    MarketScore.source_account_ref == account,
                    MarketScore.store_id == store,
                    MarketScore.item_id == item,
                )
            )
            if market is not None:
                publish_after_market(session, account, store, item, market.score)
        status = "completed"
    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=account,
            store_id=store,
            item_id=item,
            event_type="evaluation_completed" if status == "completed" else "evaluation_incomplete",
            actor_id=actor,
            payload_json={
                "trigger": "manual",
                "cutoff_la": str(cutoff),
                "status": status,
                "missing": missing if status != "completed" else [],
                "outcomes": outcome.get("outcomes", {}),
            },
            created_at=_now(),
        )
    )
    session.commit()
    return {
        "status": status,
        "trigger": "manual",
        "item_id": item,
        "cutoff_la": str(cutoff),
        "missing": missing if status != "completed" else [],
    }


def recheck_once(session: Session, accounts, approval_id: UUID, actor: str) -> dict:
    # One synchronous approved source recheck, no new table.
    approval = (
        session.execute(
            text("""SELECT * FROM app_approval_requests
         WHERE id=:id AND approval_type=:kind"""),
            {"id": approval_id, "kind": REVIEW_TYPE},
        )
        .mappings()
        .first()
    )
    if approval is None or approval["source_account_ref"] not in accounts:
        _error("NP_EVAL_APPROVAL_NOT_FOUND", 404, "申请不存在或没有数据权限")
    if (
        approval["status"] != "approved"
        or approval["snapshot"].get("review_reason_type") == "special_exception"
    ):
        _error("NP_EVAL_RECHECK_NOT_APPROVED", 409, "仅已批准纠错支持重新核算")
    snap = approval["snapshot"]
    a, s, i = snap["source_account_ref"], snap["store_id"], snap["item_id"]
    _lock(session, a, s, i)
    reg = _registry(session, a, s, i, lock=True)
    if not reg or str(reg.id) != str(approval["business_ref"]) or _protected(session, reg):
        _error("NP_EVAL_RECHECK_LOCKED", 409, "后续业务状态不允许重核")
    perf = _performance(session, reg, lock=True)
    pending = (perf.data_coverage_json or {}).get("evaluation_recheck_required") if perf else None
    if (
        not isinstance(pending, dict)
        or pending.get("approval_id") != str(approval_id)
        or pending.get("status") != "awaiting_verified_source_correction"
    ):
        _error("NP_EVAL_RECHECK_NO_PENDING", 409, "未找到有效的纠错复核授权")
    if str(perf.score) != str(snap["score"]) or perf.grade != snap["grade"]:
        _error("NP_EVAL_RECHECK_STALE", 409, "原始评级已变化")
    request = {
        "source_account_ref": a,
        "store_id": s,
        "item_id": i,
        "requested_by": actor,
        "result_json": {"approval_id": str(approval_id)},
    }
    return _execute_approved_recheck(session, request, str(uuid4()))


def _execute_approved_recheck(session: Session, job, job_id: str):
    """Read-only re-extraction followed by guarded write of an *approved* revision."""
    from .pr337_daily_db import run_daily

    a, s, i = job["source_account_ref"], job["store_id"], job["item_id"]
    prior = job["result_json"] if isinstance(job["result_json"], dict) else {}
    approval_id = prior.get("approval_id")
    if not approval_id:
        raise ValueError("APPROVAL_ID_MISSING")
    approval = (
        session.execute(
            text("""
      SELECT * FROM app_approval_requests WHERE id=CAST(:id AS uuid) AND approval_type=:kind
    """),
            {"id": approval_id, "kind": REVIEW_TYPE},
        )
        .mappings()
        .first()
    )
    if not approval or approval["status"] != "approved":
        raise ValueError("CORRECTION_APPROVAL_NOT_ACTIVE")
    reg = _registry(session, a, s, i, lock=True)
    perf = _performance(session, reg, lock=True) if reg else None
    if not perf or _protected(session, reg):
        raise ValueError("CORRECTION_TARGET_FROZEN")
    previous = dict(perf.data_coverage_json or {})
    pending = previous.get("evaluation_recheck_required")
    if (
        not isinstance(pending, dict)
        or pending.get("approval_id") != approval_id
        or pending.get("status") != "awaiting_verified_source_correction"
    ):
        raise ValueError("CORRECTION_REQUEST_CHANGED")
    old_grade, old_score = perf.grade, str(perf.score)
    if old_grade != approval["snapshot"]["grade"] or old_score != str(
        approval["snapshot"]["score"]
    ):
        raise ValueError("ORIGINAL_GRADE_CHANGED")
    old_proof = _verified_proof(perf)
    if old_proof is None:
        raise ValueError("ORIGINAL_PROOF_NOT_VERIFIED")
    result = run_daily(
        session, apply=False, cutoff_la=_cutoff(), identity_filter=(a, s, i), recheck_source=True
    )
    sources = result.get("recheck_proofs") or []
    if len(sources) != 1:
        raise ValueError("VERIFIED_RECHECK_SOURCE_UNAVAILABLE")
    new_proof = sources[0]
    cfg, version = _config(session)
    active_rule = session.scalar(
        select(RuleVersion)
        .where(RuleVersion.kind == "performance")
        .order_by(RuleVersion.version.desc())
        .limit(1)
    )
    market = session.scalar(
        select(MarketScore).where(
            MarketScore.source_account_ref == a, MarketScore.store_id == s, MarketScore.item_id == i
        )
    )
    if market is None:
        raise ValueError("MARKET_SCORE_NOT_SAVED")
    ev = _assess(new_proof, cfg, version, market.score)
    if ev.get("grade") is None or ev.get("total") is None:
        raise ValueError("RECHECK_EVIDENCE_INCOMPLETE:" + ",".join(ev.get("missing", []))[:250])
    if (
        _sha(old_proof) == _sha(new_proof)
        and old_grade == ev["grade"]
        and Decimal(old_score) == Decimal(ev["total"])
    ):
        raise ValueError("NO_VERIFIED_SOURCE_OR_RULE_CHANGE")
    revisions = list(previous.get("evaluation_revision_history") or [])
    if len(revisions) > 19:
        raise ValueError("EVALUATION_REVISION_HISTORY_CAP_REQUIRES_ARCHIVE")
    now = _now()
    revisions.append(
        {
            "approval_id": approval_id,
            "job_id": job_id,
            "original": {
                "grade": old_grade,
                "score": old_score,
                "proof": old_proof,
                "rule_version": old_proof.get("rule_version"),
            },
            "revised": {
                "grade": ev["grade"],
                "score": ev["total"],
                "proof": new_proof,
                "rule_version": version,
            },
            "reviewer": approval["reviewed_by"],
            "executed_by": job["requested_by"],
            "executed_at": now.isoformat(),
        }
    )
    block = dict(previous.get("auto_dimension_scores") or {})
    block.update(
        {
            "dimensions": new_proof["dimensions"],
            "rule_version": version,
            "automatic_points": new_proof["automatic_points"],
            "covered_weight_pct": new_proof["covered_weight_pct"],
            "cutoff_la": new_proof["cutoff_la"],
            "window_start_la": new_proof["window_start_la"],
            "window_end_la": new_proof["window_end_la"],
            "source": "approved_evaluation_recheck",
        }
    )
    previous["auto_dimension_scores"] = block
    previous["pr337_daily_verified_v1"] = new_proof
    previous["evaluation_revision_history"] = revisions
    previous["evaluation_final_snapshot"] = {
        "grade": ev["grade"],
        "total": ev["total"],
        "dimensions": ev["dimensions"],
        "rule_version": version,
        "proof_hash": _sha(new_proof),
        "market_score": market.score,
        "published_at": now.isoformat(),
        "revised_with_approval_id": approval_id,
    }
    previous["evaluation_recheck_required"] = {
        **pending,
        "status": "completed",
        "completed_at": now.isoformat(),
        "job_id": job_id,
        "revised_grade": ev["grade"],
        "revised_score": ev["total"],
    }
    previous["evaluation_formal_trigger"] = {
        "status": "completed",
        "source": "approved_recheck",
        "actor": job["requested_by"],
        "cutoff_la": new_proof["cutoff_la"],
        "proof_hash": _sha(new_proof),
        "rule_version": version,
        "confirmed_at": now.isoformat(),
    }
    perf.data_coverage_json = previous
    perf.rule_version_id = active_rule.id if active_rule is not None else None
    perf.first_wfs_available_date_la = day(new_proof["window_start_la"])
    perf.first_order_date_la = day(new_proof.get("first_order_date"))
    perf.data_status = "available"
    perf.score = Decimal(str(ev["total"]))
    perf.grade = ev["grade"]
    perf.calculated_at = now
    perf.metric_window_start_la = day(new_proof["window_start_la"])
    perf.metric_window_end_la = day(new_proof["window_end_la"])
    perf.sales_orders = new_proof["orders"]
    perf.sales_units = Decimal(str(new_proof["units"]))
    for field, key in (
        ("profit_usd", "profit_usd"),
        ("roi", "roi"),
        ("profit_margin_pct", "margin_pct"),
        ("ad_spend_usd", "ad_spend_usd"),
        ("ad_clicks", "ad_clicks"),
        ("ad_sales_usd", "ad_sales_usd"),
        ("sales_amount_usd", "sales_amount_usd"),
    ):
        value = new_proof.get(key)
        setattr(
            perf,
            field,
            Decimal(str(value)) if value is not None and field != "ad_clicks" else value,
        )
    perf.updated_at = now
    session.execute(
        text("""
      INSERT INTO app_approval_events(id,approval_id,event_type,actor_id,note,detail,created_at)
      VALUES(CAST(:id AS uuid),CAST(:aid AS uuid),'recalculated',:actor,:note,
             CAST(:detail AS jsonb),:now)
    """),
        {
            "id": str(uuid4()),
            "aid": approval_id,
            "actor": job["requested_by"],
            "note": "按已批准纠错申请重核真实数据",
            "detail": _json(
                {
                    "original_grade": old_grade,
                    "original_score": old_score,
                    "new_grade": ev["grade"],
                    "new_score": ev["total"],
                    "job_id": job_id,
                }
            ),
            "now": now,
        },
    )
    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=a,
            store_id=s,
            item_id=i,
            event_type="evaluation_recheck_completed",
            actor_id=job["requested_by"],
            payload_json={
                "approval_id": approval_id,
                "job_id": job_id,
                "before": old_grade,
                "after": ev["grade"],
            },
            created_at=now,
        )
    )
    session.commit()
    return {"execution_id": job_id, "status": "completed", "grade": ev["grade"]}


def calculation_status(session, accounts, account, store, item):
    # Current assessment status is derived from the existing persisted snapshot.
    if account not in accounts:
        _error("NP_EVAL_NO_SCOPE", 404, "无权读取当前商品")
    reg = _registry(session, account, store, item)
    perf = _performance(session, reg) if reg else None
    if perf is None:
        return {"status": "none", "item_id": item}
    cov = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    trigger = cov.get("evaluation_formal_trigger")
    return {
        "status": "completed"
        if isinstance(trigger, dict) and trigger.get("status") == "completed"
        else "incomplete",
        "item_id": item,
    }


def submit_review(
    session: Session, accounts, account, store, item, actor, reason_type, reason, evidence
):
    if account not in accounts:
        _error("NP_EVAL_NO_SCOPE", 404, "无权提交当前商品")
    if len(reason.strip()) < 5:
        _error("NP_EVAL_REASON_SHORT", 422, "申请说明至少5个字符")
    _lock(session, account, store, item)
    reg = _registry(session, account, store, item, lock=True)
    if not reg:
        _error("NP_EVAL_NO_REGISTRY", 409, "商品无正式测评记录")
    perf = _performance(session, reg, lock=True)
    if _protected(session, reg):
        _error("NP_EVAL_REVIEW_DOWNSTREAM_LOCK", 409, "已有后续业务记录，测评复核不可更改其历史")
    if not perf or perf.grade not in ("D", "Pass") or perf.score is None:
        _error("NP_EVAL_NOT_FAILED", 409, "只有已形成真实D/Pass评级的商品可申请复核")
    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    if coverage.get("evaluation_manual_exception"):
        _error("NP_EVAL_EXCEPTION_ALREADY_GRANTED", 409, "当前商品已有批准的人工特批")
    recheck = coverage.get("evaluation_recheck_required")
    if isinstance(recheck, dict) and recheck.get("status") == "awaiting_verified_source_correction":
        _error("NP_EVAL_RECHECK_ALREADY_APPROVED", 409, "已批准纠错等待重算，不能重复申请")
    pending = session.scalar(
        text("""
       SELECT id::text FROM app_approval_requests
        WHERE approval_type=:kind AND business_ref=:ref
          AND status IN ('submitted','info_required') LIMIT 1
    """),
        {"kind": REVIEW_TYPE, "ref": str(reg.id)},
    )
    if pending:
        _error("NP_EVAL_REVIEW_PENDING", 409, "该商品已有进行中的测评复核")
    auto = (
        coverage.get("auto_dimension_scores")
        if isinstance(coverage.get("auto_dimension_scores"), dict)
        else {}
    )
    market = session.scalar(
        select(MarketScore).where(
            MarketScore.source_account_ref == account,
            MarketScore.store_id == store,
            MarketScore.item_id == item,
        )
    )
    snapshot = {
        "source_account_ref": account,
        "store_id": store,
        "item_id": item,
        "registry_id": str(reg.id),
        "grade": perf.grade,
        "score": str(perf.score),
        "auto_dimensions": auto.get("dimensions"),
        "market_score": market.score if market is not None else None,
        "first_wfs_available_date_la": str(perf.first_wfs_available_date_la)
        if perf.first_wfs_available_date_la
        else None,
        "observation_cutoff_la": auto.get("cutoff_la"),
        "rule_version_id": str(perf.rule_version_id) if perf.rule_version_id else None,
        "calculated_at": perf.calculated_at.isoformat() if perf.calculated_at else None,
        "review_reason_type": reason_type,
        "proof_hash": _sha(perf.data_coverage_json or {}),
        "approval_policy": {"required_steps": 1},
    }
    approval_id = str(uuid4())
    now = _now()
    session.execute(
        text("""
      INSERT INTO app_approval_requests
      (id,approval_type,business_ref,source_account_ref,applicant_id,
       title,reason,evidence,status,risk_level,snapshot,snapshot_hash,version,submitted_at,updated_at)
      VALUES(CAST(:id AS uuid),:kind,:ref,:account,:actor,
       :title,:reason,:evidence,'submitted','medium',CAST(:snapshot AS jsonb),:sha,1,:now,:now)
    """),
        {
            "id": approval_id,
            "kind": REVIEW_TYPE,
            "ref": str(reg.id),
            "account": account,
            "actor": actor,
            "title": "新品测评复核 · " + item,
            "reason": reason.strip(),
            "evidence": evidence or None,
            "snapshot": _json(snapshot),
            "sha": _sha(snapshot),
            "now": now,
        },
    )
    session.execute(
        text("""
      INSERT INTO app_approval_events(id,approval_id,event_type,actor_id,note,detail,created_at)
      VALUES(CAST(:id AS uuid),CAST(:aid AS uuid),'submitted',:actor,:note,
             CAST(:detail AS jsonb),:now)
    """),
        {
            "id": str(uuid4()),
            "aid": approval_id,
            "actor": actor,
            "note": reason.strip(),
            "detail": _json({"reason_type": reason_type}),
            "now": now,
        },
    )
    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=account,
            store_id=store,
            item_id=item,
            event_type="evaluation_review_submitted",
            actor_id=actor,
            payload_json={"approval_id": approval_id, "reason_type": reason_type},
            created_at=now,
        )
    )
    session.commit()
    return {"application_id": approval_id, "status": "submitted", "version": 1}


def decide_review(session: Session, accounts, approval_id: UUID, actor, decision, reason, version):
    if decision not in ("approved", "rejected"):
        _error("NP_EVAL_DECISION_INVALID", 422, "不支持的审批操作")
    if len(reason.strip()) < 5:
        _error("NP_EVAL_DECISION_REASON", 422, "审批说明至少5个字符")
    row = (
        session.execute(
            text("""
      SELECT * FROM app_approval_requests WHERE id=:id AND approval_type=:kind FOR UPDATE
    """),
            {"id": approval_id, "kind": REVIEW_TYPE},
        )
        .mappings()
        .first()
    )
    if not row or row["source_account_ref"] not in accounts:
        _error("NP_EVAL_REVIEW_NOT_FOUND", 404, "找不到可访问的测评复核申请")
    if row["status"] != "submitted" or row["version"] != version:
        _error("NP_EVAL_REVIEW_CONFLICT", 409, "申请状态已变化，请刷新")
    if row["applicant_id"] == actor:
        _error("NP_EVAL_SELF_REVIEW", 403, "不能审批自己提交的申请")
    snap = row["snapshot"]
    reg = session.scalar(
        select(NewProductRegistry)
        .where(NewProductRegistry.id == UUID(row["business_ref"]))
        .with_for_update()
    )
    if reg is None or reg.source_account_ref != row["source_account_ref"]:
        _error("NP_EVAL_REVIEW_REGISTRY_CHANGED", 409, "商品身份已变化")
    perf = _performance(session, reg, lock=True)
    if _protected(session, reg):
        _error(
            "NP_EVAL_REVIEW_DOWNSTREAM_LOCK", 409, "商品已进入后续业务流程，不能审批修改测评依据"
        )
    if not perf or perf.grade != snap["grade"] or str(perf.score) != str(snap["score"]):
        _error("NP_EVAL_REVIEW_STALE", 409, "评级已变化，须重新申请")
    if _sha(perf.data_coverage_json or {}) != snap.get("proof_hash"):
        _error("NP_EVAL_REVIEW_EVIDENCE_CHANGED", 409, "原始评分证据已变化，请重新核验")
    now = _now()
    updated = session.execute(
        text("""
       UPDATE app_approval_requests SET status=:status,version=version+1,
              reviewed_by=:actor,reviewed_at=:now,review_note=:note,updated_at=:now
        WHERE id=:id AND status='submitted' AND version=:version
    """),
        {
            "id": approval_id,
            "status": decision,
            "actor": actor,
            "now": now,
            "note": reason.strip(),
            "version": version,
        },
    )
    if updated.rowcount != 1:
        _error("NP_EVAL_REVIEW_CONFLICT", 409, "并发审核冲突")
    session.execute(
        text("""
      INSERT INTO app_approval_events(id,approval_id,event_type,actor_id,note,detail,created_at)
      VALUES(CAST(:id AS uuid),:aid,:decision,:actor,:note,CAST(:detail AS jsonb),:now)
    """),
        {
            "id": str(uuid4()),
            "aid": approval_id,
            "decision": decision,
            "actor": actor,
            "note": reason.strip(),
            "detail": _json(
                {
                    "type": snap["review_reason_type"],
                    "original_grade": snap["grade"],
                    "original_score": snap["score"],
                }
            ),
            "now": now,
        },
    )
    coverage = dict(perf.data_coverage_json or {})
    if decision == "approved":
        if snap["review_reason_type"] == "special_exception":
            # Business exception is not a change to the original D/Pass grade.
            coverage["evaluation_manual_exception"] = {
                "approval_id": str(approval_id),
                "reviewer": actor,
                "reviewed_at": now.isoformat(),
                "review_reason": reason.strip(),
                "original_grade": snap["grade"],
                "original_score": snap["score"],
            }
        else:
            # Do not overwrite source evidence or grade before a verified repair.
            coverage["evaluation_recheck_required"] = {
                "approval_id": str(approval_id),
                "reason_type": snap["review_reason_type"],
                "reviewed_by": actor,
                "reviewed_at": now.isoformat(),
                "original_grade": snap["grade"],
                "original_score": snap["score"],
                "status": "awaiting_verified_source_correction",
            }
        perf.data_coverage_json = coverage
        perf.updated_at = now
    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=reg.source_account_ref,
            store_id=reg.store_id,
            item_id=reg.item_id,
            event_type="evaluation_review_" + decision,
            actor_id=actor,
            payload_json={
                "approval_id": str(approval_id),
                "reason_type": snap["review_reason_type"],
            },
            created_at=now,
        )
    )
    session.commit()
    return {
        "id": str(approval_id),
        "status": decision,
        "version": version + 1,
        "outcome": "manual_exception"
        if decision == "approved" and snap["review_reason_type"] == "special_exception"
        else "needs_source_recheck"
        if decision == "approved"
        else "rejected",
    }


def decorate_page(session: Session, data: dict) -> dict:
    """One bounded per-page lookup; no raw tables or N+1 scoring in a GET."""
    items = data.get("items") or []
    if not items:
        return data
    wants = []
    for entry in items:
        listing_row = entry.get("listing") or {}
        if all(listing_row.get(k) for k in ("source_account_ref", "store_id", "item_id")):
            wants.append(
                {
                    "a": listing_row["source_account_ref"],
                    "s": listing_row["store_id"],
                    "i": listing_row["item_id"],
                }
            )
    if not wants:
        return data
    records = (
        session.execute(
            text("""
      WITH wants AS (
       SELECT a,s,i FROM jsonb_to_recordset(CAST(:wants AS jsonb)) AS j(a text,s text,i text)
      )
      SELECT w.a,w.s,w.i,r.id AS registry_id,
             p.first_wfs_available_date_la,p.first_batch_sold_out_date_la,
             p.sold_out_evidence_status,p.score,p.grade,p.data_coverage_json,
             r.listing_date_la,
             (SELECT a.status FROM app_approval_requests a
               WHERE a.approval_type=:kind AND a.business_ref=r.id::text
               ORDER BY a.submitted_at DESC,a.id DESC LIMIT 1) AS review_status,
             (SELECT a.id::text FROM app_approval_requests a
               WHERE a.approval_type=:kind AND a.business_ref=r.id::text
               ORDER BY a.submitted_at DESC,a.id DESC LIMIT 1) AS review_id
      FROM wants w LEFT JOIN biz_new_product_registry r
       ON r.source_account_ref=w.a AND r.store_id=w.s AND r.item_id=w.i
      LEFT JOIN biz_new_product_performance_current p ON p.registry_id=r.id
    """),
            {"wants": _json(wants), "kind": REVIEW_TYPE},
        )
        .mappings()
        .all()
    )
    by_key = {(r["a"], r["s"], r["i"]): r for r in records}
    for entry in items:
        listing_row = entry.get("listing") or {}
        key = (
            listing_row.get("source_account_ref"),
            listing_row.get("store_id"),
            listing_row.get("item_id"),
        )
        r = by_key.get(key)
        if not r:
            continue
        coverage = r["data_coverage_json"] if isinstance(r["data_coverage_json"], dict) else {}
        listing_date = r["listing_date_la"] or listing_row.get("launch_date_cn")
        status = evaluation_status(
            listing_date=listing_date,
            first_wfs=r["first_wfs_available_date_la"]
            or listing_row.get("first_wfs_available_date_la"),
            coverage=coverage,
            grade=r["grade"],
            total=r["score"],
        )
        entry["evaluation_status"] = status
        # In hybrid local mode the list may read source evidence through a
        # separate read session. The local, audited final evaluation is the
        # authority for evaluation-only columns; never promote a provisional
        # remote score into a formal grade.
        if r["grade"] is not None and r["score"] is not None:
            final = coverage.get("evaluation_final_snapshot")
            if isinstance(final, dict) and final.get("grade") == r["grade"]:
                ev = entry.get("evaluation")
                if isinstance(ev, dict):
                    ev["grade"] = r["grade"]
                    ev["total"] = str(r["score"])
                    ev["rule_version"] = final.get("rule_version", ev.get("rule_version", 0))
                    ev["observation_state"] = "scored"
                    if isinstance(final.get("dimensions"), dict):
                        ev["dimensions"] = dict(final["dimensions"])
                entry.setdefault("facts", {})["market_score"] = final.get("market_score")
        entry["evaluation_review_status"] = r["review_status"]
        entry["evaluation_review_id"] = r["review_id"]
        # Expose approved exception separately; never impersonate S/A/B/C.
        entry["evaluation_manual_exception"] = bool(coverage.get("evaluation_manual_exception"))
        entry["evaluation_recheck_required"] = bool(
            isinstance(coverage.get("evaluation_recheck_required"), dict)
            and coverage["evaluation_recheck_required"].get("status")
            == "awaiting_verified_source_correction"
        )
        facts = entry.get("facts") or {}
        facts["sold_out_evidence_status"] = r["sold_out_evidence_status"]
        facts["first_batch_sold_out_date_la"] = (
            str(r["first_batch_sold_out_date_la"]) if r["first_batch_sold_out_date_la"] else None
        )
        formal = coverage.get("evaluation_formal_trigger")
        facts["evaluation_trigger_source"] = (
            formal.get("source") if isinstance(formal, dict) else None
        )
        facts["evaluation_trigger_status"] = (
            formal.get("status") if isinstance(formal, dict) else None
        )
        entry["facts"] = facts
    return data
