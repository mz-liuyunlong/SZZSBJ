"""Inbound endpoints never run collection or publication from a GET."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.inbound_schemas import (
    InboundFilter,
    InboundList,
    InboundMeta,
    InboundOptions,
    InboundOptionsQuery,
    InboundQuery,
    InboundRow,
    InboundSummary,
    InboundTrace,
)
from app.modules.pmc_domestic.inbound_service import InboundReadService
from app.modules.pmc_domestic.registry import PERMISSION_READ

router = APIRouter(prefix="/api/pmc/domestic/inbound-batches", tags=["PMC Domestic Inbound Board"])
DB = Annotated[Session, Depends(get_db_session)]
Scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission(PERMISSION_READ))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 500)}


@router.get(
    "",
    response_model=SuccessEnvelope[InboundList, InboundMeta],
    responses=ERRORS,
    operation_id="listDomesticInboundBatches",
    summary="采购入库单×SKU×店铺批次列表",
)
def list_inbound(
    request: Request, query: Annotated[InboundQuery, Query()], session: DB, _: Read, accounts: Scope
):
    data, meta = InboundReadService(session).list(query, accounts)
    return success_response(request, data=data, meta=meta)


@router.get(
    "/summary",
    response_model=SuccessEnvelope[InboundSummary, InboundMeta],
    responses=ERRORS,
    operation_id="summarizeDomesticInboundBatches",
    summary="入库及批次余额去重统计",
)
def summary(
    request: Request,
    query: Annotated[InboundFilter, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    data, meta = InboundReadService(session).summary(query, accounts)
    return success_response(request, data=data, meta=meta)


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[InboundOptions, InboundMeta],
    responses=ERRORS,
    operation_id="getDomesticInboundFilterOptions",
    summary="当前入库批次店铺、当前产品负责人和业务状态能力",
)
def filter_options(
    request: Request,
    query: Annotated[InboundOptionsQuery, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    data, meta = InboundReadService(session).filter_options(query, accounts)
    return success_response(request, data=data, meta=meta)


@router.get(
    "/{inbound_id}",
    response_model=SuccessEnvelope[InboundRow, InboundMeta],
    responses=ERRORS,
    operation_id="getDomesticInboundBatch",
    summary="入库批次详情",
)
def detail(request: Request, inbound_id: UUID, session: DB, _: Read, accounts: Scope):
    data, meta = InboundReadService(session).detail(inbound_id, accounts)
    return success_response(request, data=data, meta=meta)


@router.get(
    "/{inbound_id}/trace",
    response_model=SuccessEnvelope[InboundTrace, InboundMeta],
    responses=ERRORS,
    operation_id="traceDomesticInboundBatch",
    summary="入库事件与批次库存来源追溯",
)
def trace(request: Request, inbound_id: UUID, session: DB, _: Read, accounts: Scope):
    data, meta = InboundReadService(session).trace(inbound_id, accounts)
    return success_response(request, data=data, meta=meta)
