from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.business_rules.schemas import (
    StoreCommissionDeactivateRequest,
    StoreCommissionListData,
    StoreCommissionMutationData,
    StoreCommissionOperationLogData,
    StoreCommissionRecalculateData,
    StoreCommissionRecalculateRequest,
    StoreCommissionUpsertRequest,
)
from app.modules.business_rules.service import (
    BusinessRulesService,
    run_store_commission_recalculate_job,
)
from app.modules.integration_sync.dependencies import require_source_account_scope

router = APIRouter(prefix="/api/business-rules", tags=["Business Rules"])

db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission("business-rules:read"))]
write_principal = Annotated[Principal, Depends(require_permission("business-rules:write"))]
execute_principal = Annotated[Principal, Depends(require_permission("business-rules:execute"))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


@router.get(
    "/store-commissions",
    response_model=SuccessEnvelope[StoreCommissionListData, Any],
    responses=ERRORS,
)
def list_store_commissions(
    request: Request,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[StoreCommissionListData, Any]:
    return success_response(
        request,
        data=BusinessRulesService(session).list_store_commissions(account_refs),
        meta=None,
    )


@router.post(
    "/store-commissions",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[StoreCommissionMutationData, Any],
    responses=ERRORS,
)
def upsert_store_commission(
    request: Request,
    payload: StoreCommissionUpsertRequest,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[StoreCommissionMutationData, Any]:
    try:
        data = BusinessRulesService(session).upsert_store_commission(
            payload=payload,
            account_refs=account_refs,
            actor_ref=principal.user_id,
            request_id=get_request_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(request, data=data, meta=None)


@router.post(
    "/store-commissions/deactivate",
    response_model=SuccessEnvelope[StoreCommissionMutationData, Any],
    responses=ERRORS,
)
def deactivate_store_commission(
    request: Request,
    payload: StoreCommissionDeactivateRequest,
    session: db_session,
    _: write_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[StoreCommissionMutationData, Any]:
    try:
        data = BusinessRulesService(session).deactivate_store_commission(
            payload=payload,
            account_refs=account_refs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(request, data=data, meta=None)


@router.get(
    "/store-commissions/logs",
    response_model=SuccessEnvelope[StoreCommissionOperationLogData, Any],
    responses=ERRORS,
)
def list_store_commission_operation_logs(
    request: Request,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[StoreCommissionOperationLogData, Any]:
    return success_response(
        request,
        data=BusinessRulesService(session).list_store_commission_operation_logs(account_refs),
        meta=None,
    )


@router.post(
    "/store-commissions/recalculate",
    response_model=SuccessEnvelope[StoreCommissionRecalculateData, Any],
    responses=ERRORS,
)
def recalculate_store_commission(
    request: Request,
    payload: StoreCommissionRecalculateRequest,
    background_tasks: BackgroundTasks,
    session: db_session,
    principal: execute_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[StoreCommissionRecalculateData, Any]:
    try:
        data = BusinessRulesService(session).recalculate_store_commissions(
            payload=payload,
            account_refs=account_refs,
            actor_ref=principal.user_id,
            request_id=get_request_id(request),
        )
        if data.status == "queued":
            background_tasks.add_task(run_store_commission_recalculate_job, data.operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(request, data=data, meta=None)
