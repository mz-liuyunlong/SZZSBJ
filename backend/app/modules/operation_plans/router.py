from __future__ import annotations

# ruff: noqa: E501
from typing import Annotated, Any
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.operation_plans.schemas import (
    ConflictPolicy,
    OperationPlanClearanceRequest,
    OperationPlanEventListData,
    OperationPlanImportData,
    OperationPlanMeta,
    OperationPlanOptionsData,
    OperationPlanProductListData,
    OperationPlanProductQuery,
    OperationPlanProductRow,
    OperationPlanSummaryData,
    OperationPlanTargetUpdateRequest,
    PeriodType,
)
from app.modules.operation_plans.service import OperationPlanService, template_xlsx

PERMISSION_READ = "operations:plan:read"
PERMISSION_WRITE = "operations:plan:write"

router = APIRouter(prefix="/api/operations/plans", tags=["Operations Plans"])

db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission(PERMISSION_READ))]
write_principal = Annotated[Principal, Depends(require_permission(PERMISSION_WRITE))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def _meta(
    *,
    period_type: PeriodType,
    period_key: str,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> OperationPlanMeta:
    return OperationPlanMeta(
        source_objects=[
            "ops_operation_plan_periods",
            "ops_operation_product_plans",
            "ops_operation_plan_import_batches",
            "ops_operation_plan_import_rows",
            "ops_operation_plan_events",
            "mart_listing_management_current",
        ],
        period_type=period_type,
        period_key=period_key,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/summary",
    response_model=SuccessEnvelope[OperationPlanSummaryData, OperationPlanMeta],
    responses=ERRORS,
    operation_id="getOperationPlanSummary",
    summary="运营计划看板汇总与负责人业绩",
)
def summary(
    request: Request,
    period_type: PeriodType,
    period_key: str,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[OperationPlanSummaryData, OperationPlanMeta]:
    data = OperationPlanService(session).summary(
        period_type=period_type,
        period_key=period_key,
        account_refs=account_refs,
    )
    return success_response(
        request, data=data, meta=_meta(period_type=period_type, period_key=period_key)
    )


@router.get(
    "/products",
    response_model=SuccessEnvelope[OperationPlanProductListData, OperationPlanMeta],
    responses=ERRORS,
    operation_id="listOperationPlanProducts",
    summary="商品计划列表",
)
def products(
    request: Request,
    query: Annotated[OperationPlanProductQuery, Query()],
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[OperationPlanProductListData, OperationPlanMeta]:
    data = OperationPlanService(session).list_products(query=query, account_refs=account_refs)
    return success_response(
        request,
        data=data,
        meta=_meta(
            period_type=query.period_type,
            period_key=query.period_key,
            page=data.page,
            page_size=data.page_size,
            total=data.total,
        ),
    )


@router.get(
    "/options",
    response_model=SuccessEnvelope[OperationPlanOptionsData, OperationPlanMeta],
    responses=ERRORS,
    operation_id="getOperationPlanOptions",
    summary="运营计划筛选项",
)
def options(
    request: Request,
    period_type: PeriodType,
    period_key: str,
    session: db_session,
    _: read_principal,
    account_refs: source_scope,
) -> SuccessEnvelope[OperationPlanOptionsData, OperationPlanMeta]:
    data = OperationPlanService(session).options(
        period_type=period_type,
        period_key=period_key,
        account_refs=account_refs,
    )
    return success_response(
        request, data=data, meta=_meta(period_type=period_type, period_key=period_key)
    )


@router.get(
    "/template",
    responses=ERRORS,
    operation_id="downloadOperationPlanTemplate",
    summary="下载运营计划导入模板",
)
def template(
    _: read_principal,
) -> Response:
    content = template_xlsx()
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="operation-plan-template.xlsx"'},
    )


@router.post(
    "/import",
    response_model=SuccessEnvelope[OperationPlanImportData, OperationPlanMeta],
    responses=ERRORS,
    operation_id="importOperationPlans",
    summary="导入运营计划：成功行直接入库，失败行可下载补录",
)
async def import_plans(
    request: Request,
    session: db_session,
    principal: write_principal,
    account_refs: source_scope,
    period_type: Annotated[PeriodType, Query()],
    period_key: Annotated[str, Query()],
    conflict_policy: Annotated[ConflictPolicy, Query()] = "skip_existing",
    file_name: Annotated[str | None, Header(alias="X-File-Name")] = None,
) -> SuccessEnvelope[OperationPlanImportData, OperationPlanMeta]:
    try:
        content = await request.body()
        if not content:
            raise ValueError("导入文件不能为空")
        data = OperationPlanService(session).import_file(
            file_name=unquote(file_name or "operation-plan-import.xlsx"),
            file_bytes=content,
            period_type=period_type,
            period_key=period_key,
            conflict_policy=conflict_policy,
            account_refs=account_refs,
            actor_ref=principal.user_id,
            request_id=get_request_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(
        request, data=data, meta=_meta(period_type=period_type, period_key=period_key)
    )


@router.get(
    "/import-batches/{batch_id}/failed-export",
    responses=ERRORS,
    operation_id="downloadOperationPlanImportFailedRows",
    summary="下载运营计划导入失败明细",
)
def failed_export(
    batch_id: UUID,
    session: db_session,
    _: read_principal,
) -> Response:
    content = OperationPlanService(session).failed_export(batch_id)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="operation-plan-failed-rows.xlsx"'},
    )


@router.patch(
    "/products/{plan_id}/targets",
    response_model=SuccessEnvelope[OperationPlanProductRow, Any],
    responses=ERRORS,
    operation_id="updateOperationPlanTargets",
    summary="编辑商品计划目标",
)
def update_targets(
    request: Request,
    plan_id: UUID,
    payload: OperationPlanTargetUpdateRequest,
    session: db_session,
    principal: write_principal,
) -> SuccessEnvelope[OperationPlanProductRow, Any]:
    try:
        data = OperationPlanService(session).update_targets(
            plan_id=plan_id,
            payload=payload,
            actor_ref=principal.user_id,
            request_id=get_request_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(request, data=data, meta=None)


@router.post(
    "/products/{plan_id}/clearance",
    response_model=SuccessEnvelope[OperationPlanProductRow, Any],
    responses=ERRORS,
    operation_id="clearOperationPlanProduct",
    summary="单个商品转为清货",
)
def clearance(
    request: Request,
    plan_id: UUID,
    payload: OperationPlanClearanceRequest,
    session: db_session,
    principal: write_principal,
) -> SuccessEnvelope[OperationPlanProductRow, Any]:
    try:
        data = OperationPlanService(session).clearance(
            plan_id=plan_id,
            payload=payload,
            actor_ref=principal.user_id,
            request_id=get_request_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(request, data=data, meta=None)


@router.get(
    "/products/{plan_id}/events",
    response_model=SuccessEnvelope[OperationPlanEventListData, Any],
    responses=ERRORS,
    operation_id="listOperationPlanEvents",
    summary="商品计划调整记录",
)
def events(
    request: Request,
    plan_id: UUID,
    session: db_session,
    _: read_principal,
) -> SuccessEnvelope[OperationPlanEventListData, Any]:
    data = OperationPlanService(session).events(plan_id)
    return success_response(request, data=data, meta=None)
