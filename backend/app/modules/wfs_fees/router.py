"""WFS 费用明细接口（财务 → WFS 费用明细）。

权限：
- 看：page:finance:wfs-fees:view
- 导入：action:finance:wfs-fees:import（所有店铺都可上传卖家后台下载的报表；Rocky 2026-11-12）
- 调整 / 标已核实：action:finance:wfs-fees:adjust
- 同步：action:finance:wfs-fees:sync（PR 2 接沃尔玛接口；本 PR 只登记权限，不提供接口）
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Final
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.wfs_fees import reader
from app.modules.wfs_fees.parsing import ParseError, expand_upload
from app.modules.wfs_fees.schemas import (
    WfsFeeAdjustRequest,
    WfsFeeCheckListData,
    WfsFeeCheckRead,
    WfsFeeFileListData,
    WfsFeeImportData,
    WfsFeeImportListData,
    WfsFeeLineListData,
    WfsFeeLineRead,
    WfsFeePeriodListData,
    WfsFeeSummaryData,
    WfsFeeTypeRead,
    WfsFeeVerifyRequest,
)
from app.modules.wfs_fees.service import SOURCE_REF, WfsFeeError, WfsFeeService

READ_PERMISSION: Final = "page:finance:wfs-fees:view"
IMPORT_PERMISSION: Final = "action:finance:wfs-fees:import"
ADJUST_PERMISSION: Final = "action:finance:wfs-fees:adjust"
ERR_EMPTY_UPLOAD: Final = "WFS_FEE_EMPTY_UPLOAD"
ERR_TOO_LARGE: Final = "WFS_FEE_UPLOAD_TOO_LARGE"
ERR_BAD_ZIP: Final = "WFS_FEE_BAD_ZIP"
MAX_UPLOAD_BYTES: Final = 16 * 1024 * 1024

router = APIRouter(prefix="/api/finance/wfs-fees", tags=["Finance WFS Fees"])

db_session = Annotated[Session, Depends(get_db_session)]
viewer = Annotated[Principal, Depends(require_permission(READ_PERMISSION))]
importer = Annotated[Principal, Depends(require_permission(IMPORT_PERMISSION))]
adjuster = Annotated[Principal, Depends(require_permission(ADJUST_PERMISSION))]

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _api_error(exc: WfsFeeError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status_code, message=exc.message)


async def _read_limited_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise ApiError(code=ERR_TOO_LARGE, status_code=413, message="文件超过 16MB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise ApiError(code=ERR_TOO_LARGE, status_code=413, message="文件超过 16MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get(
    "/fee-types",
    responses=ERRORS,
    operation_id="listFinanceWfsFeeTypes",
    summary="费用类型（中英文、来源）",
)
def list_fee_types(request: Request, _: viewer) -> SuccessEnvelope[list[WfsFeeTypeRead], None]:
    return success_response(request, data=reader.fee_types())


@router.get(
    "/periods",
    responses=ERRORS,
    operation_id="listFinanceWfsFeePeriods",
    summary="店铺 × 账单期（领星账单），做筛选用",
)
def list_periods(
    request: Request, session: db_session, _: viewer
) -> SuccessEnvelope[WfsFeePeriodListData, None]:
    return success_response(
        request, data=WfsFeePeriodListData(items=reader.list_periods(session, SOURCE_REF))
    )


def line_filter(
    store_id: Annotated[str | None, Query(pattern=r"^[0-9]+(,[0-9]+)*$", max_length=600)] = None,
    report_key: Annotated[str | None, Query(max_length=2000)] = None,
    fee_type: Annotated[str | None, Query(max_length=600)] = None,
    fee_source: Annotated[
        str | None, Query(pattern=r"^(settlement|storage|inbound)(,(settlement|storage|inbound))*$")
    ] = None,
    attribution: Annotated[
        str | None, Query(max_length=120, pattern=r"^[a-z_]+(,[a-z_]+)*$")
    ] = None,
    split: Annotated[str | None, Query(pattern=r"^(yes|no)(,(yes|no))?$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    include_missing: bool = False,
) -> reader.LineFilter:
    """明细和合计共用的筛选；都可逗号分隔多选（Rocky 11-13）。split = 有 / 无分摊。"""
    return reader.LineFilter(
        store_id=store_id,
        report_key=report_key,
        fee_type=fee_type,
        fee_source=fee_source,
        attribution=attribution,
        date_from=date_from,
        date_to=date_to,
        q=q,
        include_missing=include_missing,
        split=split,
    )


filters = Annotated[reader.LineFilter, Depends(line_filter)]


@router.get(
    "/lines",
    responses=ERRORS,
    operation_id="listFinanceWfsFeeLines",
    summary="费用明细（原行带分摊子行），新到旧",
)
def list_lines(
    request: Request,
    session: db_session,
    _: viewer,
    f: filters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=reader.MAX_PAGE_SIZE)] = 100,
) -> SuccessEnvelope[WfsFeeLineListData, None]:
    items, total = reader.list_lines(session, f, page=page, page_size=page_size)
    return success_response(
        request, data=WfsFeeLineListData(items=items, total=total, page=page, page_size=page_size)
    )


@router.get(
    "/summary",
    responses=ERRORS,
    operation_id="summarizeFinanceWfsFees",
    summary="店铺 × 账单期 × 费用类型 合计（筛选与明细相同）",
)
def summarize(
    request: Request, session: db_session, _: viewer, f: filters
) -> SuccessEnvelope[WfsFeeSummaryData, None]:
    items, total = reader.summary(session, f)
    return success_response(
        request, data=WfsFeeSummaryData(items=items, total_amount_usd=f"{total:.4f}")
    )


@router.get(
    "/checks",
    responses=ERRORS,
    operation_id="listFinanceWfsFeeChecks",
    summary="和领星账单的核对结果",
)
def list_checks(
    request: Request,
    session: db_session,
    _: viewer,
    store_id: Annotated[str | None, Query(pattern=r"^[0-9]+(,[0-9]+)*$", max_length=600)] = None,
    report_key: Annotated[str | None, Query(max_length=2000)] = None,
    only_problem: bool = True,
) -> SuccessEnvelope[WfsFeeCheckListData, None]:
    return success_response(
        request,
        data=WfsFeeCheckListData(
            items=reader.list_checks(
                session, store_id=store_id, report_key=report_key, only_problem=only_problem
            )
        ),
    )


@router.get(
    "/files",
    responses=ERRORS,
    operation_id="listFinanceWfsFeeFiles",
    summary="导入 / 同步过的报表文件记录",
)
def list_files(
    request: Request,
    session: db_session,
    _: viewer,
    store_id: Annotated[str | None, Query(pattern=r"^[0-9]+(,[0-9]+)*$", max_length=600)] = None,
    fee_source: Annotated[
        str | None, Query(pattern=r"^(settlement|storage|inbound)(,(settlement|storage|inbound))*$")
    ] = None,
) -> SuccessEnvelope[WfsFeeFileListData, None]:
    return success_response(
        request,
        data=WfsFeeFileListData(
            items=reader.list_files(session, store_id=store_id, fee_source=fee_source)
        ),
    )


@router.post(
    "/imports",
    responses=ERRORS,
    operation_id="uploadFinanceWfsFeeReport",
    summary="上传一份报表（结算 / 仓储 / 入库运输 CSV，或卖家后台 ZIP）；多文件 = 多次调用",
)
async def upload_report(
    request: Request,
    session: db_session,
    principal: importer,
    file_name: Annotated[str | None, Header(alias="X-File-Name")] = None,
    store_id: Annotated[str | None, Header(alias="X-Store-Id", pattern=r"^[0-9]+$")] = None,
    period_start: Annotated[date | None, Header(alias="X-Period-Start")] = None,
    period_end: Annotated[date | None, Header(alias="X-Period-End")] = None,
) -> SuccessEnvelope[WfsFeeImportListData, None]:
    content = await _read_limited_body(request)
    if not content:
        raise ApiError(code=ERR_EMPTY_UPLOAD, status_code=422, message="文件不能为空")
    name = unquote(file_name or "未命名文件")[:200]
    try:
        parts = expand_upload(name, content)
    except ParseError as exc:
        raise ApiError(code=ERR_BAD_ZIP, status_code=422, message=str(exc)) from exc
    service = WfsFeeService(session, get_settings())
    items: list[WfsFeeImportData] = []
    try:
        for part_name, part in parts:
            result = service.upload(
                file_name=part_name[:255],
                content=part,
                actor=principal.user_id,
                request_id=get_request_id(request),
                store_id=store_id,
                period_start=period_start,
                period_end=period_end,
            )
            items.append(WfsFeeImportData(**result.__dict__))
    except WfsFeeError as exc:
        raise _api_error(exc) from exc
    return success_response(request, data=WfsFeeImportListData(items=items))


@router.post(
    "/lines/{line_id}/adjust",
    responses=ERRORS,
    operation_id="adjustFinanceWfsFeeLine",
    summary="调整归属：改分摊 / 记公司（必填原因，留痕）",
)
def adjust_line(
    request: Request,
    session: db_session,
    principal: adjuster,
    line_id: UUID,
    body: WfsFeeAdjustRequest,
) -> SuccessEnvelope[WfsFeeLineRead, None]:
    try:
        row = WfsFeeService(session, get_settings()).adjust(
            line_id,
            kind=body.kind,
            payload=body.payload,
            reason=body.reason,
            actor=principal.user_id,
            request_id=get_request_id(request),
        )
    except WfsFeeError as exc:
        raise _api_error(exc) from exc
    item = reader.get_line(session, row.id)
    assert item is not None
    return success_response(request, data=item)


@router.post(
    "/checks/verify",
    responses=ERRORS,
    operation_id="verifyFinanceWfsFeeCheck",
    summary="核对差异标已核实（必填原因）",
)
def verify_check(
    request: Request, session: db_session, principal: adjuster, body: WfsFeeVerifyRequest
) -> SuccessEnvelope[WfsFeeCheckRead, None]:
    try:
        check = WfsFeeService(session, get_settings()).verify_check(
            store_id=body.store_id,
            report_key=body.report_key,
            fee_type=body.fee_type,
            reason=body.reason,
            actor=principal.user_id,
        )
    except WfsFeeError as exc:
        raise _api_error(exc) from exc
    # 同一店铺 × 账单期下有多种费用类型：返回刚标的这一条（复审 P3）
    items = reader.list_checks(
        session, store_id=check.store_id, report_key=check.report_key, only_problem=False
    )
    return success_response(
        request, data=next(item for item in items if item.fee_type == check.fee_type)
    )
