"""物流看板 API (read-only): 8088 ``pmc-logistics`` over stored Lingxing / 众壹 / Walmart
records. No provider calls, no writes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_logistics.schemas import (
    AlertQuery,
    CarrierOrderDetail,
    CarrierQuery,
    ForecastQuery,
    LogisticsDetail,
    LogisticsList,
    LogisticsOptions,
    LogisticsRulesView,
    OverviewQuery,
    RuleListQuery,
)
from app.modules.pmc_logistics.service import LogisticsService

router = APIRouter(prefix="/api/pmc/logistics", tags=["PMC Logistics"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
# Same page permission as the WFS board until a logistics key is approved (PRP #298).
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 500, 503)}


def service(session: DB, accounts: Accounts, actor: Read) -> LogisticsService:
    if "*" in actor.permissions:
        stores = None
    else:
        try:
            uid = int(actor.user_id)
        except ValueError:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
        values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
        stores = None if "*" in values else set(values)
        if stores == set():
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return LogisticsService(session, sorted(accounts), stores)


Service = Annotated[LogisticsService, Depends(service)]


def meta(svc: LogisticsService) -> dict:
    snap = svc.snapshot()
    return {
        "source": "new_system_postgresql",
        "rule_date": snap.today.isoformat(),
        "provider_calls": False,
        "source_tables": [
            "gov_wfs_board_publications",
            "ods_lingxing_wfs_shipping_lists",
            "ods_lingxing_wfs_cargos",
            "ods_lingxing_logistics_channels",
            "ods_carrier_zhongyi_orders",
            "ods_carrier_zhongyi_tracks",
            "ods_walmart_wfs_inbound_shipments",
            "ods_walmart_wfs_inbound_items",
            "ods_walmart_wfs_receipts",
            "dim_walmart_listings",
            "dwd_lingxing_sku_product_info_current",
        ],
    }


def page_meta(svc: LogisticsService, data: LogisticsList) -> dict:
    return {**meta(svc), "page": data.page, "page_size": data.page_size, "total": data.total}


@router.get(
    "/options",
    response_model=SuccessEnvelope[LogisticsOptions, dict],
    responses=ERRORS,
    summary="物流筛选项、规则摘要、数据来源",
)
def options(request: Request, svc: Service):
    return success_response(request, data=svc.options(), meta=meta(svc))


@router.get(
    "/overview",
    response_model=SuccessEnvelope[LogisticsList, dict],
    responses=ERRORS,
    summary="物流总览（发货单，服务端分页）",
)
def overview(request: Request, svc: Service, q: Annotated[OverviewQuery, Query()]):
    data = svc.overview(q)
    return success_response(request, data=data, meta=page_meta(svc, data))


@router.get(
    "/alerts",
    response_model=SuccessEnvelope[LogisticsList, dict],
    responses=ERRORS,
    summary="异常与提醒（服务端分页）",
)
def alerts(request: Request, svc: Service, q: Annotated[AlertQuery, Query()]):
    data = svc.alerts(q)
    return success_response(request, data=data, meta=page_meta(svc, data))


@router.get(
    "/forecast",
    response_model=SuccessEnvelope[LogisticsList, dict],
    responses=ERRORS,
    summary="到货预测（店铺 × MSKU，服务端分页）",
)
def forecast(request: Request, svc: Service, q: Annotated[ForecastQuery, Query()]):
    data = svc.forecast(q)
    return success_response(request, data=data, meta=page_meta(svc, data))


@router.get(
    "/carriers",
    response_model=SuccessEnvelope[LogisticsList, dict],
    responses=ERRORS,
    summary="货代看板（众壹运单，服务端分页）",
)
def carriers(request: Request, svc: Service, q: Annotated[CarrierQuery, Query()]):
    data = svc.carriers(q)
    return success_response(request, data=data, meta=page_meta(svc, data))


@router.get(
    "/carriers/{number}",
    response_model=SuccessEnvelope[CarrierOrderDetail, dict],
    responses=ERRORS,
    summary="货代运单详情（全部轨迹）",
)
def carrier_order(
    request: Request, svc: Service, number: Annotated[str, Path(min_length=1, max_length=64)]
):
    data = svc.carrier_order(number)
    if data is None:
        raise ApiError(
            code=ErrorCode.NOT_FOUND, status_code=404, message="运单不存在或不在数据范围内"
        )
    return success_response(request, data=data, meta=meta(svc))


@router.get(
    "/rules",
    response_model=SuccessEnvelope[LogisticsRulesView, dict],
    responses=ERRORS,
    summary="时效与阈值设置（只读）",
)
def rules(request: Request, svc: Service):
    return success_response(request, data=svc.rules_view(), meta=meta(svc))


@router.get(
    "/rules/{section}",
    response_model=SuccessEnvelope[LogisticsList, dict],
    responses=ERRORS,
    summary="时效与阈值设置表格（渠道分段 / 合同时效 / 目的仓，服务端分页，排序白名单）",
)
def rule_list(
    request: Request,
    svc: Service,
    section: Annotated[Literal["cycles", "contracts", "fcs"], Path()],
    q: Annotated[RuleListQuery, Query()],
):
    try:
        data = svc.rule_list(section, q)
    except ValueError:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR, status_code=422, message="不支持按该列排序"
        ) from None
    assert data is not None  # section is validated by the path type
    return success_response(request, data=data, meta=page_meta(svc, data))


@router.get(
    "/shipping-lists/{code}",
    response_model=SuccessEnvelope[LogisticsDetail, dict],
    responses=ERRORS,
)
def shipping_list(
    request: Request, svc: Service, code: Annotated[str, Path(min_length=1, max_length=64)]
):
    data = svc.detail(code)
    if data is None:
        raise ApiError(
            code=ErrorCode.NOT_FOUND, status_code=404, message="发货单不存在或不在数据范围内"
        )
    return success_response(request, data=data, meta=meta(svc))
