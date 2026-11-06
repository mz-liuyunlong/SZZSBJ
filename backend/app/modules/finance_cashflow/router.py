from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.permissions import require_super_admin
from app.db.session import get_db_session
from app.modules.finance_cashflow.approval_service import ApprovalService
from app.modules.finance_cashflow.approval_sync import (
    ApprovalSyncNotConfiguredError,
    ApprovalSyncUnavailableError,
    latest_sync,
    start_sync,
)
from app.modules.finance_cashflow.journal import EventRejectedError
from app.modules.finance_cashflow.schemas import (
    CashflowAccountRead,
    CashflowAnomalyRead,
    CashflowApprovalRead,
    CashflowApprovalSyncData,
    CashflowCategoryRead,
    CashflowImportListData,
    CashflowImportRead,
    CashflowLineEventData,
    CashflowLineEventRequest,
    CashflowLineListData,
    CashflowUploadData,
    CashflowVoidData,
    CashflowVoidRequest,
)
from app.modules.finance_cashflow.service import (
    CashflowService,
    ImportHasReviewedLinesError,
    ImportNotFoundError,
    ImportVoidedError,
    LineNotFoundError,
    StorageNotConfiguredError,
)

logger = logging.getLogger("app.finance_cashflow")

router = APIRouter(prefix="/api/finance/cashflow", tags=["Finance Cashflow"])

db_session = Annotated[Session, Depends(get_db_session)]
# 这一版只有超级管理员能用，不新增权限点。
admin_principal = Annotated[Principal, Depends(require_super_admin)]

# 固定错误码，前端按 code 判断，文案只给人看（docs/api/finance-cashflow-import.md 有对照表）。
ERR_IMPORT_NOT_FOUND = "CASHFLOW_IMPORT_NOT_FOUND"
ERR_IMPORT_VOIDED = "CASHFLOW_IMPORT_VOIDED"
ERR_LINE_NOT_FOUND = "CASHFLOW_LINE_NOT_FOUND"
ERR_STORAGE_NOT_CONFIGURED = "CASHFLOW_STORAGE_NOT_CONFIGURED"
ERR_UPLOAD_TOO_LARGE = "CASHFLOW_UPLOAD_TOO_LARGE"
ERR_EMPTY_UPLOAD = "CASHFLOW_EMPTY_UPLOAD"
ERR_VOID_REASON_REQUIRED = "CASHFLOW_VOID_REASON_REQUIRED"
ERR_APPROVAL_SYNC_NOT_CONFIGURED = "CASHFLOW_APPROVAL_SYNC_NOT_CONFIGURED"
ERR_APPROVAL_SYNC_UNAVAILABLE = "CASHFLOW_APPROVAL_SYNC_UNAVAILABLE"


def _too_large() -> ApiError:
    return ApiError(code=ERR_UPLOAD_TOO_LARGE, status_code=413, message="文件超过上传上限")


def _import_not_found() -> ApiError:
    return ApiError(code=ERR_IMPORT_NOT_FOUND, status_code=404, message="导入批次不存在")


def _import_voided() -> ApiError:
    return ApiError(code=ERR_IMPORT_VOIDED, status_code=409, message="这一批已作废")


ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


async def _read_limited_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/imports",
    responses=ERRORS,
    operation_id="uploadFinanceCashflowFile",
    summary="上传一份银行或平台流水文件；多文件 = 多次调用，用 X-Import-Id 归入同一批",
)
async def upload_file(
    request: Request,
    session: db_session,
    principal: admin_principal,
    file_name: Annotated[str | None, Header(alias="X-File-Name")] = None,
    import_id: Annotated[UUID | None, Header(alias="X-Import-Id")] = None,
) -> SuccessEnvelope[CashflowUploadData, None]:
    settings = get_settings()
    content = await _read_limited_body(request, settings.finance_cashflow_max_upload_bytes)
    if not content:
        raise ApiError(code=ERR_EMPTY_UPLOAD, status_code=422, message="文件不能为空")
    try:
        data = CashflowService(session, settings).upload(
            import_id=import_id,
            file_name=unquote(file_name or "未命名文件")[:255],
            content=content,
            actor=principal.user_id,
            request_id=get_request_id(request),
        )
    except StorageNotConfiguredError as exc:
        raise ApiError(
            code=ERR_STORAGE_NOT_CONFIGURED, status_code=503, message="原件存储目录未配置"
        ) from exc
    except ImportVoidedError as exc:
        raise _import_voided() from exc
    if data.file.status == "parsed":
        _auto_match_quietly(session, get_request_id(request))
    return success_response(request, data=data)


def _auto_match_quietly(session: Session, request_id: str) -> None:
    """流水新导入后试一次自动挂单；失败不影响上传，下次同步还会再挂。"""
    try:
        ApprovalService(session).auto_match(request_id=request_id)
    except Exception:
        session.rollback()
        logger.exception("finance_approval_auto_match_after_upload_failed")


