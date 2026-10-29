"""WFS exception center M1: case workflow; auto-detection stubbed."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_wfs.exception_schemas import (
    AssignCommand,
    CaseEventCommand,
    ExceptionDetail,
    ExceptionFilter,
    ExceptionList,
    ExceptionOptions,
    ExceptionQuery,
    ExceptionSummary,
)
from app.modules.pmc_wfs.exception_service import ExceptionCenterService

router = APIRouter(prefix="/api/pmc/wfs/exception-center", tags=["PMC WFS Exception Center"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
AssignPerm = Annotated[Principal, Depends(require_permission("action:pmc:wfs-exceptions:assign"))]
HandlePerm = Annotated[Principal, Depends(require_permission("action:pmc:wfs-exceptions:handle"))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500, 503)}


def service(session: DB, accounts: Accounts, actor: Read):
    if "*" in actor.permissions:
        stores = None
    else:
        try:
            uid = int(actor.user_id)
        except ValueError:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403) from None
        values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
        stores = None if "*" in values else frozenset(values)
        if stores == frozenset():
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
    return ExceptionCenterService(session, accounts, stores)


Service = Annotated[ExceptionCenterService, Depends(service)]


def meta(extra: dict | None = None):
    base = {
        "source": "new_system_postgresql",
        "rule_engine": "M1_STUB",
        "lingxing_sync_enabled": False,
        "source_tables": [
            "ops_wfs_exception_cases",
            "evt_wfs_exception_detections",
            "evt_wfs_exception_actions",
            "dim_lingxing_stores",
        ],
    }
    if extra:
        base.update(extra)
    return base


@router.get("/cases", response_model=SuccessEnvelope[ExceptionList, dict], responses=ERRORS)
def list_cases(request: Request, query: Annotated[ExceptionQuery, Query()], svc: Service):
    return success_response(request, data=svc.list(query), meta=meta())


@router.get("/cases/{case_id}", response_model=SuccessEnvelope[ExceptionDetail, dict], responses=ERRORS)
def case_detail(request: Request, case_id: UUID, svc: Service):
    return success_response(request, data=svc.detail(case_id), meta=meta())


@router.get("/summary", response_model=SuccessEnvelope[ExceptionSummary, dict], responses=ERRORS)
def summary(request: Request, query: Annotated[ExceptionFilter, Query()], svc: Service):
    return success_response(request, data=svc.summary(query), meta=meta())


@router.get("/filter-options", response_model=SuccessEnvelope[ExceptionOptions, dict], responses=ERRORS)
def filter_options(request: Request, svc: Service):
    return success_response(request, data=svc.options(), meta=meta())


@router.post(
    "/cases/{case_id}/assign",
    response_model=SuccessEnvelope[ExceptionDetail, dict],
    responses=ERRORS,
)
def assign_case(
    request: Request,
    case_id: UUID,
    body: AssignCommand,
    svc: Service,
    actor: AssignPerm,
):
    return success_response(
        request,
        data=svc.assign(case_id, actor.user_id, body),
        meta=meta(),
    )


@router.post(
    "/cases/{case_id}/events",
    response_model=SuccessEnvelope[ExceptionDetail, dict],
    responses=ERRORS,
)
def case_event(
    request: Request,
    case_id: UUID,
    body: CaseEventCommand,
    svc: Service,
    actor: HandlePerm,
):
    return success_response(
        request,
        data=svc.post_event(case_id, actor.user_id, body),
        meta=meta(),
    )
