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
from app.modules.finance_cashflow.account_schemas import (
    CashAccountAdminRead,
    CashAccountCreate,
    CashAccountUpdate,
    ManualLineCreate,
    ManualLineCreated,
)
from app.modules.finance_cashflow.accounts import (
    AccountAdminService,
    AccountNotFoundError,
    AccountRejectedError,
)
from app.modules.finance_cashflow.approval_service import ApprovalService
from app.modules.finance_cashflow.approval_sync import (
    ApprovalSyncNotConfiguredError,
    ApprovalSyncUnavailableError,
    latest_sync,
    start_sync,
)
from app.modules.finance_cashflow.fx_sync import (
    FxSyncNotConfiguredError,
    FxSyncUnavailableError,
    latest_fx_sync,
    start_fx_sync,
)
from app.modules.finance_cashflow.journal import EventRejectedError
from app.modules.finance_cashflow.manual_lines import (
    ManualLineRejectedError,
    apply_running_balances,
    create_manual_line,
)
from app.modules.finance_cashflow.schemas import (
    CashflowAccountRead,
    CashflowAlertCloseRequest,
    CashflowAlertClosureRead,
    CashflowAlertReopenRequest,
    CashflowAnomalyRead,
    CashflowApprovalRead,
    CashflowApprovalSyncData,
    CashflowCategoryRead,
    CashflowFxRateRead,
    CashflowImportListData,
    CashflowImportRead,
    CashflowLineEventData,
    CashflowLineEventRequest,
    CashflowLineListData,
    CashflowPairEventData,
    CashflowPairEventRequest,
    CashflowUploadData,
    CashflowVoidData,
    CashflowVoidRequest,
)
from app.modules.finance_cashflow.service import (
    AlertClosureError,
    CashflowService,
    ImportHasReviewedLinesError,
    ImportNotFoundError,
    ImportVoidedError,
    LineNotFoundError,
    StorageNotConfiguredError,
)
from app.modules.fx_rates.reader import list_usd_cny_rates

logger = logging.getLogger("app.finance_cashflow")

router = APIRouter(prefix="/api/finance/cashflow", tags=["Finance Cashflow"])

db_session = Annotated[Session, Depends(get_db_session)]
# 这一版只有超级管理员能用，不新增权限点。
admin_principal = Annotated[Principal, Depends(require_super_admin)]

# 固定错误码，前端按 code 判断，文案只给人看（docs/api/finance-cashflow-import.md 有对照表）。
ERR_IMPORT_NOT_FOUND = "CASHFLOW_IMPORT_NOT_FOUND"
ERR_IMPORT_VOIDED = "CASHFLOW_IMPORT_VOIDED"
ERR_LINE_NOT_FOUND = "CASHFLOW_LINE_NOT_FOUND"
ERR_ALERT_CLOSURE = "CASHFLOW_ALERT_CLOSURE_INVALID"
ERR_STORAGE_NOT_CONFIGURED = "CASHFLOW_STORAGE_NOT_CONFIGURED"
ERR_UPLOAD_TOO_LARGE = "CASHFLOW_UPLOAD_TOO_LARGE"
ERR_EMPTY_UPLOAD = "CASHFLOW_EMPTY_UPLOAD"
ERR_VOID_REASON_REQUIRED = "CASHFLOW_VOID_REASON_REQUIRED"
ERR_APPROVAL_SYNC_NOT_CONFIGURED = "CASHFLOW_APPROVAL_SYNC_NOT_CONFIGURED"
ERR_APPROVAL_SYNC_UNAVAILABLE = "CASHFLOW_APPROVAL_SYNC_UNAVAILABLE"
ERR_ACCOUNT_NOT_FOUND = "CASHFLOW_ACCOUNT_NOT_FOUND"
ERR_ACCOUNT_REJECTED = "CASHFLOW_ACCOUNT_REJECTED"
ERR_MANUAL_LINE_REJECTED = "CASHFLOW_MANUAL_LINE_REJECTED"
ERR_FX_SYNC_NOT_CONFIGURED = "CASHFLOW_FX_SYNC_NOT_CONFIGURED"
ERR_FX_SYNC_UNAVAILABLE = "CASHFLOW_FX_SYNC_UNAVAILABLE"


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
    "/fx-rates",
    responses=ERRORS,
    operation_id="listFinanceCashflowFxRates",
    summary="领星美元月汇率，只读，新月份在前",
)
def list_fx_rates(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowFxRateRead], None]:
    rows = list_usd_cny_rates(session)
    return success_response(
        request,
        data=[
            CashflowFxRateRead(
                month=row.rate_month, currency_code=row.currency_code, my_rate=row.my_rate
            )
            for row in rows
        ],
    )


