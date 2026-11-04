"""V2 endpoints; Walmart is reached only through the reviewed adapter and WFS_CREATION_MODE."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.api import SuccessEnvelope
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.pmc_wfs.creation_board import (
    CreationBoard,
    StoreDefaults,
    StoreDefaultsList,
    StoreDefaultsRow,
    StoreDefaultsUpdate,
    Tab,
    TicketCounts,
    TicketList,
)
from app.modules.pmc_wfs.creation_config import creation_mode
from app.modules.pmc_wfs.creation_schemas import (
    AllocationCommand,
    AllocationPreview,
    ApprovalCommand,
    Capabilities,
    CreationCommand,
    CreationDefaultsRead,
    OperationList,
    OperationRead,
    ProbeResult,
)
from app.modules.pmc_wfs.creation_service import CreationService
from app.modules.pmc_wfs.creation_task import get_creation_dispatcher
from app.modules.pmc_wfs.gateway import get_creation_gateway
from app.modules.pmc_wfs.router import ERRORS, Service
from app.modules.pmc_wfs.router import response as preparation_response

router = APIRouter(tags=["PMC WFS Pending Packing V2"])
Create = Annotated[Principal, Depends(require_permission("action:pmc:wfs-pending-packing:create"))]
Preview = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:preview"))
]
Reconcile = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:reconcile"))
]
Approve = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:approve"))
]
Manage = Annotated[Principal, Depends(require_permission("action:pmc:wfs-settings:manage"))]
Label = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:label-retry"))
]


def creation_service(
    base: Service,
    gateway: Annotated[Any, Depends(get_creation_gateway)],
    dispatcher: Annotated[Any, Depends(get_creation_dispatcher)],
):
    return CreationService(base, gateway, dispatcher)


Creation = Annotated[CreationService, Depends(creation_service)]
V2_ERRORS = {**ERRORS, 503: ERRORS[500]}


def response(request, data):
    result = preparation_response(request, data)
    result.meta.pop("execution_enabled", None)
    return result


@router.get("/capabilities", response_model=SuccessEnvelope[Capabilities, dict])
def capabilities(request: Request, svc: Creation):
    return response(
        request,
        Capabilities(
            creation_enabled=svc.gateway.enabled,
            preview_enabled=getattr(svc.gateway, "preview_enabled", svc.gateway.enabled),
            reason=getattr(svc.gateway, "reason", None) or None,
            mode=creation_mode()
            if svc.gateway.enabled or getattr(svc.gateway, "preview_enabled", False)
            else "off",
        ),
    )


@router.get("/creation-defaults", response_model=SuccessEnvelope[CreationDefaultsRead, dict])
def defaults(
    request: Request,
    svc: Creation,
    actor: Create,
    source_account_ref: str,
    store_id: Annotated[str | None, Query(max_length=64)] = None,
):
    return response(request, svc.defaults(source_account_ref, store_id))


@router.get("/creation-tickets", response_model=SuccessEnvelope[TicketList, dict])
def tickets(
    request: Request,
    base: Service,
    tab: Tab,
    store_id: Annotated[str | None, Query(max_length=64)] = None,
    keyword: Annotated[str, Query(max_length=200)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
):
    """待创建货件的 提交中 / 创建失败 / 已创建未发货 页签（一行一票）。"""
    board = CreationBoard(base.session, base.accounts, base.stores)
    return response(request, board.list(tab, store_id, keyword, page, page_size))


@router.get("/creation-ticket-counts", response_model=SuccessEnvelope[TicketCounts, dict])
def ticket_counts(
    request: Request,
    base: Service,
    store_id: Annotated[str | None, Query(max_length=64)] = None,
    keyword: Annotated[str, Query(max_length=200)] = "",
):
    board = CreationBoard(base.session, base.accounts, base.stores)
    return response(request, board.counts(store_id, keyword))


@router.get("/store-creation-defaults", response_model=SuccessEnvelope[StoreDefaultsList, dict])
def store_defaults(request: Request, base: Service):
    return response(request, StoreDefaults(base.session, base.accounts, base.stores).list())


@router.put(
    "/store-creation-defaults/{store_id}",
    response_model=SuccessEnvelope[StoreDefaultsRow, dict],
    responses=V2_ERRORS,
)
def save_store_defaults(
    request: Request, store_id: str, body: StoreDefaultsUpdate, base: Service, actor: Manage
):
    """创建默认值按店铺保存；创建弹窗里改的值只用于那一次，不回写这里。"""
    service = StoreDefaults(base.session, base.accounts, base.stores)
    return response(request, service.update(store_id, body, actor.user_id))


@router.post("/creation-probe", response_model=SuccessEnvelope[ProbeResult, dict])
def probe(request: Request, svc: Creation, actor: Preview, store_id: str):
    return response(request, svc.probe(store_id))


@router.post(
    "/allocation-preview",
    response_model=SuccessEnvelope[AllocationPreview, dict],
    responses=V2_ERRORS,
)
def allocation(request: Request, body: AllocationCommand, svc: Creation, actor: Create):
    return response(request, svc.preview(body))


@router.post(
    "/creation-operations", response_model=SuccessEnvelope[OperationRead, dict], responses=V2_ERRORS
)
def create(request: Request, body: CreationCommand, svc: Creation, actor: Create):
    return response(request, svc.submit(body, actor.user_id))


@router.post(
    "/creation-operations/{ident}/approve",
    response_model=SuccessEnvelope[OperationRead, dict],
    responses=V2_ERRORS,
)
def approve(request: Request, ident: UUID, body: ApprovalCommand, svc: Creation, actor: Approve):
    return response(request, svc.approve(ident, body, actor.user_id))


@router.get(
    "/creation-operations", response_model=SuccessEnvelope[OperationList, dict], responses=V2_ERRORS
)
def operations(
    request: Request,
    svc: Creation,
    order_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return response(request, svc.list(order_id, page, page_size))


@router.get(
    "/creation-operations/{ident}",
    response_model=SuccessEnvelope[OperationRead, dict],
    responses=V2_ERRORS,
)
def operation(request: Request, ident: UUID, svc: Creation):
    return response(request, svc.read(ident))


@router.post(
    "/creation-operations/{ident}/reconcile",
    response_model=SuccessEnvelope[OperationRead, dict],
    responses=V2_ERRORS,
)
def reconcile(request: Request, ident: UUID, svc: Creation, actor: Reconcile):
    return response(request, svc.recover(ident, actor.user_id, "reconcile"))


@router.post(
    "/creation-operations/{ident}/retry",
    response_model=SuccessEnvelope[OperationRead, dict],
    responses=V2_ERRORS,
)
def retry(request: Request, ident: UUID, svc: Creation, actor: Approve):
    """Resend FAILED tickets (read back by the same order id first, in the worker)."""
    return response(request, svc.recover(ident, actor.user_id, "retry"))


@router.post(
    "/creation-operations/{ident}/labels/retry",
    response_model=SuccessEnvelope[OperationRead, dict],
    responses=V2_ERRORS,
)
def labels(request: Request, ident: UUID, svc: Creation, actor: Label):
    return response(request, svc.recover(ident, actor.user_id, "labels"))


@router.get(
    "/creation-operations/{ident}/labels/{shipment_id}",
    responses=V2_ERRORS,
    response_class=Response,
)
def label(ident: UUID, shipment_id: str, svc: Creation):
    return Response(
        content=svc.label(ident, shipment_id),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="wfs-label.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/optional-previews", response_model=SuccessEnvelope[dict, dict], responses=V2_ERRORS)
def preview(request: Request, body: CreationCommand, svc: Creation, actor: Preview):
    return response(request, svc.optional_preview(body))
