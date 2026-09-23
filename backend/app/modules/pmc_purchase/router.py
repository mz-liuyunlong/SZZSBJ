"""Read-only HTTP routes for the PMC purchase board (Gate 3, G3-E; PRP §7.1–7.4).

Path prefix ``/api/pmc/purchase`` (repository convention, no ``v1``; Owner 2026-09-21).
All routes: ``pmc:purchase:read`` + trusted source-account scope (fail closed), unified
envelope, ``response_model`` and ``operation_id``. No write route lives here (G3-F).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_purchase.schemas import (
    BoardFilterQuery,
    BoardListData,
    BoardListQuery,
    BoardSummaryData,
    OrderDetailData,
    PendingPlanListData,
    PendingPlanQuery,
    PurchaseReadMeta,
    SkuCycleListData,
    SkuCycleQuery,
)
from app.modules.pmc_purchase.service import PmcPurchaseReadService

PERMISSION_READ = "pmc:purchase:read"

router = APIRouter(prefix="/api/pmc/purchase", tags=["PMC Purchase Board"])

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

BOARD_OBJECTS = ("dws_purchase_board",)
SUMMARY_OBJECTS = ("dws_purchase_board", "dws_purchase_sku_cycle", "dwd_purchase_plan")
DETAIL_OBJECTS = ("dws_purchase_board", "dws_purchase_sku_cycle", "dwd_purchase_plan")
CYCLE_OBJECTS = ("dws_purchase_sku_cycle",)
PLAN_OBJECTS = ("dwd_purchase_plan", "dws_purchase_board", "dim_lingxing_stores")


def _meta(
    *objects: str,
    freshness_at: datetime | None = None,
    rule_version: int | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> PurchaseReadMeta:
    return PurchaseReadMeta(
        source_objects=list(objects),
        freshness_at=freshness_at,
        rule_version=rule_version,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/board",
    response_model=SuccessEnvelope[BoardListData, PurchaseReadMeta],
    responses=READ_ERRORS,
    operation_id="listPmcPurchaseBoard",
    summary="采购看板列表（采购单明细行 × 计划）",
)
def list_board(
    request: Request,
    query: Annotated[BoardListQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BoardListData, PurchaseReadMeta]:
    data, total, freshness, rule = PmcPurchaseReadService(session).list_board(query, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(
            *BOARD_OBJECTS,
            freshness_at=freshness,
            rule_version=rule,
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )


@router.get(
    "/board/summary",
    response_model=SuccessEnvelope[BoardSummaryData, PurchaseReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcPurchaseBoardSummary",
    summary="采购看板汇总卡片",
)
def board_summary(
    request: Request,
    query: Annotated[BoardFilterQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[BoardSummaryData, PurchaseReadMeta]:
    data, freshness, rule = PmcPurchaseReadService(session).summary(query, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(*SUMMARY_OBJECTS, freshness_at=freshness, rule_version=rule),
    )


@router.get(
    "/orders/{order_sn}",
    response_model=SuccessEnvelope[OrderDetailData, PurchaseReadMeta],
    responses=READ_ERRORS,
    operation_id="getPmcPurchaseOrderDetail",
    summary="采购单详情（单头 + 明细×ItemID + 收货记录 + 计划链 + 交期样本）",
)
def order_detail(
    request: Request,
    order_sn: str,
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[OrderDetailData, PurchaseReadMeta]:
    data, freshness, rule = PmcPurchaseReadService(session).order_detail(order_sn, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(*DETAIL_OBJECTS, freshness_at=freshness, rule_version=rule),
    )


@router.get(
    "/sku-cycles",
    response_model=SuccessEnvelope[SkuCycleListData, PurchaseReadMeta],
    responses=READ_ERRORS,
    operation_id="listPmcPurchaseSkuCycles",
    summary="SKU 实际采购交期（近 5 样本、剔除、人工基准、不稳定）",
)
def sku_cycles(
    request: Request,
    query: Annotated[SkuCycleQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[SkuCycleListData, PurchaseReadMeta]:
    data, freshness, rule = PmcPurchaseReadService(session).sku_cycles(query, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(*CYCLE_OBJECTS, freshness_at=freshness, rule_version=rule),
    )


@router.get(
    "/plans/pending",
    response_model=SuccessEnvelope[PendingPlanListData, PurchaseReadMeta],
    responses=READ_ERRORS,
    operation_id="listPmcPurchasePendingPlans",
    summary="待采购计划（已审批未下单，S2 卡片下钻）",
)
def pending_plans(
    request: Request,
    query: Annotated[PendingPlanQuery, Query()],
    session: db_session,
    _: read_principal,
    accounts: source_scope,
) -> SuccessEnvelope[PendingPlanListData, PurchaseReadMeta]:
    data, total, rule = PmcPurchaseReadService(session).pending_plans(query, accounts)
    return success_response(
        request,
        data=data,
        meta=_meta(
            *PLAN_OBJECTS,
            rule_version=rule,
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )
