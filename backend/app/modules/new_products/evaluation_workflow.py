"""New-product evaluation gate, single-item requests and audited review approvals.

Never writes source FACT/MART, never substitutes NULL with zero, and never changes
finished tracking or purchase records. All writes are to new-product snapshots,
existing new-product snapshot and approval/event tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, tuple_
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


def _stored_grade_matches_snapshot(grade, stored_total, snapshot):
    """Match an exact JSONB score to a PostgreSQL NUMERIC(10,4) score.

    Preserve grade identity and reject malformed/non-finite values. Do not use
    a permissive tolerance, because it could accept an actual changed score.
    """
    if not isinstance(snapshot, dict) or grade is None or stored_total is None:
        return False
    if snapshot.get("grade") != grade or snapshot.get("total") is None:
        return False
    try:
        exact = Decimal(str(snapshot["total"]))
        persisted = Decimal(str(stored_total))
        if not exact.is_finite() or not persisted.is_finite():
            return False
        return persisted == exact.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError, TypeError):
        return False


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
    authority = coverage.get("new_products_authority_v2")
    block = coverage.get("auto_dimension_scores")
    facts = coverage.get("new_products_score_facts_v2")
    if isinstance(authority, dict):
        if not (
            isinstance(block, dict)
            and block.get("source") == "new_products_authority_v2"
            and isinstance(facts, dict)
            and authority.get("rule_version") == block.get("rule_version")
            and authority.get("cutoff_la") == block.get("calculated_cutoff_la")
            and day(facts.get("first_wfs_available_date_la"))
            == day(perf.first_wfs_available_date_la)
        ):
            return None
        dimensions = block.get("dimensions")
        if not isinstance(dimensions, dict):
            return None
        zero = facts.get("zero_sales_verified") is True
        ad_excluded = facts.get("ad_status") == "not_run"
        if any(dimensions.get(name) is None for name in ("speed", "profit", "trust")) or (
            dimensions.get("ad") is None and not ad_excluded
        ):
            return None
        profit = coverage.get("new_products_testing_profit_v2")
        if not zero and not (
            isinstance(profit, dict)
            and profit.get("status") == "scored"
            and profit.get("policy") == "returns_ignored_samples_excluded_sample_ads_included"
            and not profit.get("missing")
        ):
            return None
        return {
            "__source": "new_products_authority_v2",
            "facts": facts,
            "dimensions": dimensions,
            "rule_version": block.get("rule_version"),
            "market_version": authority.get("market_version"),
            "window_start_la": str(perf.first_wfs_available_date_la),
            "window_end_la": str(
                min(
                    day(facts.get("observation_end_la")) or day(perf.metric_window_end_la),
                    day(authority["cutoff_la"]),
                )
            ),
            "authority_cutoff_la": authority.get("cutoff_la"),
        }
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
    if proof.get("__source") == "new_products_authority_v2":
        facts = dict(proof["facts"])
        facts["market_score"] = market
        return evaluate(facts, config, version)
    return evaluate(_facts_from_proof(proof, market), config, version)


def _ready(proof, config, version):
    # A test market score does not get persisted; this checks the complete
    # automatic evidence while retaining the existing score algorithm.
    if (
        proof.get("__source") == "new_products_authority_v2"
        and proof.get("rule_version") != version
    ):
        return False, ["自动评分规则版本已变化，请重新计算"]
    check = _assess(proof, config, version, 0)
    missing = check.get("missing") or []
    if proof.get("__source") == "new_products_authority_v2":
        for name, saved in proof["dimensions"].items():
            actual = check.get("dimensions", {}).get(name)
            if saved is None and actual is None:
                continue
            try:
                if abs(Decimal(str(saved)) - Decimal(str(actual))) > Decimal("0.02"):
                    return False, ["自动评分与保存证据不一致：" + name]
            except (ValueError, ArithmeticError, TypeError):
                return False, ["自动评分证据无法验证：" + name]
    return check.get("grade") is not None and check.get("total") is not None, missing


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


def publish_after_market(
    session: Session,
    account: str,
    store: str,
    item: str,
    market_score: int,
    market_version: int | None = None,
    risk_conditions: list[str] | None = None,
):
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
    marker = coverage.get("evaluation_grade_confirmation_v1")
    pending = isinstance(marker, dict) and marker.get("status") == "pending"
    frozen = coverage.get("evaluation_final_snapshot")
    if _protected(session, reg):
        _error("NP_EVAL_FROZEN", 409, "商品存在已审批或已冻结的业务结果")
    if pending:
        if not isinstance(frozen, dict) or market_version is None or not frozen.get("proof_hash"):
            _error(
                "NP_EVAL_PENDING_SNAPSHOT",
                409,
                "待确认评分的原始快照不完整",
            )
        if coverage.get("operator_assessment_v1") is not None:
            _error(
                "NP_EVAL_PENDING_ASSESSED",
                409,
                "已有人工测评结论，不能修改市场评分",
            )
        if marker.get("market_version") != market_version - 1:
            _error(
                "NP_EVAL_PENDING_MARKET_VERSION",
                409,
                "市场评分版本与待确认记录不一致，请刷新后重试",
            )
        if marker.get("rule_version") != frozen.get("rule_version"):
            _error(
                "NP_EVAL_PENDING_RULE_VERSION",
                409,
                "待确认评分的规则版本不一致",
            )
        if not _stored_grade_matches_snapshot(perf.grade, perf.score, frozen):
            _error(
                "NP_EVAL_PENDING_BASE_CHANGED",
                409,
                "原始计算分数或等级已变化，禁止覆盖",
            )
        # The original proof hash belongs to its publication.
        # On a pending market edit the saved authority market version changes.
        # The source, cutoff, and four automatic dimensions are checked below.
        authority = coverage.get("new_products_authority_v2")
        saved = frozen.get("dimensions")
        current = proof.get("dimensions") if isinstance(proof, dict) else None
        if (
            not isinstance(proof, dict)
            or proof.get("__source") != "new_products_authority_v2"
            or not isinstance(authority, dict)
            or authority.get("market_version") != marker.get("market_version")
            or not isinstance(saved, dict)
            or not isinstance(current, dict)
        ):
            _error("NP_EVAL_PENDING_EVIDENCE", 409, "待确认自动评分证据无法核实")
        for dimension in ("speed", "ad", "profit", "trust"):
            a, b = saved.get(dimension), current.get(dimension)
            try:
                matched = (a is None and b is None) or (
                    a is not None
                    and b is not None
                    and abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal("0.02")
                )
            except (ArithmeticError, ValueError, TypeError):
                matched = False
            if not matched:
                _error("NP_EVAL_PENDING_EVIDENCE", 409, "自动评分维度已变化，须复核")
    else:
        if proof is None or trigger.get("proof_hash") != _sha(proof):
            _error("NP_EVAL_EVIDENCE_CHANGED", 409, "评分证据已变更，需要重新核实")
        if perf.grade is not None or perf.score is not None:
            _error("NP_EVAL_RESULT_FROZEN", 409, "已有正式测评结果，须走复核通道")
    config, version = _config(session)
    if trigger.get("rule_version") != proof.get("rule_version"):
        _error("NP_EVAL_RULE_STALE", 409, "自动评分规则版本不一致")
    verified, missing = _ready(proof, config, version)
    if not verified:
        _error(
            "NP_EVAL_INSUFFICIENT_EVIDENCE",
            409,
            "自动评分证据不完整：" + "、".join(missing),
        )
    ev = _assess(proof, config, version, market_score)
    if ev.get("grade") is None or ev.get("total") is None:
        _error(
            "NP_EVAL_INSUFFICIENT_EVIDENCE",
            409,
            "真实指标尚不足以形成完整评级：" + "、".join(ev.get("missing") or []),
        )
    if pending:
        coverage = {
            key: value for key, value in coverage.items() if key != "evaluation_final_snapshot"
        }
    from .risk_finalization import resolve_final_risks

    selected = risk_conditions
    if selected is None:
        archived = coverage.get("market_risks_frozen_v1")
        if isinstance(archived, dict):
            selected = archived.get("conditions")
    try:
        risk_record, risk_display = resolve_final_risks(
            coverage=coverage,
            config=config,
            rule_version=version,
            base_grade=ev["grade"],
            manual_selected=selected,
            cutoff=day(proof.get("authority_cutoff_la")) or day(proof.get("window_end_la")),
            first_wfs=perf.first_wfs_available_date_la,
        )
    except (ValueError, TypeError, KeyError) as exc:
        _error("NP_RISK_FINALIZATION_BLOCKED", 409, str(exc))

    ev["grade"] = risk_record["effective_grade"]
    perf.score = Decimal(str(ev["total"]))
    perf.grade = ev["grade"]
    perf.process_status = "assessment_complete"
    coverage = dict(coverage)
    if proof.get("__source") == "new_products_authority_v2":
        # V2 read-side grade validation needs the newly committed market version.
        current = dict(coverage.get("new_products_authority_v2") or {})
        current["market_version"] = (
            market_version
            if market_version is not None
            else (
                session.scalar(
                    select(MarketScore.version).where(
                        MarketScore.source_account_ref == account,
                        MarketScore.store_id == store,
                        MarketScore.item_id == item,
                    )
                )
                or 0
            )
        )
        current["status"] = "ready"
        current["missing"] = []
        coverage["new_products_authority_v2"] = current
        facts_block = dict(coverage.get("new_products_score_facts_v2") or {})
        facts_block["market_score"] = str(market_score)
        coverage["new_products_score_facts_v2"] = facts_block
    coverage["evaluation_final_snapshot"] = {
        "grade": ev["grade"],
        "total": ev["total"],
        "dimensions": ev["dimensions"],
        "rule_version": version,
        "proof_hash": _sha(proof),
        "market_score": market_score,
        "published_at": _now().isoformat(),
        "risk_evaluation": risk_record,
        "system_risk_display": risk_display,
    }
    if pending and isinstance(coverage.get("operator_score_correction_v1"), dict):
        from .score_corrections import calculate_effective

        block = dict(coverage["operator_score_correction_v1"])
        if not isinstance(block.get("overrides"), dict):
            _error("NP_EVAL_CORRECTION_CONFLICT", 409, "历史修正记录格式无效")
        baseline = {
            "rule_version": version,
            "total": ev["total"],
            "grade": ev["grade"],
            "dimensions": dict(ev["dimensions"]),
            "ad_excluded": bool(ev.get("ad_excluded")),
        }
        try:
            effective = calculate_effective(
                baseline, block["overrides"], config, risk_evaluation=risk_record
            )
        except (KeyError, ValueError, TypeError, ArithmeticError):
            _error("NP_EVAL_CORRECTION_CONFLICT", 409, "市场评分更新后，原修正分数无法安全重算")
        block["system"] = baseline
        block["effective"] = effective
        coverage["operator_score_correction_v1"] = block
    coverage["evaluation_grade_confirmation_v1"] = {
        "status": "pending",
        "rule_version": version,
        "market_version": market_version,
        "created_at": _now().isoformat(),
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


def _iter_formal_candidates(
    session: Session,
    *,
    identity: tuple[str, str, str] | None = None,
    page_size: int = 500,
):
    """Stable identity-keyset scan, including candidates beyond the old 5000 cap."""
    cursor: tuple[str, str, str] | None = None
    while True:
        r = NewProductRegistry
        stmt = (
            select(r, NewProductPerformanceCurrent)
            .join(
                NewProductPerformanceCurrent,
                NewProductPerformanceCurrent.registry_id == r.id,
            )
            .where(r.is_currently_tagged.is_(True))
        )
        if identity is not None:
            stmt = stmt.where(
                r.source_account_ref == identity[0],
                r.store_id == identity[1],
                r.item_id == identity[2],
            )
        if cursor is not None:
            stmt = stmt.where(tuple_(r.source_account_ref, r.store_id, r.item_id) > cursor)
        rows = session.execute(
            stmt.order_by(r.source_account_ref, r.store_id, r.item_id).limit(page_size)
        ).all()
        if not rows:
            break
        for reg, perf in rows:
            yield reg, perf
        if len(rows) < page_size or identity is not None:
            break
        reg = rows[-1][0]
        cursor = (str(reg.source_account_ref), str(reg.store_id), str(reg.item_id))


def finalize_automatic(
    session: Session,
    cutoff: date | None = None,
    *,
    identity: tuple[str, str, str] | None = None,
    actor: str = "system",
) -> dict:
    """Run once *inside existing PR337 master task* after evidence publication.

    No second scheduler. A completed trigger freezes its first published window.
    """
    cutoff = cutoff or _cutoff()
    config, version = _config(session)
    rows = _iter_formal_candidates(session, identity=identity)
    counts = {"checked": 0, "published": 0, "incomplete": 0, "sold_out_verified": 0}
    for reg, perf in rows:
        if perf.grade is not None or perf.score is not None or _protected(session, reg):
            continue
        coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
        trigger = coverage.get("evaluation_formal_trigger")
        if trigger:
            if (
                isinstance(trigger, dict)
                and trigger.get("status") == "completed"
                and perf.grade is None
            ):
                refreshed = _verified_proof(perf)
                if (
                    refreshed is not None
                    and refreshed.get("__source") == "new_products_authority_v2"
                ):
                    ready_now, _ = _ready(refreshed, config, version)
                    if ready_now and trigger.get("proof_hash") != _sha(refreshed):
                        next_coverage = dict(coverage)
                        next_trigger = dict(trigger)
                        next_trigger["proof_hash"] = _sha(refreshed)
                        next_trigger["rule_version"] = version
                        next_coverage["evaluation_formal_trigger"] = next_trigger
                        perf.data_coverage_json = next_coverage
                        perf.updated_at = _now()
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
        if _set_formal(perf, source=source, cutoff=cutoff, proof=proof, actor=actor):
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
    """Recalculate one exact-identity V2 snapshot; never fake a formal completion."""
    from .unified_publish import execute_unified_job

    cutoff = _cutoff()
    first = day(getattr(listing, "first_wfs_available_date_la", None))
    if first is None or first > cutoff:
        _error("NP_EVAL_FIRST_WFS_REQUIRED", 409, "WFS首次可售日期未核实或尚无完整业务日")
    reg = _registry(session, account, store, item)
    if reg is None:
        _error("NP_EVAL_NO_REGISTRY", 409, "没有可评分的真实新品")
    perf = _performance(session, reg)
    if _protected(session, reg) or (
        perf is not None and (perf.grade is not None or perf.score is not None)
    ):
        _error("NP_EVAL_RESULT_FROZEN", 409, "已有正式等级或审批结果，不允许再次计算")
    coverage = (
        perf.data_coverage_json
        if perf is not None and isinstance(perf.data_coverage_json, dict)
        else {}
    )
    old_trigger = coverage.get("evaluation_formal_trigger")
    if isinstance(old_trigger, dict) and old_trigger.get("status") == "completed":
        # A formal trigger is immutable; do not run the ordinary publisher over it.
        proof = _verified_proof(perf)
        config, version = _config(session)
        valid, _ = _ready(proof, config, version) if proof else (False, [])
        if not valid or old_trigger.get("proof_hash") != _sha(proof):
            _error("NP_EVAL_FORMAL_EVIDENCE_CHANGED", 409, "正式测评证据已变化，请走复核")
        return {
            "status": "completed",
            "trigger": "already_formal",
            "item_id": item,
            "cutoff_la": str(cutoff),
            "missing": [],
            "dimensions": (coverage.get("auto_dimension_scores") or {}).get("dimensions", {}),
        }

    # Release the API request's source read transaction before separate source/target
    # publisher sessions acquire locks. Production still needs standard write approval.
    session.rollback()
    result = execute_unified_job(
        item_ids={item},
        limit=1,
        apply=True,
        auto_only=True,
        manual_identity=(account, store, item),
    )
    session.expire_all()
    reg = _registry(session, account, store, item)
    perf = _performance(session, reg) if reg is not None else None
    if perf is None:
        _error("NP_EVAL_SNAPSHOT_UNAVAILABLE", 409, "自动评分未生成结果")
    if _protected(session, reg) or perf.grade is not None or perf.score is not None:
        _error("NP_EVAL_RESULT_FROZEN", 409, "正式结果或业务审批已锁定")
    if result.get("graded_skipped") or result.get("frozen") or result.get("frozen_formal"):
        _error("NP_EVAL_RESULT_FROZEN", 409, "正式结果已锁定，不能重复计算")

    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    block = coverage.get("auto_dimension_scores")
    dimensions = block.get("dimensions") if isinstance(block, dict) else {}
    facts = coverage.get("new_products_score_facts_v2") or {}
    labels = {"speed": "出单速度", "ad": "广告有效性", "profit": "利润空间", "trust": "数据可信度"}
    missing = [
        label
        for key, label in labels.items()
        if not isinstance(dimensions, dict)
        or (
            dimensions.get(key) is None
            and not (key == "ad" and facts.get("ad_status") == "not_run")
        )
    ]
    processed = result.get("written", 0) + result.get("reconciled", 0) == 1
    if not processed:
        missing.append("本次自动评分未成功发布")
    status = "incomplete"
    if processed and not missing:
        eligible_now, eligible_reason = eligible(
            first_wfs=day(perf.first_wfs_available_date_la),
            cutoff=cutoff,
            sold_status=perf.sold_out_evidence_status,
            sold_day=perf.first_batch_sold_out_date_la,
        )
        if eligible_now:
            # Same gate as nightly formalization, but restricted to this full identity.
            finalize_automatic(
                session,
                cutoff,
                identity=(account, store, item),
                actor=actor,
            )
            coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
            trigger = coverage.get("evaluation_formal_trigger")
            proof = _verified_proof(perf)
            config, version = _config(session)
            ready, reasons = _ready(proof, config, version) if proof else (False, ["V2证据未核实"])
            final_snapshot = coverage.get("evaluation_final_snapshot")
            verified_final = (
                perf.grade is not None
                and perf.score is not None
                and isinstance(final_snapshot, dict)
            )
            verified_pending = (
                (proof is not None and trigger.get("proof_hash") == _sha(proof) and ready)
                if isinstance(trigger, dict)
                else False
            )
            if (
                isinstance(trigger, dict)
                and trigger.get("status") == "completed"
                and (verified_pending or verified_final)
            ):
                status = "completed"
            else:
                missing.extend(reasons or ["正式测评窗口或证据条件尚未满足"])
        else:
            missing.append("尚未满足14天或经过核实的提前售罄条件：" + eligible_reason)
    if status == "incomplete":
        details = (block or {}).get("missing") if isinstance(block, dict) else []
        missing.extend(x for x in (details or []) if x != "市场竞争人工评分" and x not in missing)
        if not missing:
            missing.append("正式测评未完成")

    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=account,
            store_id=store,
            item_id=item,
            event_type="evaluation_completed" if status == "completed" else "evaluation_incomplete",
            actor_id=actor,
            payload_json={
                "trigger": "manual_auto_only",
                "cutoff_la": str(cutoff),
                "status": status,
                "missing": missing,
                "unified": result,
            },
            created_at=_now(),
        )
    )
    session.commit()
    return {
        "status": status,
        "trigger": "manual_auto_only",
        "item_id": item,
        "cutoff_la": str(cutoff),
        "missing": missing,
        "dimensions": dimensions if isinstance(dimensions, dict) else {},
    }


def recheck_once(
    session: Session, accounts, approval_id: UUID, actor: str, *, source: Session | None = None
) -> dict:
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
    if approval["status"] != "approved" or approval["snapshot"].get("review_reason_type") in (
        "special_exception",
        "manual_decision_change",
    ):
        _error("NP_EVAL_RECHECK_NOT_APPROVED", 409, "仅已批准纠错支持重新核算")
    snap = approval["snapshot"]
    a, s, i = snap["source_account_ref"], snap["store_id"], snap["item_id"]
    _lock(session, a, s, i)
    reg = _registry(session, a, s, i, lock=True)
    if (
        a != approval["source_account_ref"]
        or a not in accounts
        or not reg
        or str(reg.id) != str(approval["business_ref"])
        or _protected(session, reg)
    ):
        _error("NP_EVAL_RECHECK_LOCKED", 409, "后续业务状态不允许重核")
    perf = _performance(session, reg, lock=True)
    pending = (perf.data_coverage_json or {}).get("evaluation_recheck_required") if perf else None
    if (
        not isinstance(pending, dict)
        or pending.get("approval_id") != str(approval_id)
        or pending.get("status") != "awaiting_verified_source_correction"
        or pending.get("reason_type") != snap.get("review_reason_type")
        or snap.get("review_reason_type") not in ("calculation_error", "scoring_basis_error")
    ):
        _error("NP_EVAL_RECHECK_NO_PENDING", 409, "未找到有效的纠错复核授权")
    if str(perf.score) != str(snap["score"]) or perf.grade != snap["grade"]:
        _error("NP_EVAL_RECHECK_STALE", 409, "原始评级已变化")
    coverage = perf.data_coverage_json or {}
    verdict = coverage.get("operator_assessment_v1")
    # Formal decisions and V2 risk snapshots cannot use the legacy PR337 writer:
    # it does not rebuild the V2 evidence or reopen the grade-confirmation gate.
    if (
        isinstance(verdict, dict)
        or isinstance(coverage.get("new_products_authority_v2"), dict)
        or isinstance(coverage.get("evaluation_grade_confirmation_v1"), dict)
    ):
        if source is None:
            _error("NP_EVAL_RECHECK_SOURCE_REQUIRED", 409, "纠错重算需要已授权的只读经营数据源")
        return _recheck_formal_v2(session, source, accounts, approval, reg, perf, actor)
    request = {
        "source_account_ref": a,
        "store_id": s,
        "item_id": i,
        "requested_by": actor,
        "result_json": {"approval_id": str(approval_id)},
    }
    return _execute_approved_recheck(session, request, str(uuid4()))


def _recheck_formal_v2(session, source, accounts, approval, reg, perf, actor):
    """Approved single-item correction, using the same V2 publisher and risk gate.

    Never invoked by a GET or daily job. Source reads remain read-only. The prior
    formal grade, human decision and all evidence are archived inside the same
    transaction; any incomplete proof or failed gate rolls back the reopening.
    """
    from copy import deepcopy

    from .pr337_daily_pipeline import load_scoped_campaign_catalog
    from .unified_publish import _candidate_scores, _save_one, load_ad_snapshots

    key = (reg.source_account_ref, reg.store_id, reg.item_id)
    NewProductService(session, read_session=source)._listing(accounts, *key)
    if not reg.is_currently_tagged:
        _error("NP_EVAL_RECHECK_TAG_REMOVED", 409, "商品已移出新品范围，不能重新核算")
    previous = deepcopy(perf.data_coverage_json or {})
    old_verdict = previous.get("operator_assessment_v1")
    if isinstance(old_verdict, dict) and old_verdict.get("decision") != "failed":
        _error("NP_EVAL_RECHECK_NOT_FAILED", 409, "仅未通过的人工结论可重新打开测评")
    old_proof = _verified_proof(perf)
    if not isinstance(old_proof, dict):
        _error("NP_EVAL_RECHECK_OLD_PROOF", 409, "原评分证据无法核实，不能覆盖历史评分")
    old_final = previous.get("evaluation_final_snapshot")
    if not isinstance(old_final, dict) or not _stored_grade_matches_snapshot(
        perf.grade, perf.score, old_final
    ):
        _error("NP_EVAL_RECHECK_OLD_SNAPSHOT", 409, "原正式评分快照无法核实，不能重新核算")
    old_risk = old_final.get("risk_evaluation")
    selected = old_risk.get("manual_selected") if isinstance(old_risk, dict) else None
    if not isinstance(selected, list) or not selected:
        frozen = previous.get("market_risks_frozen_v1")
        selected = frozen.get("conditions") if isinstance(frozen, dict) else None
    if not isinstance(selected, list) or not selected:
        _error("NP_EVAL_RECHECK_RISK_SELECTION_MISSING", 409, "历史人工风险条件缺失，不能安全重算")
    cutoff = (
        day(old_proof.get("authority_cutoff_la"))
        or day(old_proof.get("cutoff_la"))
        or day(old_proof.get("window_end_la"))
    )
    if cutoff is None or cutoff > _cutoff():
        _error("NP_EVAL_RECHECK_WINDOW_INVALID", 409, "原测评业务截止日无法核实")
    histories = previous.get("evaluation_recheck_history_v2", [])
    if not isinstance(histories, list) or len(histories) >= 20:
        _error("NP_EVAL_RECHECK_HISTORY_CAP", 409, "纠错历史已达上限，需要先归档")
    market = session.scalar(
        select(MarketScore)
        .where(
            MarketScore.source_account_ref == key[0],
            MarketScore.store_id == key[1],
            MarketScore.item_id == key[2],
        )
        .with_for_update()
    )
    if market is None:
        _error("NP_EVAL_RECHECK_MARKET_MISSING", 409, "原市场评分缺失，不能重新核算")
    # Same verified source selection as ordinary V2; one exact identity, no batch publish.
    candidate = _candidate_scores(source, session, [key], cutoff).get(key)
    if not isinstance(candidate, dict) or not isinstance(candidate.get("evaluation"), dict):
        _error("NP_EVAL_RECHECK_SOURCE_INCOMPLETE", 409, "纠错后的真实经营数据仍不完整")
    facts = candidate.get("facts") or {}
    first = day(facts.get("first_wfs_available_date_la"))
    if first is None or first != day(perf.first_wfs_available_date_la):
        _error("NP_EVAL_RECHECK_WFS_CHANGED", 409, "首次可售日变化，需先核实原测评窗口")
    # Historical correction must not become a score change merely because
    # additional calendar days elapsed after the original evaluation window.
    old_facts = old_proof.get("facts")
    old_elapsed = old_facts.get("elapsed_days") if isinstance(old_facts, dict) else None
    if old_elapsed is not None:
        facts["elapsed_days"] = old_elapsed
    else:
        facts["elapsed_days"] = (cutoff - first).days + 2
    config, version = _config(session)
    if candidate.get("rule_version") != version:
        _error("NP_EVAL_RECHECK_RULE_STALE", 409, "重算期间评分规则已变更，请重试")
    candidate["evaluation"] = evaluate(facts, config, version)
    catalog, _, _ = load_scoped_campaign_catalog(session, cutoff)
    ads = load_ad_snapshots(source, [key], {key: first}, cutoff, campaign_catalog=catalog).get(key)
    if not isinstance(ads, dict):
        _error("NP_EVAL_RECHECK_AD_MISSING", 409, "纠错广告证据缺失")
    old_grade, old_score = perf.grade, str(perf.score)
    approval_id = str(approval["id"])
    now = _now()
    job_id = str(uuid4())
    pending = deepcopy(previous["evaluation_recheck_required"])
    # Preserve original JSON and record explicit authorization. Nothing is visible
    # outside the transaction until the same V2 risk gate has passed successfully.
    archived = {k: v for k, v in previous.items() if k != "evaluation_recheck_history_v2"}
    archive = {
        "approval_id": approval_id,
        "executed_at": now.isoformat(),
        "actor": actor,
        "grade": old_grade,
        "score": old_score,
        "coverage": archived,
    }
    current = dict(previous)
    for name in (
        "evaluation_final_snapshot",
        "evaluation_grade_confirmation_v1",
        "evaluation_formal_trigger",
        "operator_assessment_v1",
        "operator_score_correction_v1",
        "evaluation_operating_archive_v1",
        "evaluation_recheck_required",
        "evaluation_manual_exception",
        "ad_display_v1",
    ):
        current.pop(name, None)
    current["evaluation_recheck_history_v2"] = [*histories, archive]
    if isinstance(old_verdict, dict):
        history = current.get("operator_assessment_history_v1") or []
        if not isinstance(history, list):
            _error("NP_EVAL_RECHECK_HISTORY_INVALID", 409, "历史人工测评记录格式不正确")
        current["operator_assessment_history_v1"] = [*history, old_verdict]
    try:
        with session.begin_nested():
            # Only this locked and approved correction can temporarily reopen the
            # local record; the ordinary publisher's freeze checks remain untouched.
            perf.data_coverage_json = current
            perf.grade = None
            perf.score = None
            perf.process_status = "evaluating"
            session.flush()
            outcome = _save_one(session, key, ads, candidate, cutoff=cutoff, auto_only=True)
            if outcome not in ("written", "reconciled"):
                _error("NP_EVAL_RECHECK_PUBLISH_BLOCKED", 409, "纠错证据保存未通过：" + outcome)
            proof = _verified_proof(perf)
            if not isinstance(proof, dict):
                _error("NP_EVAL_RECHECK_SOURCE_UNVERIFIED", 409, "新评分证据未核实，保留原测评结论")
            _set_formal(perf, source="approved_recheck", cutoff=cutoff, proof=proof, actor=actor)
            result = publish_after_market(
                session, *key, market.score, market.version, risk_conditions=selected
            )
            revised = dict(perf.data_coverage_json or {})
            final = revised.get("evaluation_final_snapshot")
            marker = revised.get("evaluation_grade_confirmation_v1")
            if (
                not isinstance(result, dict)
                or not isinstance(final, dict)
                or not isinstance(marker, dict)
                or marker.get("status") != "pending"
            ):
                _error("NP_EVAL_RECHECK_FORMAL_BLOCKED", 409, "新正式评分未通过完整证据及风险校验")
            risk_keys = (
                "rule_version",
                "base_grade",
                "effective_grade",
                "risk_hits",
                "recommend_not_pass",
                "manual_selected",
                "system_evidence_cutoff_la",
            )
            new_risk = final.get("risk_evaluation") or {}
            prior_risk = old_risk if isinstance(old_risk, dict) else {}
            final_proof = _verified_proof(perf)
            if not isinstance(final_proof, dict):
                _error("NP_EVAL_RECHECK_SOURCE_UNVERIFIED", 409, "新正式评分证据无法核实")
            same_evidence = _sha(final_proof) == _sha(old_proof) and all(
                new_risk.get(k) == prior_risk.get(k) for k in risk_keys
            )
            # An approved scoring-basis review may reopen manual market/risk
            # assessment even if source metrics are unchanged. It still must
            # pass the full V2 proof and grade-confirmation gates before buying.
            if same_evidence and pending.get("reason_type") != "scoring_basis_error":
                _error(
                    "NP_EVAL_RECHECK_NO_CHANGE",
                    409,
                    "未发现已核实的数据、评分规则或风险变化，不能重开测评",
                )
            revised["evaluation_recheck_required"] = {
                **pending,
                "status": "completed",
                "completed_at": now.isoformat(),
                "job_id": job_id,
                "revised_grade": perf.grade,
                "revised_score": str(perf.score),
            }
            perf.data_coverage_json = revised
            session.add(
                ActionEvent(
                    id=uuid4(),
                    source_account_ref=key[0],
                    store_id=key[1],
                    item_id=key[2],
                    event_type="evaluation_recheck_completed",
                    actor_id=actor,
                    payload_json={
                        "approval_id": approval_id,
                        "job_id": job_id,
                        "before": old_grade,
                        "after": perf.grade,
                        "status": "pending_grade_confirmation",
                    },
                    created_at=now,
                )
            )
            session.execute(
                text(
                    "\n"
                    "                INSERT INTO app_approval_events(id,approval_id,eve"
                    "nt_type,actor_id,note,detail,created_at)\n"
                    "                VALUES(CAST(:id AS uuid),CAST(:aid AS "
                    "uuid),'recalculated',:actor,:note,CAST(:detail AS jsonb),:now)\n"
                    "            "
                ),
                {
                    "id": str(uuid4()),
                    "aid": approval_id,
                    "actor": actor,
                    "note": "已核实纠错证据，重新进入待等级确认",
                    "detail": _json(
                        {
                            "before_grade": old_grade,
                            "before_score": old_score,
                            "new_grade": perf.grade,
                            "new_score": str(perf.score),
                            "job_id": job_id,
                        }
                    ),
                    "now": now,
                },
            )
            new_grade = perf.grade
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "execution_id": job_id,
        "status": "completed",
        "grade": new_grade,
        "next_status": "待等级确认",
    }


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


def _validate_review_pass(perf, coverage, new_decision):
    if new_decision != "passed":
        return
    final = coverage.get("evaluation_final_snapshot")
    risk = final.get("risk_evaluation") if isinstance(final, dict) else None
    confirmation = coverage.get("evaluation_grade_confirmation_v1")
    if perf.grade not in ("S", "A", "B", "C") or (
        isinstance(risk, dict) and risk.get("recommend_not_pass") is True
    ):
        _error(
            "NP_ASSESSMENT_REVIEW_GRADE_BLOCKED",
            409,
            "D/Pass或高风险不通过商品不能直接改为测评通过，请先核实评分依据",
        )
    if isinstance(confirmation, dict) and confirmation.get("status") != "confirmed":
        _error("NP_ASSESSMENT_GRADE_UNCONFIRMED", 409, "请先确认等级")


def submit_review(
    session: Session,
    accounts,
    account,
    store,
    item,
    actor,
    reason_type,
    reason,
    evidence,
    new_decision=None,
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
    if not perf or perf.grade is None or perf.score is None:
        _error("NP_EVAL_NOT_SCORED", 409, "尚无正式评分")
    coverage = perf.data_coverage_json if isinstance(perf.data_coverage_json, dict) else {}
    manual_change = reason_type == "manual_decision_change"
    prior_verdict = coverage.get("operator_assessment_v1")
    if manual_change:
        _validate_review_pass(perf, coverage, new_decision)
        if not isinstance(prior_verdict, dict):
            _error("NP_ASSESSMENT_NOT_CONFIRMED", 409, "请先完成初次人工确认")
        if new_decision not in ("passed", "failed") or new_decision == prior_verdict.get(
            "decision"
        ):
            _error("NP_ASSESSMENT_REVIEW_CHOICE", 422, "变更结论须与原结论不同")
        if len("".join(reason.split())) < 20:
            _error("NP_ASSESSMENT_REVIEW_REASON", 422, "结论复核依据不少于20字")
    elif perf.grade not in ("D", "Pass") and not (
        reason_type in ("calculation_error", "scoring_basis_error")
        and isinstance(prior_verdict, dict)
        and prior_verdict.get("decision") == "failed"
    ):
        _error("NP_EVAL_NOT_FAILED", 409, "仅测评未通过商品可申请评分纠错，特批仍限D/Pass")
    if not manual_change and coverage.get("evaluation_manual_exception"):
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
        "operator_decision_before": dict(prior_verdict)
        if isinstance(prior_verdict, dict)
        else None,
        "operator_decision_requested": new_decision if manual_change else None,
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


def decide_review(
    session: Session,
    accounts,
    approval_id: UUID,
    actor,
    decision,
    reason,
    version,
    *,
    allow_self=False,
):
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
    if row["applicant_id"] == actor and not allow_self:
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
    if decision == "approved" and snap["review_reason_type"] == "manual_decision_change":
        _validate_review_pass(
            perf, perf.data_coverage_json or {}, snap.get("operator_decision_requested")
        )
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
        if snap["review_reason_type"] == "manual_decision_change":
            old = coverage.get("operator_assessment_v1")
            prior = snap.get("operator_decision_before")
            if not isinstance(old, dict) or old != prior:
                _error("NP_ASSESSMENT_REVIEW_STALE", 409, "历史人工结论已变化")
            changed = dict(old)
            changed.update(
                {
                    "decision": snap["operator_decision_requested"],
                    "reason": row["reason"],
                    "actor_id": row["applicant_id"],
                    "confirmed_at": now.isoformat(),
                    "approved_by": actor,
                    "approval_id": str(approval_id),
                    "revision": int(old.get("revision", 1)) + 1,
                }
            )
            coverage["operator_assessment_history_v1"] = [
                *coverage.get("operator_assessment_history_v1", []),
                dict(old),
            ]
            coverage["operator_assessment_v1"] = changed
            session.add(
                ActionEvent(
                    id=uuid4(),
                    source_account_ref=reg.source_account_ref,
                    store_id=reg.store_id,
                    item_id=reg.item_id,
                    event_type="operator_assessment_review_approved",
                    actor_id=actor,
                    payload_json={"before": old, "after": changed, "approval_id": str(approval_id)},
                    created_at=now,
                )
            )
        elif snap["review_reason_type"] == "special_exception":
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
        "outcome": "manual_decision_changed"
        if decision == "approved" and snap["review_reason_type"] == "manual_decision_change"
        else "manual_exception"
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
    # NP_SYSTEM_RISK_DISPLAY_V1: one config read; no source-table scans in GET.
    from .risk_display import build_saved_risk_display

    config, risk_rule_version = NewProductService(session)._config()
    risk_config = config.get("riskConditions") if isinstance(config, dict) else None
    risk_cutoff = _cutoff()
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
             p.sold_out_evidence_status,p.score,p.grade,
             jsonb_strip_nulls(jsonb_build_object(
               'evaluation_final_snapshot',p.data_coverage_json->'evaluation_final_snapshot',
               'evaluation_grade_confirmation_v1',p.data_coverage_json->'evaluation_grade_confirmation_v1',
               'operator_score_correction_v1',p.data_coverage_json->'operator_score_correction_v1',
               'operator_assessment_v1',p.data_coverage_json->'operator_assessment_v1',
               'evaluation_manual_exception',p.data_coverage_json->'evaluation_manual_exception',
               'evaluation_recheck_required',p.data_coverage_json->'evaluation_recheck_required',
               'evaluation_formal_trigger',p.data_coverage_json->'evaluation_formal_trigger',
               'auto_dimension_scores',p.data_coverage_json->'auto_dimension_scores'
             )) AS data_coverage_json,
             r.listing_date_la,
             p.data_coverage_json #>> '{evaluation_operating_archive_v1,suggested_qty}'
              AS frozen_suggested_qty,
             review.status AS review_status, review.id::text AS review_id,
             CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                  THEN review.reason END AS review_request_reason,
             CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                  THEN review.review_note END AS review_decision_reason,
             CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                  THEN review.reason_type END AS review_reason_type
      FROM wants w LEFT JOIN biz_new_product_registry r
       ON r.source_account_ref=w.a AND r.store_id=w.s AND r.item_id=w.i
      LEFT JOIN biz_new_product_performance_current p ON p.registry_id=r.id
      LEFT JOIN LATERAL (
        SELECT a.id,a.status,
               CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                    THEN a.reason END AS reason,
               CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                    THEN a.review_note END AS review_note,
               CASE WHEN p.data_coverage_json #>> '{operator_assessment_v1,decision}' = 'failed'
                    THEN a.snapshot->>'review_reason_type' END AS reason_type
        FROM app_approval_requests a
        WHERE a.approval_type=:kind AND a.business_ref=r.id::text
          AND a.source_account_ref=w.a
        ORDER BY a.submitted_at DESC,a.id DESC LIMIT 1
      ) review ON true
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
        entry["system_risk_display"] = build_saved_risk_display(
            coverage,
            risk_config,
            cutoff_la=risk_cutoff,
            first_wfs=r["first_wfs_available_date_la"],
            rule_version=risk_rule_version,
        )
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
        confirmation = coverage.get("evaluation_grade_confirmation_v1")
        entry["evaluation_grade_confirmation"] = (
            confirmation if isinstance(confirmation, dict) else None
        )
        correction = coverage.get("operator_score_correction_v1")
        if isinstance(correction, dict):
            revision = correction.get("revision")
            entry["score_correction_revision"] = (
                revision if type(revision) is int and revision >= 0 else None
            )
            entry["score_correction_state"] = (
                "applied"
                if isinstance(entry.get("score_correction"), dict)
                and entry["score_correction"].get("revision") == revision
                else "stale"
            )
        else:
            entry["score_correction_revision"] = 0
            entry["score_correction_state"] = "none"
        if (
            isinstance(confirmation, dict)
            and confirmation.get("status") == "confirmed"
            and isinstance(coverage.get("operator_score_correction_v1"), dict)
        ):
            from .score_corrections import public_correction

            entry["score_correction"] = public_correction(coverage["operator_score_correction_v1"])
        verdict = coverage.get("operator_assessment_v1")
        entry["evaluation_decision"] = verdict if isinstance(verdict, dict) else None
        if status == "测评未通过":
            final = coverage.get("evaluation_final_snapshot")
            risk = final.get("risk_evaluation") if isinstance(final, dict) else None
            blocked = isinstance(risk, dict) and risk.get("recommend_not_pass") is True
            risk_limited = blocked or (
                isinstance(risk, dict)
                and r["grade"] in ("D", "Pass")
                and risk.get("base_grade") in ("S", "A", "B", "C")
                and bool(risk.get("risk_hits"))
            )
            entry["failed_assessment_info"] = {
                "reason_kind": "risk_limit"
                if risk_limited
                else "grade_limit"
                if r["grade"] in ("D", "Pass")
                else "manual_decision",
                "manual_pass_allowed": r["grade"] in ("S", "A", "B", "C") and not blocked,
                "review_request_reason": r.get("review_request_reason"),
                "review_decision_reason": r.get("review_decision_reason"),
                "review_reason_type": r.get("review_reason_type"),
            }

        # Read only a scalar recommendation, never copy the full daily archive
        # into a 200-item list response.
        if r.get("frozen_suggested_qty") is not None:
            entry["suggested_qty"] = int(r["frozen_suggested_qty"])
        # In hybrid local mode the list may read source evidence through a
        # separate read session. The local, audited final evaluation is the
        # authority for evaluation-only columns; never promote a provisional
        # remote score into a formal grade.
        final = coverage.get("evaluation_final_snapshot")
        if r["grade"] is not None and r["score"] is not None:
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
        if isinstance(confirmation, dict) and confirmation.get("status") == "pending":
            # The authoritative DB grade replaced the earlier list overlay.
            # Apply the same saved revision AFTER the authoritative snapshot.
            entry.pop("score_correction", None)
            if isinstance(correction, dict):
                from .score_corrections import overlay

                valid_final = (
                    r["grade"] is not None
                    and r["score"] is not None
                    and isinstance(final, dict)
                    and final.get("grade") == r["grade"]
                )
                risk_record = final.get("risk_evaluation") if isinstance(final, dict) else None
                if valid_final and overlay(
                    entry,
                    correction,
                    config,
                    risk_evaluation=risk_record,
                    require_risk=True,
                ):
                    entry["score_correction_state"] = "applied"
                    entry["suggested_qty"] = NewProductService._suggested_quantity(
                        entry["evaluation"], config
                    )
                else:
                    # Do not silently display an old correction as current.
                    entry["score_correction_state"] = "stale"
                    entry["suggested_qty"] = None
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
        # NP_VERIFIED_LISTING_END_V2
        final = coverage.get("evaluation_final_snapshot")
        facts["evaluation_grade_published_at"] = (
            final.get("published_at")
            if isinstance(final, dict)
            and final.get("grade") == r["grade"]
            and r["grade"] is not None
            and r["score"] is not None
            and isinstance(final.get("published_at"), str)
            else None
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
