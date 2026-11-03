"""HTTP routes for the PMC overview board (PRP pmc-overview §5, read-only).

Path prefix ``/api/pmc/overview``. All routes: ``pmc:overview:read`` + trusted
source-account scope (fail closed: an empty scope gets 403), unified envelope,
``response_model`` and ``operation_id``. 5173 transitional source = one 8088 snapshot
file (see :mod:`snapshot`); missing file → 503 ``PMC_OVERVIEW_NOT_READY``, never sample data.
No write route in phase 1 (PRP D5).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_overview import service
from app.modules.pmc_overview.schemas import (
    OverviewExportData,
    OverviewFilterOptionsData,
    OverviewFilterQuery,
    OverviewItemDetail,
    OverviewItemListData,
    OverviewItemsQuery,
    OverviewReadMeta,
    OverviewRuleParam,
    OverviewRulesData,
    OverviewSummaryData,
    OverviewWarehouseData,
)
from app.modules.pmc_overview.snapshot import OverviewBoard, SnapshotNotReady, load_board

PERMISSION_READ = "pmc:overview:read"
NOT_READY = "PMC_OVERVIEW_NOT_READY"
SOURCE_OBJECTS = ("pmc_overview_snapshot_8088",)

router = APIRouter(prefix="/api/pmc/overview", tags=["PMC Overview Board"])

read_principal = Annotated[Principal, Depends(require_permission(PERMISSION_READ))]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _board(accounts: frozenset[str]) -> OverviewBoard:
    # The 8088 snapshot is company-wide; a principal without any source account sees nothing.
    if not accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    try:
        return load_board()
    except SnapshotNotReady as exc:
        raise ApiError(
            code=NOT_READY,
            status_code=503,
            message="总看板数据未就绪",
            details={"reason": str(exc)},
        ) from exc


def _meta(
    board: OverviewBoard,
    *,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> OverviewReadMeta:
    return OverviewReadMeta(
        source_objects=list(SOURCE_OBJECTS),
        data_date=board.today,
        rule_version=board.rule_version,
        draft_mode=board.draft_mode,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/summary",
    response_model=SuccessEnvelope[OverviewSummaryData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewSummary",
    summary="总看板汇总卡片（全部 ItemID，不随筛选变化）",
)
def get_summary(
    request: Request, _: read_principal, accounts: source_scope
) -> SuccessEnvelope[OverviewSummaryData, OverviewReadMeta]:
    board = _board(accounts)
    data = OverviewSummaryData(
        data_date=board.today,
        source=board.source,
        source_note=board.source_note,
        kpi=service.kpi_out(board),
        params={k: int(v) for k, v in board.raw_params.items()},
        parity_with_8088=board.parity,
        unattributed=service.unattributed_out(board),
        overseas_total=board.overseas_total,
    )
    return success_response(request, data=data, meta=_meta(board))


@router.get(
    "/items",
    response_model=SuccessEnvelope[OverviewItemListData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="listPmcOverviewItems",
    summary="ItemID 主表（按问题优先级排序，分页）",
)
def list_items(
    request: Request,
    query: Annotated[OverviewItemsQuery, Query()],
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[OverviewItemListData, OverviewReadMeta]:
    board = _board(accounts)
    rows, total = service.list_items(board, query)
    return success_response(
        request,
        data=OverviewItemListData(items=rows),
        meta=_meta(board, page=query.page, page_size=query.page_size, total=total),
    )


@router.get(
    "/items/{item_id}",
    response_model=SuccessEnvelope[OverviewItemDetail, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewItem",
    summary="ItemID 详情（店铺分布、断货时间线、批次、提示、补货）",
)
def get_item(
    request: Request,
    item_id: Annotated[str, Path(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z_-]+$")],
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[OverviewItemDetail, OverviewReadMeta]:
    board = _board(accounts)
    detail = service.item_detail(board, item_id)
    if detail is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    return success_response(request, data=detail, meta=_meta(board))


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[OverviewFilterOptionsData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewFilterOptions",
    summary="筛选项（店铺、负责人、问题类型）",
)
def filter_options(
    request: Request, _: read_principal, accounts: source_scope
) -> SuccessEnvelope[OverviewFilterOptionsData, OverviewReadMeta]:
    board = _board(accounts)
    data = OverviewFilterOptionsData(
        stores=board.stores, owners=board.owners, categories=service.categories()
    )
    return success_response(request, data=data, meta=_meta(board))


@router.get(
    "/warehouses",
    response_model=SuccessEnvelope[OverviewWarehouseData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewWarehouses",
    summary="仓库分布（国内仓 / 海外仓，有库存的仓）",
)
def warehouses(
    request: Request, _: read_principal, accounts: source_scope
) -> SuccessEnvelope[OverviewWarehouseData, OverviewReadMeta]:
    board = _board(accounts)
    data = OverviewWarehouseData(
        warehouses=service.warehouses_out(board, only_stocked=True),
        overseas_total=board.overseas_total,
    )
    return success_response(request, data=data, meta=_meta(board))


@router.get(
    "/rules",
    response_model=SuccessEnvelope[OverviewRulesData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewRules",
    summary="当前规则参数（一期只读）",
)
def rules(
    request: Request, _: read_principal, accounts: source_scope
) -> SuccessEnvelope[OverviewRulesData, OverviewReadMeta]:
    board = _board(accounts)
    data = OverviewRulesData(
        rule_version=board.rule_version,
        params=[OverviewRuleParam(key=k, value=int(v)) for k, v in board.raw_params.items()],
    )
    return success_response(request, data=data, meta=_meta(board))


@router.get(
    "/export",
    response_model=SuccessEnvelope[OverviewExportData, OverviewReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcOverviewExport",
    summary="下载 Excel 用数据（全部或当前筛选；浏览器生成 5 个工作表）",
)
def export(
    request: Request,
    query: Annotated[OverviewFilterQuery, Query()],
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[OverviewExportData, OverviewReadMeta]:
    board = _board(accounts)
    rows = service.filter_rows(board, query)
    data = OverviewExportData(
        data_date=board.today,
        source_note=board.source_note,
        params={k: int(v) for k, v in board.raw_params.items()},
        store_summary=board.store_summary,
        items=[service.row_out(r) for r in rows],
        ops_heads=list(board.ops.get("heads") or []),
        ops_rows=list(board.ops.get("rows") or []),
        warehouses=service.warehouses_out(board, only_stocked=False),
    )
    return success_response(request, data=data, meta=_meta(board, total=len(rows)))