@router.get(
    "/fx-rates/sync",
    responses=ERRORS,
    operation_id="getFinanceCashflowFxSync",
    summary="最近一次同步领星汇率的状态",
)
def get_fx_sync(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[CashflowApprovalSyncData, None]:
    return success_response(request, data=latest_fx_sync(session))


@router.post(
    "/fx-rates/sync",
    status_code=202,
    responses=ERRORS,
    operation_id="startFinanceCashflowFxSync",
    summary="手动同步领星汇率（走任务中心的同步任务，已在跑就不重复开）",
)
def post_fx_sync(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[CashflowApprovalSyncData, None]:
    try:
        data = start_fx_sync(session, actor=principal.user_id, request_id=get_request_id(request))
    except FxSyncNotConfiguredError as exc:
        raise ApiError(
            code=ERR_FX_SYNC_NOT_CONFIGURED,
            status_code=409,
            message="汇率同步任务还没打开",
        ) from exc
    except FxSyncUnavailableError as exc:
        raise ApiError(
            code=ERR_FX_SYNC_UNAVAILABLE,
            status_code=503,
            message="任务队列暂时不可用，请稍后再试",
        ) from exc
    return success_response(request, data=data)


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
    # 手工账户（现金等）没有银行余额：从第一笔往下累计后填进去。
    apply_running_balances(session, data.items)
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
    "/alert-closures",
    responses=ERRORS,
    operation_id="listFinanceCashflowAlertClosures",
    summary="已关闭的日记账异常",
)
def list_alert_closures(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashflowAlertClosureRead], None]:
    return success_response(request, data=CashflowService(session).list_alert_closures())


@router.post(
    "/alert-closures",
    responses=ERRORS,
    operation_id="closeFinanceCashflowAlert",
    summary="关闭一条日记账异常（写原因）",
)
def close_alert(
    request: Request,
    session: db_session,
    principal: admin_principal,
    payload: CashflowAlertCloseRequest,
) -> SuccessEnvelope[None, None]:
    try:
        CashflowService(session).close_alert(payload, actor=principal.user_id)
    except AlertClosureError as exc:
        session.rollback()
        raise ApiError(
            code=ERR_ALERT_CLOSURE, status_code=exc.status_code, message=exc.message
        ) from exc
    return success_response(request, data=None)


@router.post(
    "/alert-closures/reopen",
    responses=ERRORS,
    operation_id="reopenFinanceCashflowAlert",
    summary="重新打开一条关闭过的日记账异常（写原因）",
)
def reopen_alert(
    request: Request,
    session: db_session,
    principal: admin_principal,
    payload: CashflowAlertReopenRequest,
) -> SuccessEnvelope[None, None]:
    try:
        CashflowService(session).reopen_alert(payload, actor=principal.user_id)
    except AlertClosureError as exc:
        session.rollback()
        raise ApiError(
            code=ERR_ALERT_CLOSURE, status_code=exc.status_code, message=exc.message
        ) from exc
    return success_response(request, data=None)


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


