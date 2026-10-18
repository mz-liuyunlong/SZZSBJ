"""Scoped operation log and batch editing API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.operation_logs.access import LogAccess, require_log_access, require_owned_identity
from app.modules.operation_logs.service import read_detail, save_batch, save_link

router = APIRouter(prefix="/api/operations/logs", tags=["Operation Logs"])
db_dep = Annotated[Session, Depends(get_db_session)]
scope_dep = Annotated[frozenset[str], Depends(require_source_account_scope)]
access_dep = Annotated[LogAccess, Depends(require_log_access)]
read_dep = Annotated[
    Principal,
    Depends(require_any_permission("page:operations:log:view", "page:sales:daily-sales:view")),
]
write_dep = Annotated[Principal, Depends(require_permission("action:operations:log:edit"))]
errors: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
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
    work_types: list[str] = Field(default_factory=list, max_length=6)
    observe_days: int | None = Field(default=None, ge=1, le=365)
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
def get_logs(
    request: Request,
    account: str,
    day: date,
    store: str,
    item: str,
    session: db_dep,
    _: read_dep,
    accounts: scope_dep,
    access: access_dep,
    msku: str = "",
) -> SuccessEnvelope[dict[str, Any], Any]:
    require_owned_identity(
        session, access, account=account, store=store, item=item, msku=msku, day=day
    )
    data = read_detail(
        session,
        accounts=accounts,
        account=account,
        day=day,
        store=store,
        item=item,
        msku=msku,
        access=access,
    )
    return success_response(request, data=data, meta=None)


@router.put("/manual/batch", response_model=SuccessEnvelope[dict[str, Any], Any], responses=errors)
def write_logs(
    request: Request,
    payload: BatchWrite,
    session: db_dep,
    principal: write_dep,
    accounts: scope_dep,
    access: access_dep,
) -> SuccessEnvelope[dict[str, Any], Any]:
    values = save_batch(
        session,
        accounts=accounts,
        rows=[r.model_dump() for r in payload.rows],
        actor=principal.user_id,
        access=access,
    )
    return success_response(request, data={"revisions": values}, meta=None)


@router.put("/links", response_model=SuccessEnvelope[dict[str, bool], Any], responses=errors)
def write_links(
    request: Request,
    payload: LinkWrite,
    session: db_dep,
    principal: write_dep,
    accounts: scope_dep,
    access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    save_link(
        session,
        accounts=accounts,
        **payload.identity.model_dump(),
        entry_type=payload.entry_type,
        name=payload.name,
        url=payload.url,
        note=payload.note,
        actor=principal.user_id,
        access=access,
    )
    return success_response(request, data={"saved": True}, meta=None)

class OwnerMappingWrite(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    owner_uid: str = Field(min_length=1, max_length=128)
    app_user_id: int = Field(ge=1)


def _admin_only(access: LogAccess) -> None:
    if not access.is_admin:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)


@router.get("/owner-mappings", response_model=SuccessEnvelope[list[dict[str, Any]], Any], responses=errors)
def list_owner_mappings(
    request: Request, session: db_dep, _: read_dep, access: access_dep,
) -> SuccessEnvelope[list[dict[str, Any]], Any]:
    _admin_only(access)
    records = session.execute(
        text("""
            select m.source_account_ref, m.owner_uid, m.app_user_id,
                   u.username, u.display_name
            from ops_lingxing_owner_user_mappings m
            join app_users u on u.id = m.app_user_id
            where m.source_account_ref = any(:accounts)
            order by m.source_account_ref, m.owner_uid
        """),
        {"accounts": list(access.accounts)},
    ).mappings().all()
    return success_response(request, data=[dict(r) for r in records], meta=None)


@router.put("/owner-mappings", response_model=SuccessEnvelope[dict[str, bool], Any], responses=errors)
def put_owner_mapping(
    request: Request, payload: OwnerMappingWrite, session: db_dep,
    _: write_dep, access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    _admin_only(access)
    access.require_account(payload.source_account_ref)
    user_exists = session.scalar(
        text("select exists(select 1 from app_users where id = :uid and is_active = 1)"),
        {"uid": payload.app_user_id},
    )
    if not user_exists:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    params = {
        "account": payload.source_account_ref, "owner_uid": payload.owner_uid.strip(),
        "uid": payload.app_user_id, "actor": access.user_id,
    }
    if not params["owner_uid"]:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    try:
        old = session.scalar(
            text("""
                select app_user_id from ops_lingxing_owner_user_mappings
                where source_account_ref = :account and owner_uid = :owner_uid
                for update
            """), params
        )
        session.execute(
            text("""
                insert into ops_lingxing_owner_user_mappings
                    (source_account_ref, owner_uid, app_user_id, updated_by_user_id)
                values (:account, :owner_uid, :uid, :actor)
                on conflict (source_account_ref, owner_uid)
                do update set app_user_id = excluded.app_user_id,
                              updated_by_user_id = excluded.updated_by_user_id,
                              updated_at = now()
            """), params,
        )
        if old != payload.app_user_id:
            session.execute(
                text("""
                    insert into ops_lingxing_owner_mapping_audit
                      (source_account_ref, owner_uid, before_user_id,
                       after_user_id, actor_user_id, action)
                    values (:account, :owner_uid, :before, :uid, :actor, :action)
                """),
                {**params, "before": old,
                 "action": "reassign" if old is not None else "assign"},
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return success_response(request, data={"saved": True}, meta=None)


@router.delete("/owner-mappings/{owner_uid}", response_model=SuccessEnvelope[dict[str, bool], Any], responses=errors)
def delete_owner_mapping(
    request: Request, owner_uid: str, source_account_ref: str,
    session: db_dep, _: write_dep, access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    _admin_only(access)
    access.require_account(source_account_ref)
    params = {
        "account": source_account_ref, "owner_uid": owner_uid,
        "actor": access.user_id,
    }
    try:
        old = session.scalar(
            text("""
                delete from ops_lingxing_owner_user_mappings
                where source_account_ref = :account and owner_uid = :owner_uid
                returning app_user_id
            """), params,
        )
        if old is not None:
            session.execute(
                text("""
                    insert into ops_lingxing_owner_mapping_audit
                      (source_account_ref, owner_uid, before_user_id,
                       after_user_id, actor_user_id, action)
                    values (:account, :owner_uid, :before, null, :actor, 'revoke')
                """), {**params, "before": old},
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return success_response(request, data={"deleted": old is not None}, meta=None)
