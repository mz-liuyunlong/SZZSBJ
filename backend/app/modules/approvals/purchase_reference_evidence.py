"""Read-only, as-submitted evidence for the new-product purchase approval UI.

Uses the locked purchase score snapshot, the score's historical rule version,
and only audit events that existed before the application. No writes or rescore.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
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
    correction = _mapping(snapshot.get("score_correction") or facts.get("score_correction"))
    system = _mapping(correction.get("system"))
    system_dimensions = _scores(system.get("dimensions")) if system else effective_dimensions.copy()
    history = []
    # The locked purchase snapshot is the authority; never read a current correction block.
    for event in (
        correction.get("history", []) if isinstance(correction.get("history"), list) else []
    ):
        if not isinstance(event, dict):
            continue
        dimension = event.get("dimension")
        if dimension not in _DIMENSIONS[:-1]:
            continue
        reason = event.get("reason")
        history.append(
            {
                "dimension": dimension,
                "before": _score(event.get("before")),
                "after": _score(event.get("after")),
                "reason": reason.strip() if isinstance(reason, str) else None,
                "actor_id": str(event.get("actor_id") or "") or None,
                "at": str(event.get("at") or "") or None,
                "revision": event.get("revision")
                if isinstance(event.get("revision"), int)
                else None,
            }
        )
    # Fail closed on an incompatible correction snapshot.
    if any(
        _score(_mapping(correction.get("effective")).get("dimensions", {}).get(name)) != value
        for name, value in effective_dimensions.items()
        if correction
        and name != "market"
        and isinstance(_mapping(correction.get("effective")).get("dimensions"), dict)
    ):
        system_dimensions = {name: None for name in _DIMENSIONS}
        history = []

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
        "manual_risks": manual_risks,
        "system_risks": system_risks,
        "competitor_ids": competitors,
        "no_competitors": no_competitors if isinstance(no_competitors, bool) else None,
        "market_reason": market_reason.strip()
        if isinstance(market_reason, str) and market_reason.strip()
        else None,
        "manual_conclusion": _manual_selection(snapshot, facts, audited),
    }
