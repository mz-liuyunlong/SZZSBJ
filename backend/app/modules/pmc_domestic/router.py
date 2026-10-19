"""Domestic warehouse batch board. Read-only, account scoped."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.registry import PERMISSION_READ
from app.modules.pmc_domestic.schemas import (
    BatchFilterQuery,
    BatchListData,
    BatchListQuery,
    BatchRowRead,
    BatchSummaryData,
    BatchTraceData,
    DomesticFilterOptionsData,
    DomesticReadMeta,
)
from app.modules.pmc_domestic.service import PmcDomesticBatchReadService

router = APIRouter(prefix="/api/pmc/domestic", tags=["PMC Domestic Batch Board"])

db_session = Annotated[Session, Depends(get_db_session)]
source_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_principal = Annotated[Principal, Depends(require_permission(PERMISSION_READ))]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}

BATCH_OBJECTS = ("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link")
OWNER_OBJECTS = ("dwd_lingxing_sku_identity_index", "dwd_lingxing_sku_product_info_current")


def _meta(
    *objects: str,
    freshness_at: datetime | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> DomesticReadMeta:
    return DomesticReadMeta(
        source_objects=list(objects),
        freshness_at=freshness_at,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[DomesticFilterOptionsData, DomesticReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcDomesticFilterOptions",
    summary="国内仓可见批次的店铺与当前产品负责人选项",
)
def filter_options(
    request: Request, session: db_session, _: read_principal, accounts: source_scope,
) -> SuccessEnvelope[DomesticFilterOptionsData, DomesticReadMeta]:
    data = PmcDomesticBatchReadService(session).filter_options(accounts)
    return success_response(
        request, data=data, meta=_meta(*BATCH_OBJECTS, "dim_lingxing_stores", *OWNER_OBJECTS),
    )


@router.get(
    "/batches",
    response_model=SuccessEnvelope[BatchListData, DomesticReadMeta],
    responses=READ_ERRORS,
    operation_id="listPmcDomesticBatches",
    summary="国内仓批次看板列表（一行一张收货单的一行）",
)
def list_batches(
    request: Request,
    query: Annotated[BatchListQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BatchListData, DomesticReadMeta]:
    data, total, freshness = PmcDomesticBatchReadService(session).list_batches(query, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(
            *BATCH_OBJECTS, *(OWNER_OBJECTS if query.owner_uid else ()),
            freshness_at=freshness,
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/batches/summary",
    response_model=SuccessEnvelope[BatchSummaryData, DomesticReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcDomesticBatchSummary",
    summary="国内仓批次看板统计",
)
def batch_summary(
    request: Request,
    query: Annotated[BatchFilterQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BatchSummaryData, DomesticReadMeta]:
    data, freshness = PmcDomesticBatchReadService(session).summary(query, accounts)
    return success_response(request, data=data, meta=_meta(
        *BATCH_OBJECTS, *(OWNER_OBJECTS if query.owner_uid else ()), freshness_at=freshness,
    ))


@router.get(
    "/batches/{batch_id}",
    response_model=SuccessEnvelope[BatchRowRead, DomesticReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcDomesticBatchDetail",
    summary="国内仓收货批次详情",
)
def batch_detail(
    request: Request,
    batch_id: UUID,
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BatchRowRead, DomesticReadMeta]:
    data, freshness = PmcDomesticBatchReadService(session).detail(batch_id, accounts)
    return success_response(request, data=data, meta=_meta(*BATCH_OBJECTS, freshness_at=freshness))


@router.get(
    "/batches/{batch_id}/trace",
    response_model=SuccessEnvelope[BatchTraceData, DomesticReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcDomesticBatchTrace",
    summary="国内仓收货批次追溯。出库来源未发布时为未知",
)
def batch_trace(
    request: Request,
    batch_id: UUID,
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BatchTraceData, DomesticReadMeta]:
    data, freshness = PmcDomesticBatchReadService(session).trace(batch_id, accounts)
    return success_response(request, data=data, meta=_meta(*BATCH_OBJECTS, freshness_at=freshness))
