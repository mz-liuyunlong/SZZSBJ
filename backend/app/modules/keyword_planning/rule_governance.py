"""Guarded scoring-rule drafts and retirement. No implicit approval or ad execution.

D01-D08 require an independent business approval record. Until an approved
workflow exists, publication is blocked by design, not an unfinished TODO.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AiKwRuleDecision, AiKwRuleDecisionEvent, AiKwRuleSet, AiKwRuleVersion
from .rule_gates import ALGORITHM_VERSION, ColdStartLimits


class RuleGovernanceBlocked(ValueError):
    """Machine-readable, no sensitive details or arbitrary SQL messages."""


@dataclass(frozen=True)
class RuleVersionReceipt:
    id: UUID
    rule_set_id: UUID
    version_number: int
    status: str
    config_sha256: str


def canonical_digest(document: object) -> str:
    return hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _registry(mapping: Mapping[str, str]) -> dict[str, str]:
    """Only normalized names with identifiable prior review references are accepted."""
    if not isinstance(mapping, dict) or len(mapping) > 2000:
        raise RuleGovernanceBlocked("BRAND_REGISTRY_INVALID")
    result: dict[str, str] = {}
    for name, ref in mapping.items():
        if not (
            isinstance(name, str)
            and isinstance(ref, str)
            and 1 <= len(name.strip()) <= 128
            and name == name.strip()
            and 1 <= len(ref.strip()) <= 255
            and ref == ref.strip()
        ):
            raise RuleGovernanceBlocked("BRAND_EVIDENCE_REQUIRED")
        normalized = " ".join(name.casefold().split())
        if normalized in result:
            raise RuleGovernanceBlocked("DUPLICATE_BRAND_NAME")
        result[normalized] = ref
    return result


def build_draft_config(
    *,
    limits: ColdStartLimits,
    confirmed_brands: Mapping[str, str],
    suspected_brands: Mapping[str, str],
) -> dict[str, object]:
    limits.validate()
    # Quotas are configurable business policy, never claimed Walmart API limits.
    values = asdict(limits)
    if any(value > 500 for value in values.values()):
        raise RuleGovernanceBlocked("DRAFT_LIMIT_TOO_LARGE")
    confirmed = _registry(confirmed_brands)
    suspected = _registry(suspected_brands)
    if confirmed.keys() & suspected.keys():
        raise RuleGovernanceBlocked("BRAND_REVIEW_CONFLICT")
    return {
        "limits": values,
        "confirmed_brands": confirmed,
        "suspected_brands": suspected,
        "business_approvals": {f"D{i:02d}": "pending" for i in range(1, 9)},
        "automatic_classification_approved": False,
        "official_bulk_template_approved": False,
    }


def create_scoring_ruleset(
    session: Session,
    *,
    account: str,
    actor: str,
    rule_key: str,
    display_name: str,
) -> UUID:
    """Create a disabled account-owned scoring ruleset, never a global rule."""
    if (
        not account
        or len(account) > 128
        or not actor
        or len(actor) > 255
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", rule_key)
        or not 1 <= len(display_name.strip()) <= 255
    ):
        raise RuleGovernanceBlocked("RULE_SET_INPUT_INVALID")
    with session.begin():
        existing = session.scalar(
            select(AiKwRuleSet).where(
                AiKwRuleSet.rule_key == rule_key,
                AiKwRuleSet.scope_key == account,
            )
        )
        if existing is not None:
            raise RuleGovernanceBlocked("RULE_SET_ALREADY_EXISTS")
        record = AiKwRuleSet(
            rule_key=rule_key,
            scope_key=account,
            rule_type="scoring",
            display_name=display_name.strip(),
            created_by=actor,
            is_enabled=False,
        )
        session.add(record)
        session.flush()
        return record.id


def create_scoring_draft(
    session: Session,
    *,
    account: str,
    rule_set_id: UUID,
    actor: str,
    limits: ColdStartLimits,
    confirmed_brands: Mapping[str, str],
    suspected_brands: Mapping[str, str],
) -> RuleVersionReceipt:
    """Create a non-executable draft, serializing version allocation on the rule set."""
    if not account or not actor or len(actor) > 255:
        raise RuleGovernanceBlocked("ACCOUNT_OR_ACTOR_MISSING")
    config = build_draft_config(
        limits=limits,
        confirmed_brands=confirmed_brands,
        suspected_brands=suspected_brands,
    )
    with session.begin():
        rule_set = session.scalar(
            select(AiKwRuleSet)
            .where(
                AiKwRuleSet.id == rule_set_id,
            )
            .with_for_update()
        )
        if rule_set is None or rule_set.rule_type != "scoring" or rule_set.scope_key != account:
            raise RuleGovernanceBlocked("RULE_SET_NOT_IN_ACCOUNT")
        # Database unique(rule_set_id, version_number) handles concurrent sessions;
        # FOR UPDATE locks the parent before computing max version.
        existing = session.scalars(
            select(AiKwRuleVersion.version_number).where(
                AiKwRuleVersion.rule_set_id == rule_set_id,
            )
        )
        number = max((int(item) for item in existing), default=0) + 1
        record = AiKwRuleVersion(
            rule_set_id=rule_set_id,
            version_number=number,
            status="draft",
            config_json=config,
            config_sha256=canonical_digest(config),
            schema_version="v1.1-draft",
            engine_version=ALGORITHM_VERSION,
        )
        session.add(record)
        session.flush()
        return RuleVersionReceipt(
            record.id,
            rule_set_id,
            number,
            "draft",
            record.config_sha256,
        )


def retire_published_rule(
    session: Session,
    *,
    account: str,
    version_id: UUID,
) -> RuleVersionReceipt:
    """Retire only; never edit the content or resurrect a published rule."""
    if not account:
        raise RuleGovernanceBlocked("ACCOUNT_MISSING")
    with session.begin():
        version = session.scalar(
            select(AiKwRuleVersion)
            .where(
                AiKwRuleVersion.id == version_id,
            )
            .with_for_update()
        )
        if version is None:
            raise RuleGovernanceBlocked("RULE_VERSION_NOT_FOUND")
        owner = session.get(AiKwRuleSet, version.rule_set_id)
        if owner is None or owner.rule_type != "scoring" or owner.scope_key != account:
            raise RuleGovernanceBlocked("RULE_SET_NOT_IN_ACCOUNT")
        if version.status != "published":
            raise RuleGovernanceBlocked("RULE_NOT_PUBLISHED")
        version.status = "retired"
        session.flush()
        return RuleVersionReceipt(
            version.id,
            version.rule_set_id,
            version.version_number,
            "retired",
            version.config_sha256,
        )


DECISION_KEYS = frozenset(f"D{i:02d}" for i in range(1, 9))


def _owned_version(
    session: Session, *, account: str, version_id: UUID
) -> tuple[AiKwRuleVersion, AiKwRuleSet]:
    version = session.scalar(
        select(AiKwRuleVersion).where(AiKwRuleVersion.id == version_id).with_for_update()
    )
    owner = session.get(AiKwRuleSet, version.rule_set_id) if version else None
    if (
        version is None
        or owner is None
        or owner.scope_key != account
        or owner.rule_type != "scoring"
    ):
        raise RuleGovernanceBlocked("RULE_VERSION_NOT_IN_ACCOUNT")
    if canonical_digest(version.config_json) != version.config_sha256:
        raise RuleGovernanceBlocked("RULE_CONFIG_HASH_MISMATCH")
    return version, owner


def submit_rule_decision(
    session: Session,
    *,
    account: str,
    version_id: UUID,
    decision_key: str,
    actor: str,
    proposal: dict[str, object],
    evidence_ref: str,
) -> UUID:
    """Owner submits a concrete proposal; this is never self-approval."""
    if decision_key not in DECISION_KEYS or not actor or not 1 <= len(evidence_ref) <= 255:
        raise RuleGovernanceBlocked("DECISION_INPUT_INVALID")
    if not isinstance(proposal, dict) or not proposal or len(json.dumps(proposal)) > 8192:
        raise RuleGovernanceBlocked("DECISION_PROPOSAL_REQUIRED")
    if decision_key == "D04" and proposal.get("strategy") not in (
        "null_review",
        "legacy_unknown_two",
    ):
        raise RuleGovernanceBlocked("D04_STRATEGY_REQUIRED")
    with session.begin():
        version, owner = _owned_version(session, account=account, version_id=version_id)
        if version.status != "draft" or actor != owner.created_by:
            raise RuleGovernanceBlocked("DECISION_SUBMITTER_NOT_OWNER")
        row = session.scalar(
            select(AiKwRuleDecision)
            .where(
                AiKwRuleDecision.rule_version_id == version_id,
                AiKwRuleDecision.decision_key == decision_key,
            )
            .with_for_update()
        )
        if row is not None and row.status != "rejected":
            raise RuleGovernanceBlocked("DECISION_ALREADY_SUBMITTED")
        old = row.status if row else None
        if row is None:
            row = AiKwRuleDecision(
                rule_version_id=version_id,
                decision_key=decision_key,
                status="pending_review",
                config_sha256=version.config_sha256,
                evidence_ref=evidence_ref,
                decision_json=proposal,
                submitted_by=actor,
            )
            session.add(row)
        else:
            row.status = "pending_review"
            row.config_sha256 = version.config_sha256
            row.evidence_ref = evidence_ref
            row.decision_json = proposal
            row.submitted_by = actor
            row.reviewed_by = None
            row.reviewed_at = None
        session.flush()
        session.add(
            AiKwRuleDecisionEvent(
                decision_id=row.id,
                action="submit",
                actor=actor,
                status_before=old,
                status_after="pending_review",
                evidence_ref=evidence_ref,
            )
        )
        return row.id


def review_rule_decision(
    session: Session,
    *,
    account: str,
    version_id: UUID,
    decision_key: str,
    actor: str,
    approved: bool,
    evidence_ref: str,
) -> str:
    if decision_key not in DECISION_KEYS or not actor or not 1 <= len(evidence_ref) <= 255:
        raise RuleGovernanceBlocked("DECISION_INPUT_INVALID")
    with session.begin():
        version, owner = _owned_version(session, account=account, version_id=version_id)
        row = session.scalar(
            select(AiKwRuleDecision)
            .where(
                AiKwRuleDecision.rule_version_id == version_id,
                AiKwRuleDecision.decision_key == decision_key,
            )
            .with_for_update()
        )
        if version.status != "draft" or row is None or row.status != "pending_review":
            raise RuleGovernanceBlocked("DECISION_NOT_PENDING")
        if actor in (owner.created_by, row.submitted_by):
            raise RuleGovernanceBlocked("INDEPENDENT_REVIEWER_REQUIRED")
        if row.config_sha256 != version.config_sha256:
            raise RuleGovernanceBlocked("DECISION_CONFIG_CHANGED")
        row.status = "approved" if approved else "rejected"
        row.reviewed_by = actor
        row.reviewed_at = datetime.now(UTC)
        session.add(
            AiKwRuleDecisionEvent(
                decision_id=row.id,
                action="approve" if approved else "reject",
                actor=actor,
                status_before="pending_review",
                status_after=row.status,
                evidence_ref=evidence_ref,
            )
        )
        return row.status


def publish_scoring_rule(
    session: Session,
    *,
    account: str,
    version_id: UUID,
    actor: str,
) -> RuleVersionReceipt:
    """Only a separate publisher may activate a frozen draft with eight approvals."""
    with session.begin():
        version, owner = _owned_version(session, account=account, version_id=version_id)
        if version.status != "draft" or actor == owner.created_by:
            raise RuleGovernanceBlocked("INDEPENDENT_PUBLISHER_REQUIRED")
        decisions = list(
            session.scalars(
                select(AiKwRuleDecision)
                .where(
                    AiKwRuleDecision.rule_version_id == version_id,
                )
                .with_for_update()
            )
        )
        if (
            len(decisions) != 8
            or {d.decision_key for d in decisions} != DECISION_KEYS
            or any(
                d.status != "approved"
                or d.config_sha256 != version.config_sha256
                or not d.reviewed_by
                or not d.reviewed_at
                for d in decisions
            )
        ):
            raise RuleGovernanceBlocked("INDEPENDENT_D01_D08_APPROVAL_REQUIRED")
        reviewers = {d.reviewed_by for d in decisions}
        if len(reviewers) < 2 or actor in reviewers:
            raise RuleGovernanceBlocked("SEPARATE_REVIEW_AND_PUBLISH_REQUIRED")
        version.status = "published"
        version.published_by = actor
        version.published_at = datetime.now(UTC)
        owner.is_enabled = True
        session.flush()
        return RuleVersionReceipt(
            version.id, owner.id, version.version_number, "published", version.config_sha256
        )
