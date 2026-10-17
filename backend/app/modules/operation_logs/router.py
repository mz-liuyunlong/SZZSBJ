"""Scoped operation log and batch editing API."""
from __future__ import annotations
from datetime import date
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.operation_logs.service import read_detail, save_batch, save_link

router = APIRouter(prefix="/api/operations/logs", tags=["Operation Logs"])
db_dep = Annotated[Session, Depends(get_db_session)]
scope_dep = Annotated[frozenset[str], Depends(require_source_account_scope)]
read_dep = Annotated[Principal, Depends(require_any_permission(
    "page:operations:log:view", "page:sales:daily-sales:view"
))]
write_dep = Annotated[Principal, Depends(require_permission("action:operations:log:edit"))]
errors: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}

class Identity(BaseModel):
    account: str = Field(min_length=1, max_length=128)
    day: date
    store: str = Field(min_length=1, max_length=128)
    item: str = Field(min_length=1, max_length=128)
    msku: str = Field(default="", max_length=128)

class WriteRow(Identity):
    content: str = Field(max_length=10000)
    work_type: str = Field(default="其他", max_length=32)
    status: str = Field(default="draft", pattern="^(draft|submitted)$")
    revision: int = Field(ge=0)

class BatchWrite(BaseModel):
    rows: list[WriteRow] = Field(min_length=1, max_length=200)

class LinkWrite(BaseModel):
    identity: Identity
    entry_type: str = Field(pattern="^(keyword|ad)$")
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2000)
    note: str = Field(default="", max_length=5000)

@router.get("", response_model=SuccessEnvelope[dict[str, Any], Any], responses=errors)
def get_logs(request: Request, account: str, day: date, store: str,
             item: str, session: db_dep, _: read_dep, accounts: scope_dep,
             msku: str = "") -> SuccessEnvelope[dict[str, Any], Any]:
    data = read_detail(session, accounts=accounts, account=account,
                       day=day, store=store, item=item, msku=msku)
    return success_response(request, data=data, meta=None)

@router.put("/manual/batch", response_model=SuccessEnvelope[dict[str, Any], Any],
            responses=errors)
def write_logs(request: Request, payload: BatchWrite, session: db_dep,
               principal: write_dep, accounts: scope_dep
               ) -> SuccessEnvelope[dict[str, Any], Any]:
    values = save_batch(session, accounts=accounts,
                        rows=[r.model_dump() for r in payload.rows],
                        actor=principal.user_id)
    return success_response(request, data={"revisions": values}, meta=None)

@router.put("/links", response_model=SuccessEnvelope[dict[str, bool], Any],
            responses=errors)
def write_links(request: Request, payload: LinkWrite, session: db_dep,
                principal: write_dep, accounts: scope_dep
                ) -> SuccessEnvelope[dict[str, bool], Any]:
    save_link(session, accounts=accounts, **payload.identity.model_dump(),
              entry_type=payload.entry_type, name=payload.name, url=payload.url,
              note=payload.note, actor=principal.user_id)
    return success_response(request, data={"saved": True}, meta=None)
