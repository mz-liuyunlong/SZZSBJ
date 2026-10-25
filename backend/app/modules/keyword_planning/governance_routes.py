"""V1.1 rule review API. No auto-publish and no advertiser side effects."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission, require_super_admin
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

from .analysis_routes import _account_allowed, _require_opted_in_writes
from .models import AiKwRuleDecision, AiKwRuleDecisionEvent, AiKwRuleSet, AiKwRuleVersion
from .rule_gates import ColdStartLimits
from .rule_governance import (
    RuleGovernanceBlocked,
    RuleVersionReceipt,
    create_scoring_draft,
    create_scoring_ruleset,
    publish_scoring_rule,
    retire_published_rule,
    review_rule_decision,
    submit_rule_decision,
    update_scoring_draft,
)

router = APIRouter(tags=["Keyword Planning"])


class CreateDraftBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    limits: dict[str, int] = Field(default_factory=dict)
    confirmed_brands: dict[str, str] = Field(default_factory=dict)
    suspected_brands: dict[str, str] = Field(default_factory=dict)
    editor_config: dict[str, object] = Field(default_factory=dict)


class CreateRuleSetBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    rule_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)


class RetireBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)


class DecisionSubmitBody(RetireBody):
    proposal: dict[str, object]
    evidence_ref: str = Field(min_length=1, max_length=255)


class DecisionReviewBody(RetireBody):
    approved: bool
    evidence_ref: str = Field(min_length=1, max_length=255)


def _isolated_write(session: Session) -> None:
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "SESSION_NOT_ISOLATED"},
        )
    session.rollback()


class RuleDraftRead(BaseModel):
    version_id: UUID
    rule_set_id: UUID
    version_number: int
    status: str
    config_sha256: str
    publish_eligible: bool = False


class RuleSetListRead(BaseModel):
    items: list[dict[str, object]]
    total: int


class RuleVersionListRead(BaseModel):
    items: list[dict[str, object]]
    total: int


class RuleSetCreateRead(BaseModel):
    rule_set_id: UUID
    status: str
    publication_authorized: bool


class DecisionReceipt(BaseModel):
    decision_id: UUID | None = None
    decision_key: str | None = None
    status: str


class DecisionListRead(BaseModel):
    items: list[dict[str, object]]
    events: list[dict[str, object]]
    total: int


def _receipt(row: RuleVersionReceipt) -> RuleDraftRead:
    return RuleDraftRead(
        version_id=row.id,
        rule_set_id=row.rule_set_id,
        version_number=row.version_number,
        status=row.status,
        config_sha256=row.config_sha256,
    )


def _invalid(exc: RuleGovernanceBlocked) -> ApiError:
    return ApiError(
        code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
    )


@router.get("/rulesets", response_model=SuccessEnvelope[RuleSetListRead, None])
def list_rule_sets(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
) -> SuccessEnvelope[RuleSetListRead, None]:
    _account_allowed(source_account_ref, allowed_accounts, principal)
    rows = list(
        session.scalars(
            select(AiKwRuleSet)
            .where(
                AiKwRuleSet.scope_key.in_(("global", source_account_ref)),
                AiKwRuleSet.rule_type == "scoring",
            )
            .order_by(AiKwRuleSet.rule_key.asc())
            .limit(501)
        )
    )
    if len(rows) > 500:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "RULE_SET_LIMIT_EXCEEDED"},
        )
    items = [
        {
            "rule_set_id": str(row.id),
            "rule_key": row.rule_key,
            "display_name": row.display_name,
            "scope_key": row.scope_key,
            "is_enabled": row.is_enabled,
        }
        for row in rows
    ]
    return success_response(request, data=RuleSetListRead(items=items, total=len(items)), meta=None)


@router.get(
    "/rulesets/{rule_set_id}/versions",
    response_model=SuccessEnvelope[RuleVersionListRead, None],
)
def list_rule_versions(
    request: Request,
    rule_set_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
):
    _account_allowed(source_account_ref, allowed_accounts, principal)
    owner = session.get(AiKwRuleSet, rule_set_id)
    if (
        owner is None
        or owner.rule_type != "scoring"
        or owner.scope_key not in ("global", source_account_ref)
    ):
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    versions = list(
        session.scalars(
            select(AiKwRuleVersion)
            .where(
                AiKwRuleVersion.rule_set_id == rule_set_id,
            )
            .order_by(AiKwRuleVersion.version_number.desc())
            .limit(501)
        )
    )
    if len(versions) > 500:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "VERSION_LIMIT_EXCEEDED"},
        )
    return success_response(
        request,
        data=RuleVersionListRead(
            items=[
                {
                    "version_id": str(row.id),
                    "version_number": row.version_number,
                    "status": row.status,
                    "config_sha256": row.config_sha256,
                    "config": row.config_json,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "published_at": row.published_at.isoformat() if row.published_at else None,
                    "publish_eligible": False,  # never infer approval from a version list
                }
                for row in versions
            ],
            total=len(versions),
        ),
        meta=None,
    )


@router.post("/rulesets", response_model=SuccessEnvelope[RuleSetCreateRead, None])
def create_scoring_rule_set(
    request: Request,
    body: CreateRuleSetBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_super_admin)],
):
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "SESSION_NOT_ISOLATED"},
        )
    session.rollback()
    try:
        created = create_scoring_ruleset(
            session,
            account=body.source_account_ref,
            actor=principal.user_id,
            rule_key=body.rule_key,
            display_name=body.display_name,
        )
    except RuleGovernanceBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(
        request,
        data=RuleSetCreateRead(
            rule_set_id=created, status="disabled", publication_authorized=False
        ),
        meta=None,
    )


@router.post("/rulesets/{rule_set_id}/drafts", response_model=SuccessEnvelope[RuleDraftRead, None])
def create_draft(
    request: Request,
    rule_set_id: UUID,
    body: CreateDraftBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_super_admin)],
) -> SuccessEnvelope[RuleDraftRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "SESSION_NOT_ISOLATED"},
        )
    session.rollback()
    try:
        # Disallow unknown keys and bool-as-int when deserializing via dataclass.
        valid_keys = set(asdict(ColdStartLimits()))
        if set(body.limits) - valid_keys:
            raise RuleGovernanceBlocked("UNRECOGNIZED_DRAFT_LIMIT")
        limits = ColdStartLimits(**body.limits)
        receipt = create_scoring_draft(
            session,
            account=body.source_account_ref,
            rule_set_id=rule_set_id,
            actor=principal.user_id,
            limits=limits,
            confirmed_brands=body.confirmed_brands,
            suspected_brands=body.suspected_brands,
            editor_config=body.editor_config,
        )
    except (RuleGovernanceBlocked, TypeError, ValueError) as exc:
        raise _invalid(RuleGovernanceBlocked(str(exc))) from exc
    return success_response(request, data=_receipt(receipt), meta=None)


@router.patch("/rules/{version_id}/draft", response_model=SuccessEnvelope[RuleDraftRead, None])
def save_draft(
    request: Request,
    version_id: UUID,
    body: CreateDraftBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_super_admin)],
) -> SuccessEnvelope[RuleDraftRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _isolated_write(session)
    try:
        if set(body.limits) - set(asdict(ColdStartLimits())):
            raise RuleGovernanceBlocked("UNRECOGNIZED_DRAFT_LIMIT")
        receipt = update_scoring_draft(
            session,
            account=body.source_account_ref,
            version_id=version_id,
            actor=principal.user_id,
            limits=ColdStartLimits(**body.limits),
            confirmed_brands=body.confirmed_brands,
            suspected_brands=body.suspected_brands,
            editor_config=body.editor_config,
        )
    except (RuleGovernanceBlocked, TypeError, ValueError) as exc:
        raise _invalid(RuleGovernanceBlocked(str(exc))) from exc
    return success_response(request, data=_receipt(receipt), meta=None)


@router.post("/rules/{version_id}/retire", response_model=SuccessEnvelope[RuleDraftRead, None])
def retire_rule(
    request: Request,
    version_id: UUID,
    body: RetireBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_super_admin)],
) -> SuccessEnvelope[RuleDraftRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=409,
            details={"reason_code": "SESSION_NOT_ISOLATED"},
        )
    session.rollback()
    try:
        receipt = retire_published_rule(
            session,
            account=body.source_account_ref,
            version_id=version_id,
        )
    except RuleGovernanceBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(request, data=_receipt(receipt), meta=None)


@router.get("/rules/{version_id}/decisions", response_model=SuccessEnvelope[DecisionListRead, None])
def list_rule_decisions(
    request: Request,
    version_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
):
    _account_allowed(source_account_ref, allowed_accounts, principal)
    version = session.get(AiKwRuleVersion, version_id)
    owner = session.get(AiKwRuleSet, version.rule_set_id) if version else None
    if owner is None or owner.scope_key != source_account_ref:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    decisions = list(
        session.scalars(
            select(AiKwRuleDecision)
            .where(
                AiKwRuleDecision.rule_version_id == version_id,
            )
            .order_by(AiKwRuleDecision.decision_key)
        )
    )
    events = (
        list(
            session.scalars(
                select(AiKwRuleDecisionEvent)
                .where(
                    AiKwRuleDecisionEvent.decision_id.in_([row.id for row in decisions]),
                )
                .order_by(AiKwRuleDecisionEvent.created_at, AiKwRuleDecisionEvent.id)
            )
        )
        if decisions
        else []
    )
    return success_response(
        request,
        data=DecisionListRead(
            **{
                "items": [
                    {
                        "decision_key": row.decision_key,
                        "status": row.status,
                        "proposal": row.decision_json,
                        "evidence_ref": row.evidence_ref,
                        "submitted_by": row.submitted_by,
                        "reviewed_by": row.reviewed_by,
                        "config_sha256": row.config_sha256,
                    }
                    for row in decisions
                ],
                "events": [
                    {
                        "decision_id": str(row.decision_id),
                        "action": row.action,
                        "actor": row.actor,
                        "status_after": row.status_after,
                        "evidence_ref": row.evidence_ref,
                    }
                    for row in events
                ],
                "total": len(decisions),
            }
        ),
        meta=None,
    )


@router.post(
    "/rules/{version_id}/decisions/{decision_key}/submit",
    response_model=SuccessEnvelope[DecisionReceipt, None],
)
def submit_decision(
    request: Request,
    version_id: UUID,
    decision_key: str,
    body: DecisionSubmitBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[
        Principal, Depends(require_permission("action:ai-center:keyword-rules:submit"))
    ],
):
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _isolated_write(session)
    try:
        decision_id = submit_rule_decision(
            session,
            account=body.source_account_ref,
            version_id=version_id,
            decision_key=decision_key,
            actor=principal.user_id,
            proposal=body.proposal,
            evidence_ref=body.evidence_ref,
        )
    except RuleGovernanceBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(
        request, data=DecisionReceipt(decision_id=decision_id, status="pending_review"), meta=None
    )


@router.post(
    "/rules/{version_id}/decisions/{decision_key}/review",
    response_model=SuccessEnvelope[DecisionReceipt, None],
)
def review_decision(
    request: Request,
    version_id: UUID,
    decision_key: str,
    body: DecisionReviewBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[
        Principal, Depends(require_permission("action:ai-center:keyword-rules:review"))
    ],
):
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _isolated_write(session)
    try:
        status = review_rule_decision(
            session,
            account=body.source_account_ref,
            version_id=version_id,
            decision_key=decision_key,
            actor=principal.user_id,
            approved=body.approved,
            evidence_ref=body.evidence_ref,
        )
    except RuleGovernanceBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(
        request, data=DecisionReceipt(decision_key=decision_key, status=status), meta=None
    )


@router.post("/rules/{version_id}/publish", response_model=SuccessEnvelope[RuleDraftRead, None])
def publish_rule(
    request: Request,
    version_id: UUID,
    body: RetireBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[
        Principal, Depends(require_permission("action:ai-center:keyword-rules:publish"))
    ],
) -> SuccessEnvelope[RuleDraftRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _isolated_write(session)
    try:
        receipt = publish_scoring_rule(
            session,
            account=body.source_account_ref,
            version_id=version_id,
            actor=principal.user_id,
        )
    except RuleGovernanceBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(request, data=_receipt(receipt), meta=None)