@router.post(
    "/lines/pair-events",
    responses=ERRORS,
    operation_id="postFinanceCashflowPairEvent",
    summary="配对 / 取消配对：几笔全部成功或者都不变",
)
def post_pair_event(
    request: Request,
    session: db_session,
    principal: admin_principal,
    payload: CashflowPairEventRequest,
) -> SuccessEnvelope[CashflowPairEventData, None]:
    try:
        data = CashflowService(session).post_pair_event(
            payload,
            actor=principal.user_id,
            request_id=get_request_id(request),
        )
    except LineNotFoundError as exc:
        raise ApiError(code=ERR_LINE_NOT_FOUND, status_code=404, message="流水不存在") from exc
    except EventRejectedError as exc:
        raise ApiError(code=exc.code, status_code=exc.status_code, message=exc.message) from exc
    return success_response(request, data=data)


# ------------------------------------------------------------ 账户管理 / 手工录入


@router.get(
    "/accounts/admin",
    responses=ERRORS,
    operation_id="listFinanceCashflowAccountsAdmin",
    summary="账户管理列表（识别值只说填了哪几项，不返回内容）",
)
def list_accounts_admin(
    request: Request,
    session: db_session,
    principal: admin_principal,
) -> SuccessEnvelope[list[CashAccountAdminRead], None]:
    return success_response(request, data=AccountAdminService(session).list_accounts())


def _account_error(exc: AccountRejectedError) -> ApiError:
    return ApiError(code=ERR_ACCOUNT_REJECTED, status_code=exc.status_code, message=exc.message)


@router.post(
    "/accounts",
    status_code=201,
    responses=ERRORS,
    operation_id="createFinanceCashflowAccount",
    summary="新增账户",
)
def create_account(
    request: Request,
    session: db_session,
    principal: admin_principal,
    payload: CashAccountCreate,
) -> SuccessEnvelope[CashAccountAdminRead, None]:
    try:
        data = AccountAdminService(session).create(payload)
    except AccountRejectedError as exc:
        session.rollback()
        raise _account_error(exc) from exc
    logger.info("finance cash account created key=%s by=%s", data.account_key, principal.user_id)
    return success_response(request, data=data)


@router.patch(
    "/accounts/{account_key}",
    responses=ERRORS,
    operation_id="updateFinanceCashflowAccount",
    summary="修改 / 停用 / 启用账户（不能删除）",
)
def update_account(
    request: Request,
    session: db_session,
    principal: admin_principal,
    account_key: str,
    payload: CashAccountUpdate,
) -> SuccessEnvelope[CashAccountAdminRead, None]:
    try:
        data = AccountAdminService(session).update(account_key, payload)
    except AccountNotFoundError as exc:
        session.rollback()
        raise ApiError(code=ERR_ACCOUNT_NOT_FOUND, status_code=404, message="账户不存在") from exc
    except AccountRejectedError as exc:
        session.rollback()
        raise _account_error(exc) from exc
    logger.info("finance cash account updated key=%s by=%s", account_key, principal.user_id)
    return success_response(request, data=data)


@router.post(
    "/manual-lines",
    status_code=201,
    responses=ERRORS,
    operation_id="createFinanceCashflowManualLine",
    summary="手工录入一笔流水（现金，或银行 / 平台流水里没有的费用）",
)
def post_manual_line(
    request: Request,
    session: db_session,
    principal: admin_principal,
    payload: ManualLineCreate,
) -> SuccessEnvelope[ManualLineCreated, None]:
    try:
        data = create_manual_line(
            session, payload, actor=principal.user_id, request_id=get_request_id(request)
        )
    except ManualLineRejectedError as exc:
        session.rollback()
        raise ApiError(
            code=ERR_MANUAL_LINE_REJECTED if exc.status_code != 404 else ERR_ACCOUNT_NOT_FOUND,
            status_code=exc.status_code,
            message=exc.message,
        ) from exc
    return success_response(request, data=data)
