"""Scoped clearance APIs. No endpoint issues Walmart repricing or ad actions."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import has_permission, require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope

from . import hybrid_v28, service
from .local_store_v28 import is_local, storage_session
from .rules import CLEARANCE_RULE_CATALOG, ClearanceRules

router = APIRouter(prefix="/api/clearance", tags=["WFS Clearance Center"])
db_session = Annotated[Session, Depends(get_db_session)]
account_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
authenticated = Annotated[Principal, Depends(require_principal)]
view = Annotated[
    Principal,
    Depends(
        require_any_permission(
            "page:products:product-management:view", "action:products:clearance-center:review"
        )
    ),
]
manage = Annotated[
    Principal, Depends(require_permission("action:products:clearance-center:manage-rules"))
]
review = Annotated[
    Principal, Depends(require_permission("action:products:clearance-center:review"))
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleUpdate(Strict):
    expected_version: int = Field(ge=1)
    config: ClearanceRules
    reason: str = Field(min_length=2, max_length=500)


class ClearanceApply(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=1, max_length=128)
    qty: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=160)
    methods: list[Literal["降价", "广告清货"]] = Field(min_length=1, max_length=2)
    note: str = Field(default="", max_length=4000)
    planned_completion_date: date | None = None


class ClearanceDecision(Strict):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=4000)
    expected_version: int = Field(ge=1)


class NoteWrite(Strict):
    note: str = Field(default="", max_length=4000)


@router.get("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def rules_get(request: Request, session: db_session, principal: view):
    with storage_session(session) as store:
        version, config = service.rule_version(store, require_persisted=True)
    return success_response(
        request,
        data={
            "version": version,
            "config": config.model_dump(),
            "catalog": [
                {"group": group, "key": key, "label": label, "kind": kind}
                for group, key, label, kind in CLEARANCE_RULE_CATALOG
            ],
            "can_edit": has_permission(principal, "action:products:clearance-center:manage-rules"),
        },
        meta=None,
    )


def rules_history_from_store(read: Session, offset: int, limit: int) -> list[dict]:
    with storage_session(read) as store:
        return service.rules_history(store, offset, limit)


@router.get("/rules/history", response_model=SuccessEnvelope[dict[str, Any], None])
def rules_history(
    request: Request,
    session: db_session,
    principal: view,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return success_response(
        request,
        data={
            "items": rules_history_from_store(session, (page - 1) * page_size, page_size),
            "page": page,
            "page_size": page_size,
        },
        meta=None,
    )


@router.put("/rules", response_model=SuccessEnvelope[dict[str, Any], None])
def rules_save(request: Request, payload: RuleUpdate, session: db_session, principal: manage):
    with storage_session(session, writable=True) as store:
        version = service.save_rules(
            store, payload.config, payload.expected_version, payload.reason, principal.user_id
        )
    # Rule saves never bypass owner authorization by dispatching production recalculation.
    return success_response(
        request, data={"version": version, "recalculation": "not_dispatched"}, meta=None
    )


@router.post("/recalculate", response_model=SuccessEnvelope[dict[str, Any], None])
def recalculate(request: Request, session: db_session, principal: manage):
    # Explicitly authorized manual recalculation; never dispatch an automatic task.
    # In local mode the source Session reads 15432 and the storage Session writes 55433.
    if is_local():
        with storage_session(session, writable=True) as write:
            result = service.recalculate_all(session, risk_session=write)
    else:
        from .tasks import run_daily

        result = run_daily(retry_failed=True)
    return success_response(request, data=result, meta=None)


@router.get("/filter-options", response_model=SuccessEnvelope[dict[str, Any], None])
def filter_options(request: Request, session: db_session, principal: view, accounts: account_scope):
    from .filters_v23 import list_filter_options

    return success_response(request, data=list_filter_options(session, accounts), meta=None)


@router.get("/listings", response_model=SuccessEnvelope[dict[str, Any], None])
def listings(
    request: Request,
    session: db_session,
    principal: view,
    accounts: account_scope,
    keyword: str = Query(default="", max_length=128),
    risk_only: bool = True,
    exact_total: bool = False,
    store_refs: list[str] = Query(default=[], max_length=200),  # noqa: B008
    owner_names: list[str] = Query(default=[], max_length=200),  # noqa: B008
    risk_levels: list[Literal["high", "medium", "low", "none", "unknown"]] = Query(  # noqa: B008
        default=[], max_length=5
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    return success_response(
        request,
        data=service.search_listings(
            session,
            accounts,
            keyword,
            page,
            page_size,
            risk_only=risk_only,
            exact_total=exact_total,
            store_refs=tuple(store_refs),
            owner_names=tuple(owner_names),
            risk_levels=tuple(risk_levels),
        ),
        meta=None,
    )


@router.get("/listing", response_model=SuccessEnvelope[dict[str, Any], None])
def listing_detail(
    request: Request,
    session: db_session,
    principal: view,
    accounts: account_scope,
    source_account_ref: str,
    store_id: str,
    item_id: str,
):
    return success_response(
        request,
        data=service.one_listing(
            session, account=source_account_ref, store=store_id, item=item_id, accounts=accounts
        ),
        meta=None,
    )


@router.post("/applications", response_model=SuccessEnvelope[dict[str, Any], None])
def apply(
    request: Request,
    payload: ClearanceApply,
    session: db_session,
    principal: authenticated,
    accounts: account_scope,
):
    with storage_session(session, writable=True) as write:
        return success_response(
            request,
            data=hybrid_v28.submit_application(
                session,
                write,
                account=payload.source_account_ref,
                store=payload.store_id,
                item=payload.item_id,
                accounts=accounts,
                actor=principal.user_id,
                qty=payload.qty,
                reason=payload.reason,
                methods=payload.methods,
                note=payload.note,
                due=payload.planned_completion_date.isoformat()
                if payload.planned_completion_date
                else None,
            ),
            meta=None,
        )


@router.get("/applications", response_model=SuccessEnvelope[dict[str, Any], None])
def application_list(
    request: Request,
    session: db_session,
    principal: view,
    accounts: account_scope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: str | None = None,
):
    reviewer = has_permission(principal, "action:products:clearance-center:review")
    with storage_session(session) as write:
        return success_response(
            request,
            data=hybrid_v28.list_applications(
                session,
                write,
                accounts,
                principal.user_id,
                reviewer=reviewer,
                page=page,
                page_size=page_size,
                status=status,
            ),
            meta=None,
        )


@router.get("/applications/{application_id}", response_model=SuccessEnvelope[dict[str, Any], None])
def application_detail(
    request: Request,
    application_id: UUID,
    session: db_session,
    principal: view,
    accounts: account_scope,
):
    reviewer = has_permission(principal, "action:products:clearance-center:review")
    with storage_session(session) as write:
        return success_response(
            request,
            data=hybrid_v28.application_detail(
                session, write, application_id, accounts, principal.user_id, reviewer=reviewer
            ),
            meta=None,
        )


@router.post(
    "/applications/{application_id}/cancel", response_model=SuccessEnvelope[dict[str, Any], None]
)
def cancel(
    request: Request,
    application_id: UUID,
    payload: NoteWrite,
    session: db_session,
    principal: view,
    accounts: account_scope,
):
    with storage_session(session, writable=True) as write:
        return success_response(
            request,
            data=hybrid_v28.cancel_application(
                session, write, application_id, accounts, principal.user_id, payload.note
            ),
            meta=None,
        )


@router.post(
    "/applications/{application_id}/review", response_model=SuccessEnvelope[dict[str, Any], None]
)
def review_one(
    request: Request,
    application_id: UUID,
    payload: ClearanceDecision,
    session: db_session,
    principal: review,
    accounts: account_scope,
):
    with storage_session(session, writable=True) as write:
        return success_response(
            request,
            data=hybrid_v28.review_application(
                session,
                write,
                application_id,
                accounts,
                principal.user_id,
                payload.decision,
                payload.note,
                payload.expected_version,
            ),
            meta=None,
        )


@router.post(
    "/applications/{application_id}/complete", response_model=SuccessEnvelope[dict[str, Any], None]
)
def complete(
    request: Request,
    application_id: UUID,
    payload: NoteWrite,
    session: db_session,
    principal: view,
    accounts: account_scope,
):
    can_manage = has_permission(principal, "action:products:clearance-center:complete")
    with storage_session(session, writable=True) as write:
        return success_response(
            request,
            data=hybrid_v28.complete_application(
                session,
                write,
                application_id,
                accounts,
                principal.user_id,
                payload.note,
                can_manage=can_manage,
            ),
            meta=None,
        )


@router.post(
    "/applications/{application_id}/reconcile", response_model=SuccessEnvelope[dict[str, Any], None]
)
def reconcile(
    request: Request,
    application_id: UUID,
    session: db_session,
    principal: view,
    accounts: account_scope,
):
    with storage_session(session, writable=True) as write:
        return success_response(
            request,
            data=hybrid_v28.reconcile_application(session, write, application_id, accounts),
            meta=None,
        )


@router.get("/lifecycle-overrides", response_model=SuccessEnvelope[dict[str, Any], None])
def lifecycle_overrides(
    request: Request, session: db_session, principal: view, accounts: account_scope
):
    with storage_session(session) as write:
        return success_response(
            request,
            data={"items": hybrid_v28.lifecycle_overrides(session, write, accounts)},
            meta=None,
        )
