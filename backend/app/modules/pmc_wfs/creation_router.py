"""V2 endpoints remain fail-closed without a reviewed external write adapter."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.api import SuccessEnvelope
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.modules.pmc_wfs.creation_schemas import (
    AllocationCommand,
    AllocationPreview,
    Capabilities,
    CreationCommand,
    OperationList,
    OperationRead,
)
from app.modules.pmc_wfs.creation_service import CreationService
from app.modules.pmc_wfs.gateway import get_creation_gateway
from app.modules.pmc_wfs.router import ERRORS, Service
from app.modules.pmc_wfs.router import response as preparation_response
from app.modules.pmc_wfs.tasks import get_creation_dispatcher

router = APIRouter(tags=["PMC WFS Pending Packing V2"])
Create = Annotated[Principal, Depends(require_permission("action:pmc:wfs-pending-packing:create"))]
Preview = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:preview"))
]
Reconcile = Annotated[
    Principal, Depends(require_permission("action:pmc:wfs-pending-packing:reconcile"))
]
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
            preview_enabled=svc.gateway.enabled,
            reason=None if svc.gateway.enabled else "Walmart 创建与探测尚未启用，可先核对分箱方案",
        ),
    )


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
