"""Permission-protected preparation routes. Approval and Walmart operations are absent."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_wfs.schemas import (
    DraftCommand,
    DraftRead,
    DraftResult,
    IdentityCommand,
    IdentityOptions,
    PendingFilter,
    PendingList,
    PendingOptions,
    PendingQuery,
    PendingRow,
    PendingSummary,
)
from app.modules.pmc_wfs.service import WfsService

router = APIRouter(prefix="/api/pmc/wfs/pending-packing", tags=["PMC WFS Pending Packing"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
Submit = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:draft-submit"))
]
Switch = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:identity-switch"))
]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500)}


def service(session: DB, accounts: Accounts, actor: Read):
    if "*" in actor.permissions:
        stores = None
    else:
        try:
            uid = int(actor.user_id)
        except ValueError:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
        values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
        stores = None if "*" in values else frozenset(values)
        if stores == frozenset():
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return WfsService(session, accounts, stores)


Service = Annotated[WfsService, Depends(service)]


def response(request, data):
    return success_response(
        request,
        data=data,
        meta={
            "source": "new_system_postgresql",
            "execution_enabled": False,
            "source_tables": [
                "ops_domestic_packing_orders",
                "ops_domestic_packing_box_sets",
                "ops_domestic_packing_box_lines",
                "ops_pmc_wfs_box_allocations",
            ],
        },
    )


@router.get("/orders", response_model=SuccessEnvelope[PendingList, dict], responses=ERRORS)
def orders(request: Request, query: Annotated[PendingQuery, Query()], svc: Service):
    return response(request, svc.list(query))


@router.get("/summary", response_model=SuccessEnvelope[PendingSummary, dict], responses=ERRORS)
def summary(request: Request, query: Annotated[PendingFilter, Query()], svc: Service):
    return response(request, svc.summary(query))


@router.get(
    "/filter-options", response_model=SuccessEnvelope[PendingOptions, dict], responses=ERRORS
)
def options(request: Request, svc: Service):
    return response(request, svc.options())


@router.get("/orders/{ident}", response_model=SuccessEnvelope[PendingRow, dict], responses=ERRORS)
def detail(request: Request, ident: UUID, svc: Service):
    return response(request, svc.detail(ident))


@router.get(
    "/orders/{ident}/identity-options",
    response_model=SuccessEnvelope[IdentityOptions, dict],
    responses=ERRORS,
)
def identity_options(request: Request, ident: UUID, svc: Service):
    return response(request, svc.identity_options(ident))


@router.post(
    "/orders/{ident}/identity",
    response_model=SuccessEnvelope[PendingRow, dict],
    responses=ERRORS,
)
def identity(request: Request, ident: UUID, body: IdentityCommand, svc: Service, actor: Switch):
    return response(request, svc.switch(ident, body, actor.user_id))


@router.post("/drafts", response_model=SuccessEnvelope[DraftResult, dict], responses=ERRORS)
def submit(request: Request, body: DraftCommand, svc: Service, actor: Submit):
    return response(request, svc.submit(body, actor.user_id))


@router.get("/drafts/{ident}", response_model=SuccessEnvelope[DraftRead, dict], responses=ERRORS)
def draft(request: Request, ident: UUID, svc: Service):
    return response(request, svc.draft(ident))
