"""Scoped packing endpoints; action permissions are mapped before generic page rules."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.packing_models import PackingEvent
from app.modules.pmc_domestic.packing_repository import order_read
from app.modules.pmc_domestic.packing_schemas import (
    ApproveCommand,
    CandidateList,
    EditOptions,
    EventList,
    EventRead,
    ManualCommand,
    ManualSubmitted,
    OrderList,
    OrderRead,
    PackingFilter,
    PackingOption,
    PackingOptions,
    PackingQuery,
    PackingSummary,
    RejectCommand,
)
from app.modules.pmc_domestic.packing_service import PackingService

router = APIRouter(
    prefix="/api/pmc/domestic/packing-approval", tags=["PMC Domestic Packing Approval"]
)
DB = Annotated[Session, Depends(get_db_session)]
Scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:domestic-warehouse-board:view"))]
Approve = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-approve")),
]
Reject = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-reject")),
]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500)}


@router.get("/pending", response_model=SuccessEnvelope[CandidateList, dict], responses=ERRORS)
def pending(
    request: Request,
    query: Annotated[PackingQuery, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    data = PackingService(session).pending(query, accounts)
    return success_response(
        request,
        data=data,
        meta={
            "source": "new_system_postgresql",
            "page": query.page,
            "page_size": query.page_size,
            "total": data.total,
            "local_verification_only": True,
        },
    )


@router.get(
    "/pending/summary",
    response_model=SuccessEnvelope[PackingSummary, dict],
    responses=ERRORS,
)
def summary(
    request: Request,
    query: Annotated[PackingFilter, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    return success_response(
        request,
        data=PackingService(session).summary(query, accounts),
        meta={"source": "new_system_postgresql"},
    )


@router.get(
    "/filter-options",
    response_model=SuccessEnvelope[PackingOptions, dict],
    responses=ERRORS,
)
def options(request: Request, session: DB, _: Read, accounts: Scope):
    rows = PackingService(session).repo.candidates(accounts, include_decided=True)
    stores = {r.store_id: r.store_name or r.store_id for r in rows if r.store_id}
    return success_response(
        request,
        data=PackingOptions(
            stores=[PackingOption(value=k, label=v) for k, v in sorted(stores.items())]
        ),
        meta={"source": "new_system_postgresql"},
    )


@router.get("/orders", response_model=SuccessEnvelope[OrderList, dict], responses=ERRORS)
def orders(
    request: Request,
    query: Annotated[PackingQuery, Query()],
    session: DB,
    _: Read,
    accounts: Scope,
):
    return success_response(
        request,
        data=PackingService(session).orders(query, accounts),
        meta={"source": "new_system_postgresql"},
    )


@router.get(
    "/orders/{order_id}",
    response_model=SuccessEnvelope[OrderRead, dict],
    responses=ERRORS,
)
def detail(request: Request, order_id: UUID, session: DB, _: Read, accounts: Scope):
    return success_response(
        request,
        data=order_read(PackingService(session).order(order_id, accounts)),
        meta={"source": "new_system_postgresql"},
    )


@router.get(
    "/orders/{order_id}/events",
    response_model=SuccessEnvelope[EventList, dict],
    responses=ERRORS,
)
def events(request: Request, order_id: UUID, session: DB, _: Read, accounts: Scope):
    PackingService(session).order(order_id, accounts)
    rows = session.scalars(
        select(PackingEvent)
        .where(PackingEvent.order_id == order_id)
        .order_by(PackingEvent.occurred_at, PackingEvent.id)
    )
    data = EventList(
        items=[
            EventRead(
                id=r.id,
                event_kind=r.event_kind,
                actor_uid=r.actor_uid,
                order_version=r.order_version,
                occurred_at=r.occurred_at,
                note=r.request_json.get("note"),
            )
            for r in rows
        ]
    )
    return success_response(request, data=data, meta={"source": "new_system_postgresql"})


@router.post(
    "/pending/{candidate_id}/approve",
    response_model=SuccessEnvelope[OrderRead, dict],
    responses=ERRORS,
)
def approve(
    request: Request,
    candidate_id: UUID,
    body: ApproveCommand,
    session: DB,
    actor: Approve,
    accounts: Scope,
):
    return success_response(
        request,
        data=PackingService(session).decide(candidate_id, body, "approve", actor.user_id, accounts),
        meta={"local_verification_only": True},
    )


@router.post(
    "/pending/{candidate_id}/reject",
    response_model=SuccessEnvelope[OrderRead, dict],
    responses=ERRORS,
)
def reject(
    request: Request,
    candidate_id: UUID,
    body: RejectCommand,
    session: DB,
    actor: Reject,
    accounts: Scope,
):
    return success_response(
        request,
        data=PackingService(session).decide(candidate_id, body, "reject", actor.user_id, accounts),
        meta={"local_verification_only": True},
    )


@router.get(
    "/pending/{candidate_id}/edit-options",
    response_model=SuccessEnvelope[EditOptions, dict],
    responses=ERRORS,
)
def edit_options(
    request: Request,
    candidate_id: UUID,
    source_account_ref: str,
    session: DB,
    _: Read,
    accounts: Scope,
):
    return success_response(
        request,
        data=PackingService(session).edit_options(candidate_id, source_account_ref, accounts),
        meta={"local_verification_only": True},
    )


@router.get(
    "/manual/sources", response_model=SuccessEnvelope[CandidateList, dict], responses=ERRORS
)
def manual_sources(
    request: Request, query: Annotated[PackingQuery, Query()], session: DB, _: Read, accounts: Scope
):
    from app.modules.pmc_domestic.packing_manual_service import ManualPackingService

    return success_response(
        request,
        data=ManualPackingService(PackingService(session)).source_list(query, accounts),
        meta={"source": "new_system_postgresql"},
    )


@router.get(
    "/manual/{board_id}/options",
    response_model=SuccessEnvelope[EditOptions, dict],
    responses=ERRORS,
)
def manual_options(
    request: Request, board_id: UUID, source_account_ref: str, session: DB, _: Read, accounts: Scope
):
    from app.modules.pmc_domestic.packing_manual_service import ManualPackingService

    return success_response(
        request,
        data=ManualPackingService(PackingService(session)).options(
            board_id, source_account_ref, accounts
        ),
        meta={"source": "new_system_postgresql"},
    )


ManualCreate = Annotated[
    Principal,
    Depends(require_permission("action:pmc:domestic-warehouse-board:packing-manual-create")),
]


@router.post("/manual", response_model=SuccessEnvelope[ManualSubmitted, dict], responses=ERRORS)
def manual_submit(
    request: Request, body: ManualCommand, session: DB, actor: ManualCreate, accounts: Scope
):
    from app.modules.pmc_domestic.packing_manual_service import ManualPackingService

    return success_response(
        request,
        data=ManualPackingService(PackingService(session)).submit(body, actor.user_id, accounts),
        meta={"local_verification_only": True},
    )