@router.get(
    "/imports",
    responses=ERRORS,
    operation_id="listFinanceCashflowImports",
    summary="导入批次列表",
)
def list_imports(
    request: Request,
    session: db_session,
    principal: admin_principal,
    status: Annotated[str | None, Query(max_length=16)] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SuccessEnvelope[CashflowImportListData, None]:
    data = CashflowService(session).list_imports(
        status=status, from_date=from_date, to_date=to_date, page=page, page_size=page_size
    )
    return success_response(request, data=data)


@router.get(
    "/imports/{import_id}",
    responses=ERRORS,
    operation_id="getFinanceCashflowImport",
    summary="一批导入的详情",
)
def get_import(
    request: Request,
    session: db_session,
    principal: admin_principal,
    import_id: UUID,
) -> SuccessEnvelope[CashflowImportRead, None]:
    try:
        data = CashflowService(session).get_import(import_id)
    except ImportNotFoundError as exc:
        raise _import_not_found() from exc
    return success_response(request, data=data)


@router.post(
    "/imports/{import_id}/void",
    responses=ERRORS,
    operation_id="voidFinanceCashflowImport",
    summary="整批作废（必填原因）",
)
def void_import(
    request: Request,
    session: db_session,
    principal: admin_principal,
    import_id: UUID,
    payload: CashflowVoidRequest,
) -> SuccessEnvelope[CashflowVoidData, None]:
    if not payload.reason.strip():
        raise ApiError(code=ERR_VOID_REASON_REQUIRED, status_code=422, message="作废必须填原因")
    try:
        data = CashflowService(session).void_import(
            import_id, reason=payload.reason, actor=principal.user_id
        )
    except ImportHasReviewedLinesError as exc:
        raise ApiError(
            code="CASHFLOW_IMPORT_HAS_REVIEWED_LINES",
            status_code=409,
            message="这一批里有已审核的流水，要先退回审核才能作废",
            details={"count": len(exc.line_uids), "line_ids": exc.line_uids},
        ) from exc
    except ImportNotFoundError as exc:
        raise _import_not_found() from exc
    except ImportVoidedError as exc:
        raise _import_voided() from exc
    return success_response(request, data=data)


@router.get(
    "/accounts",
    responses=ERRORS,
    operation_id="listFinanceCashflowAccounts",
    summary="账户，含流水条数、最近文件和覆盖区间",
)
def list_accounts(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowAccountRead], None]:
    return success_response(request, data=CashflowService(session).list_accounts())


@router.get(
    "/categories",
    responses=ERRORS,
    operation_id="listFinanceCashflowCategories",
    summary="类别字典",
)
def list_categories(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowCategoryRead], None]:
    return success_response(request, data=CashflowService(session).list_categories())


@router.get(
    "/lines",
    responses=ERRORS,
    operation_id="listFinanceCashflowLines",
    summary="日记账流水",
)
def list_lines(
    request: Request,
    session: db_session,
    principal: admin_principal,
    account_key: Annotated[str | None, Query(max_length=64)] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> SuccessEnvelope[CashflowLineListData, None]:
    data = CashflowService(session).list_lines(
        account_key=account_key,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    return success_response(request, data=data)


@router.get(
    "/anomalies",
    responses=ERRORS,
    operation_id="listFinanceCashflowAnomalies",
    summary="日记账异常（读时计算）",
)
def list_anomalies(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowAnomalyRead], None]:
    return success_response(request, data=CashflowService(session).list_anomalies())


@router.get(
    "/approvals",
    responses=ERRORS,
    operation_id="listFinanceCashflowApprovals",
    summary="飞书审批单，含已付情况",
)
def list_approvals(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowApprovalRead], None]:
    return success_response(request, data=ApprovalService(session).list_approvals())


@router.get(
    "/approvals/sync",
    responses=ERRORS,
    operation_id="getFinanceCashflowApprovalSync",
    summary="最近一次同步审批单的状态",
)
def get_approval_sync(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[CashflowApprovalSyncData, None]:
    return success_response(request, data=latest_sync(session))


@router.post(
    "/approvals/sync",
    status_code=202,
    responses=ERRORS,
    operation_id="startFinanceCashflowApprovalSync",
    summary="手动同步审批单（走任务中心的同步任务，已在跑就不重复开）",
)
def post_approval_sync(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[CashflowApprovalSyncData, None]:
    try:
        data = start_sync(session, actor=principal.user_id, request_id=get_request_id(request))
    except ApprovalSyncNotConfiguredError as exc:
        raise ApiError(
            code=ERR_APPROVAL_SYNC_NOT_CONFIGURED,
            status_code=409,
            message="审批单同步任务还没配置",
        ) from exc
    except ApprovalSyncUnavailableError as exc:
        raise ApiError(
            code=ERR_APPROVAL_SYNC_UNAVAILABLE,
            status_code=503,
            message="任务队列暂时不可用，请稍后再试",
        ) from exc
    return success_response(request, data=data)


@router.post(
    "/lines/{line_uid}/events",
    responses=ERRORS,
    operation_id="postFinanceCashflowLineEvent",
    summary="人工动作：初审、终审、改类别、挂单号、剔除",
)
def post_line_event(
    request: Request,
    session: db_session,
    principal: admin_principal,
    line_uid: str,
    payload: CashflowLineEventRequest,
) -> SuccessEnvelope[CashflowLineEventData, None]:
    try:
        data = CashflowService(session).post_event(
            line_uid,
            payload,
            actor=principal.user_id,
            request_id=get_request_id(request),
        )
    except LineNotFoundError as exc:
        session.rollback()
        raise ApiError(code=ERR_LINE_NOT_FOUND, status_code=404, message="流水不存在") from exc
    except EventRejectedError as exc:
        session.rollback()
        raise ApiError(code=exc.code, status_code=exc.status_code, message=exc.message) from exc
    return success_response(request, data=data)
