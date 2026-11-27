"""Read-only, as-submitted evidence for the new-product purchase approval UI.

Uses the locked purchase score snapshot, the score's historical rule version,
and only audit events that existed before the application. No writes or rescore.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.modules.new_products.models import ActionEvent, RuleVersion
from app.modules.new_products.rules import DEFAULT_WEIGHTS

_DIMENSIONS = ("speed", "ad", "profit", "trust", "market")


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _score(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return str(score) if score.is_finite() and 0 <= score <= 10 else None


def _scores(value: object) -> dict[str, str | None]:
    data = _mapping(value)
    return {name: _score(data.get(name)) for name in _DIMENSIONS}


# NP_PURCHASE_SCORE_GRADE_EVIDENCE_V1
_GRADES = ("S", "A", "B", "C", "D", "Pass")


def _grade(value):
    return value if isinstance(value, str) and value in _GRADES else None


def _same_score(left, right):
    a, b = _score(left), _score(right)
    return a is not None and b is not None and Decimal(a) == Decimal(b)


def _same_dimensions(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    for name in _DIMENSIONS:
        if name not in left or name not in right:
            return False
        a, b = left[name], right[name]
        if a is None and b is None:
            continue
        if not _same_score(a, b):
            return False
    return True


def _matching_confirmation(application, evaluation, audited):
    # Only the last confirmation before this application is authoritative.
    event = next((e for e in audited if e.event_type == "grade_confirmed"), None)
    record = _mapping(event.payload_json) if event is not None else {}
    revision = record.get("correction_revision")
    if (
        record.get("status") != "confirmed"
        or type(revision) is not int
        or revision < 0
        or record.get("rule_version") != application.score_rule_version
        or _grade(record.get("effective_grade")) is None
        or record.get("effective_grade") != evaluation.get("grade")
        or not _same_score(record.get("effective_total"), evaluation.get("total"))
    ):
        return None, {}
    return event, record


def _recover_correction_from_audit(evaluation, audited, confirmation, record):
    # No inference from a later product score. The full revision sequence,
    # system values, and last per-dimension values must match the purchase.
    if confirmation is None:
        return {}
    revision = record["correction_revision"]
    dimensions = _mapping(evaluation.get("dimensions"))
    if not _same_dimensions(dimensions, dimensions):
        return {}
    if revision == 0:
        return {
            "revision": 0,
            "system": {"dimensions": dict(dimensions), "grade": evaluation.get("grade")},
            "effective": {"dimensions": dict(dimensions), "grade": evaluation.get("grade")},
            "history": [],
        }
    # Bound the audit segment to this confirmation and stop at an earlier
    # confirmation. A truncated/incomplete segment must not assert no edits.
    events = []
    started = False
    for event in audited:
        if event is confirmation:
            started = True
            continue
        if not started:
            continue
        if event.event_type == "grade_confirmed":
            break
        if event.event_type == "score_correction_saved":
            events.append(_mapping(event.payload_json))
    events.reverse()
    if len(events) != revision or any(
        type(e.get("revision")) is not int or e["revision"] != index
        for index, e in enumerate(events, 1)
    ):
        return {}
    system = dict(dimensions)
    previous = {}
    original = {}
    for event in events:
        name = event.get("dimension")
        if name not in _DIMENSIONS[:-1]:
            return {}
        base, before, after = (_score(event.get(k)) for k in ("system_score", "before", "after"))
        if base is None or before is None or after is None:
            return {}
        if name in previous:
            if not _same_score(previous[name], before) or not _same_score(original[name], base):
                return {}
        elif not _same_score(base, before):
            return {}
        original[name] = base
        previous[name] = after
        system[name] = base
    if any(not _same_score(dimensions.get(name), value) for name, value in previous.items()):
        return {}
    # Old events contain effective_grade but do not always contain the original
    # grade. Do not reconstruct it from today's rules or assume it was unchanged.
    return {
        "revision": revision,
        "system": {"dimensions": system},
        "effective": {"dimensions": dict(dimensions), "grade": evaluation.get("grade")},
        "history": events,
    }


def _recover_locked_confirmation(session, application, evaluation, record):
    # Optional read of the original *locked* confirmation, not the live score.
    # A later recheck/confirmation cannot match this historical audit identity.
    if not record or not isinstance(record.get("confirmed_at"), str):
        return {}, {}
    from app.modules.new_products.models import NewProductPerformanceCurrent, NewProductRegistry

    coverage = session.scalar(
        select(NewProductPerformanceCurrent.data_coverage_json)
        .join(NewProductRegistry, NewProductRegistry.id == NewProductPerformanceCurrent.registry_id)
        .where(
            NewProductRegistry.source_account_ref == application.source_account_ref,
            NewProductRegistry.store_id == application.store_id,
            NewProductRegistry.item_id == application.item_id,
        )
    )
    coverage = _mapping(coverage)
    marker = _mapping(coverage.get("evaluation_grade_confirmation_v1"))
    keys = (
        "status",
        "actor_id",
        "confirmed_at",
        "rule_version",
        "market_version",
        "correction_revision",
        "effective_grade",
        "effective_total",
    )
    if any(key not in record or marker.get(key) != record[key] for key in keys):
        return {}, {}
    final = _mapping(coverage.get("evaluation_final_snapshot"))
    if (
        final.get("rule_version") != application.score_rule_version
        or final.get("grade") != evaluation.get("grade")
        or not _same_score(final.get("total"), evaluation.get("total"))
        or not _same_dimensions(final.get("dimensions"), evaluation.get("dimensions"))
    ):
        return {}, {}
    original = _mapping(final.get("grade_before_confirmation_v1"))
    correction = _mapping(coverage.get("operator_score_correction_v1"))
    if record["correction_revision"] == 0:
        return {}, original
    if (
        correction.get("revision") != record["correction_revision"]
        or not isinstance(correction.get("history"), list)
        or len(correction["history"]) != record["correction_revision"]
        or not _same_dimensions(
            _mapping(correction.get("effective")).get("dimensions"), final.get("dimensions")
        )
        or not _same_dimensions(
            _mapping(correction.get("system")).get("dimensions"), original.get("dimensions")
        )
    ):
        return {}, {}
    return correction, original


# NP_PURCHASE_SCORE_HOVER_HEADER_V2
def _history_actor_names(session, history):
    ids = set()
    for event in history:
        actor = event.get("actor_id")
        if isinstance(actor, str) and actor.isascii() and actor.isdigit():
            value = int(actor)
            if 0 < value <= 9223372036854775807:
                ids.add(value)
    if not ids:
        return {}
    stmt = text(
        "SELECT id, COALESCE(NULLIF(btrim(display_name), ''), "
        "NULLIF(btrim(feishu_name), '')) AS actor_name "
        "FROM app_users WHERE id IN :actor_ids"
    ).bindparams(bindparam("actor_ids", expanding=True))
    rows = session.execute(stmt, {"actor_ids": sorted(ids)}).mappings().all()
    return {str(row["id"]): row["actor_name"] for row in rows if row["actor_name"]}


def _manual_selection(snapshot: dict[str, Any], facts: dict[str, Any], events: list[ActionEvent]):
    """Show only an explicitly persisted manual conclusion, never infer one from C grade."""
    for source in (snapshot, facts):
        for key in (
            "evaluation_decision",
            "manual_decision",
            "assessment_decision",
            "evaluation_manual_decision",
            "operator_decision",
        ):
            item = _mapping(source.get(key))
            outcome = item.get("decision") or item.get("outcome") or item.get("result")
            if isinstance(outcome, str) and outcome.strip():
                reason = item.get("reason") or item.get("note")
                return {
                    "decision": outcome.strip(),
                    "reason": reason.strip() if isinstance(reason, str) else None,
                }
    for event in events:
        event_name = event.event_type.lower()
        if not any(
            key in event_name
            for key in (
                "manual_decision",
                "assessment_confirmed",
                "evaluation_decision",
                "assessment_decision",
                "manual_assessment",
            )
        ):
            continue
        item = _mapping(event.payload_json)
        outcome = item.get("decision") or item.get("outcome") or item.get("result")
        if isinstance(outcome, str) and outcome.strip():
            reason = item.get("reason") or item.get("note")
            return {
                "decision": outcome.strip(),
                "reason": reason.strip() if isinstance(reason, str) else None,
            }
    return None


def purchase_reference_evidence(
    session: Session, application: Any, *, preloaded=None
) -> dict[str, Any]:
    """Call only after purchase-detail scope and reviewer/applicant access checks."""
    snapshot = _mapping(application.score_snapshot)
    facts = _mapping(snapshot.get("facts"))
    evaluation = _mapping(snapshot.get("evaluation"))
    effective_dimensions = _scores(evaluation.get("dimensions"))
    # The specific historical scoring rule version is persisted separately.
    weights: dict[str, int | float] | None = None
    rule_version = application.score_rule_version
    if rule_version == 0:
        weights = dict(DEFAULT_WEIGHTS)
    else:
        version = (
            preloaded[0]
            if preloaded is not None
            else session.scalar(
                select(RuleVersion)
                .where(
                    RuleVersion.kind == "performance",
                    RuleVersion.version == rule_version,
                )
                .limit(1)
            )
        )
        config = _mapping(version.config_json) if version is not None else {}
        candidate = _mapping(config.get("weights"))
        if set(candidate) == set(_DIMENSIONS):
            try:
                parsed = {name: Decimal(str(candidate[name])) for name in _DIMENSIONS}
                if (
                    all(v.is_finite() and v >= 0 for v in parsed.values())
                    and sum(parsed.values()) == 100
                ):
                    weights = {
                        name: int(v) if v == int(v) else float(v) for name, v in parsed.items()
                    }
            except (ValueError, TypeError, InvalidOperation, OverflowError):
                pass

    # All historical events are strictly bounded by purchase application time.
    audited = (
        preloaded[1]
        if preloaded is not None
        else list(
            session.scalars(
                select(ActionEvent)
                .where(
                    ActionEvent.source_account_ref == application.source_account_ref,
                    ActionEvent.store_id == application.store_id,
                    ActionEvent.item_id == application.item_id,
                    ActionEvent.created_at <= application.created_at,
                )
                .order_by(ActionEvent.created_at.desc(), ActionEvent.id.desc())
                .limit(120)
            ).all()
        )
    )
    # NP_PURCHASE_SCORE_GRADE_EVIDENCE_V1: prefer immutable application proof.
    correction = _mapping(snapshot.get("score_correction") or facts.get("score_correction"))
    original = _mapping(snapshot.get("grade_before_confirmation"))
    if not correction:
        confirmation, record = _matching_confirmation(application, evaluation, audited)
        if confirmation is not None:
            correction, recovered_original = _recover_locked_confirmation(
                session, application, evaluation, record
            )
            if recovered_original:
                original = recovered_original
            if not correction:
                correction = _recover_correction_from_audit(
                    evaluation, audited, confirmation, record
                )
    system = _mapping(correction.get("system"))
    system_dimensions = _scores(system.get("dimensions"))
    history = []
    saved_history = correction.get("history")
    for event in saved_history if isinstance(saved_history, list) else []:
        if not isinstance(event, dict) or event.get("dimension") not in _DIMENSIONS[:-1]:
            continue
        reason = event.get("reason")
        history.append(
            {
                "dimension": event["dimension"],
                "before": _score(event.get("before")),
                "after": _score(event.get("after")),
                "reason": reason.strip() if isinstance(reason, str) else None,
                "actor_id": str(event.get("actor_id") or "") or None,
                "at": str(event.get("at") or "") or None,
                "revision": event.get("revision") if type(event.get("revision")) is int else None,
                "before_grade": _grade(event.get("before_grade")),
                "after_grade": _grade(event.get("effective_grade")),
                "before_total": _score(event.get("before_total")),
                "after_total": _score(event.get("effective_total")),
            }
        )
    if not correction or not _same_dimensions(
        _mapping(correction.get("effective")).get("dimensions"), evaluation.get("dimensions")
    ):
        system_dimensions = {name: None for name in _DIMENSIONS}
        history = []
        system = {}
        original = {}
    system_grade = _grade(system.get("grade"))
    if original and _same_dimensions(original.get("dimensions"), system.get("dimensions")):
        original_grade = _grade(original.get("grade"))
        if system_grade is None or system_grade == original_grade:
            system_grade = original_grade
        else:
            system_grade = None
    effective_grade = _grade(evaluation.get("grade"))
    # Expose exact frozen totals, not a calculation using current weights.
    system_total = _score(system.get("total"))
    if (
        system_total is None
        and original
        and _same_dimensions(original.get("dimensions"), system.get("dimensions"))
        and _grade(original.get("grade")) == system_grade
        and system_grade is not None
    ):
        system_total = _score(original.get("total"))
    effective_total = _score(evaluation.get("total"))
    actor_names = _history_actor_names(session, history)
    for entry in history:
        entry["actor_name"] = actor_names.get(entry["actor_id"])

    market_event = next((event for event in audited if event.event_type == "market_score"), None)
    market_data = _mapping(market_event.payload_json) if market_event is not None else {}
    # If scores differ, the event is not evidence for this frozen purchase snapshot.
    market_matches = (
        bool(market_data)
        and _score(market_data.get("score")) is not None
        and (
            Decimal(str(market_data["score"])) == Decimal(effective_dimensions["market"])
            if effective_dimensions["market"] is not None
            else False
        )
    )
    if not market_matches:
        market_data = {}
    manual_risks = market_data.get("risk_conditions")
    manual_risks = (
        [item for item in manual_risks if isinstance(item, str) and item.strip()]
        if isinstance(manual_risks, list)
        else None
    )
    competitors = market_data.get("competitor_ids")
    competitors = (
        [item for item in competitors if isinstance(item, str) and item.strip()]
        if isinstance(competitors, list)
        else None
    )
    no_competitors = market_data.get("no_competitors")
    market_reason = market_data.get("reason")
    raw_system_risks = evaluation.get("risk")
    system_risks = (
        [risk for risk in raw_system_risks if isinstance(risk, str) and risk.strip()]
        if isinstance(raw_system_risks, list)
        else None
    )

    return {
        "frozen": True,
        "score_rule_version": rule_version,
        "system_dimensions": system_dimensions,
        "effective_dimensions": effective_dimensions,
        "weights": weights,
        "correction_history": history,
        "system_grade": system_grade,
        "effective_grade": effective_grade,
        "system_total": system_total,
        "effective_total": effective_total,
        "manual_risks": manual_risks,
        "system_risks": system_risks,
        "competitor_ids": competitors,
        "no_competitors": no_competitors if isinstance(no_competitors, bool) else None,
        "market_reason": market_reason.strip()
        if isinstance(market_reason, str) and market_reason.strip()
        else None,
        "manual_conclusion": _manual_selection(snapshot, facts, audited),
    }
