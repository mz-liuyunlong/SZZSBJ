"""Warehouse endpoints stay thin; each write has an independent action permission."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.warehouse_overpack import current_board_publication
from app.modules.pmc_domestic.warehouse_schemas import (
    BoxesCommand,
    CustomsCommand,
    DoneCommand,
    NoteCommand,
    ReboxCommand,
    SupplementalInboundCommand,
    SupplementalSyncCommand,
    UnpackedDispositionCommand,
    WarehouseEvents,
    WarehouseFilter,
    WarehouseList,
    WarehouseOptions,
    WarehouseOrderRead,
    WarehouseQuery,
    WarehouseSummary,
)
from app.modules.pmc_domestic.warehouse_service import WarehouseService

router = APIRouter(prefix="/api/pmc/domestic/packing-warehouse", tags=["PMC Packing Warehouse"])
DB = Annotated[Session, Depends(get_db_session)]
Scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:domestic-warehouse-board:view"))]
Boxes = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-boxes-save")),
]
Done = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-done")),
]
Customs = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-customs")),
]
Notes = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-note")),
]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500)}
META = {
    "source": "new_system_postgresql",
    "local_verification_only": True,
    "arrival_date_rule": "inbound_date",
    "shipment_status": "not_connected",
}


@router.get("/orders", response_model=SuccessEnvelope[WarehouseList, dict], responses=ERRORS)
def orders(
    request: Request,
    q: Annotated[WarehouseQuery, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    return success_response(request, data=WarehouseService(session).list(q, accounts), meta=META)


@router.get(
    "/orders/summary",
    response_model=SuccessEnvelope[WarehouseSummary, dict],
    responses=ERRORS,
)
def summary(
    request: Request,
    q: Annotated[WarehouseFilter, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    return success_response(request, data=WarehouseService(session).summary(q, accounts), meta=META)


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[WarehouseOptions, dict],
    responses=ERRORS,
)
def options(request: Request, session: DB, _: Read, accounts: Scope):
    return success_response(request, data=WarehouseService(session).options(accounts), meta=META)


@router.get(
    "/orders/{ident}",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def detail(request: Request, ident: UUID, session: DB, _: Read, accounts: Scope):
    return success_response(
        request, data=WarehouseService(session).detail(ident, accounts), meta=META
    )


@router.get(
    "/orders/{ident}/events",
    response_model=SuccessEnvelope[WarehouseEvents, dict],
    responses=ERRORS,
)
def events(
    request: Request,
    ident: UUID,
    session: DB,
    _: Read,
    accounts: Scope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return success_response(
        request,
        data=WarehouseService(session).events(ident, accounts, page, page_size),
        meta=META,
    )


@router.post(
    "/orders/{ident}/boxes",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def boxes(
    request: Request,
    ident: UUID,
    body: BoxesCommand,
    session: DB,
    actor: Boxes,
    accounts: Scope,
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "boxes", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/done",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def done(
    request: Request,
    ident: UUID,
    body: DoneCommand,
    session: DB,
    actor: Done,
    accounts: Scope,
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "done", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/customs",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def customs(
    request: Request,
    ident: UUID,
    body: CustomsCommand,
    session: DB,
    actor: Customs,
    accounts: Scope,
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "customs", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/notes",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def notes(
    request: Request,
    ident: UUID,
    body: NoteCommand,
    session: DB,
    actor: Notes,
    accounts: Scope,
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "note", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/unpacked",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def unpacked(
    request: Request,
    ident: UUID,
    body: UnpackedDispositionCommand,
    session: DB,
    accounts: Scope,
    actor: Annotated[
        Principal,
        Depends(require_permission("action:pmc:domestic-warehouse-board:packing-unpacked-dispose")),
    ],
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "unpacked", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/rebox",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def rebox(
    request: Request,
    ident: UUID,
    body: ReboxCommand,
    session: DB,
    accounts: Scope,
    actor: Annotated[
        Principal, Depends(require_permission("action:pmc:domestic-warehouse-board:packing-rebox"))
    ],
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "rebox", body, actor.user_id, accounts),
        meta=META,
    )


def warehouse_publication_provider(session: DB):
    """Name the current governed publication in this process database."""

    def provide(account, warehouse_id, sku, inbound_sn):
        return current_board_publication(session, account, warehouse_id, sku, inbound_sn)

    return provide


@router.post(
    "/orders/{ident}/supplemental-inbound",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def supplemental_inbound(
    request: Request,
    ident: UUID,
    body: SupplementalInboundCommand,
    session: DB,
    accounts: Scope,
    actor: Annotated[
        Principal,
        Depends(require_permission("action:pmc:domestic-warehouse-board:packing-supplement-ib")),
    ],
):
    return success_response(
        request,
        data=WarehouseService(session).command(ident, "ib", body, actor.user_id, accounts),
        meta=META,
    )


@router.post(
    "/orders/{ident}/supplemental-sync",
    response_model=SuccessEnvelope[WarehouseOrderRead, dict],
    responses=ERRORS,
)
def supplemental_sync(
    request: Request,
    ident: UUID,
    body: SupplementalSyncCommand,
    session: DB,
    accounts: Scope,
    actor: Annotated[
        Principal,
        Depends(require_permission("action:pmc:domestic-warehouse-board:packing-supplement-sync")),
    ],
    provider: Annotated[object | None, Depends(warehouse_publication_provider)],
):
    return success_response(
        request,
        data=WarehouseService(session, provider).command(
            ident, "sync", body, actor.user_id, accounts
        ),
        meta=META,
    )
