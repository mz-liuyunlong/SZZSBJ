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
# Owner mapping is an administrator-managed employee onboarding operation.
# An IAM administrator is not necessarily an operation-log editor.
# _admin_only(access) and source-account checks still apply to all routes.
mapping_read_dep = Annotated[
    Principal,
    Depends(
        require_any_permission(
            "page:settings:user-management:view",
            "settings:users:read",
            "page:operations:log:view",
            "page:sales:daily-sales:view",
        )
    ),
]
mapping_write_dep = Annotated[
    Principal,
    Depends(
        require_any_permission(
            "action:settings:user-management:edit",
            "action:settings:user-management:configure-data-scope",
            "settings:users:write",
            "action:operations:log:edit",
        )
    ),
]
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


@router.get(
    "/owner-mappings", response_model=SuccessEnvelope[list[dict[str, Any]], Any], responses=errors
)
def list_owner_mappings(
    request: Request,
    session: db_dep,
    _: mapping_read_dep,
    access: access_dep,
) -> SuccessEnvelope[list[dict[str, Any]], Any]:
    _admin_only(access)
    records = (
        session.execute(
            text("""
            select m.source_account_ref, m.owner_uid, m.app_user_id,
                   u.username, u.display_name
            from ops_lingxing_owner_user_mappings m
            join app_users u on u.id = m.app_user_id
            where m.source_account_ref = any(:accounts)
            order by m.source_account_ref, m.owner_uid
        """),
            {"accounts": list(access.accounts)},
        )
        .mappings()
        .all()
    )
    return success_response(request, data=[dict(r) for r in records], meta=None)


@router.put(
    "/owner-mappings", response_model=SuccessEnvelope[dict[str, bool], Any], responses=errors
)
def put_owner_mapping(
    request: Request,
    payload: OwnerMappingWrite,
    session: db_dep,
    _: mapping_write_dep,
    access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    # Preserve the original API contract, but never allow a silent re-assignment.
    # Delegate to the exact-UID, account-scoped, audited create-only endpoint.
    return assign_owner_mapping(
        request=request, payload=payload, session=session, _=_, access=access
    )


# Explicit UID binding for onboarding. Names are labels, never authorization.
@router.get(
    "/owner-mappings/candidates",
    response_model=SuccessEnvelope[list[dict[str, Any]], Any],
    responses=errors,
)
def list_owner_mapping_candidates(
    request: Request,
    session: db_dep,
    _: mapping_read_dep,
    access: access_dep,
) -> SuccessEnvelope[list[dict[str, Any]], Any]:
    _admin_only(access)
    rows = (
        session.execute(
            text("""
        select p.source_account_ref, btrim(p.owner_uid) as owner_uid,
               min(nullif(btrim(p.owner_name), '')) as owner_name,
               count(*)::int as product_count,
               count(distinct nullif(btrim(p.owner_name), ''))::int as name_count,
               count(*) filter (where nullif(btrim(p.owner_name), '') is null)::int as blank_names,
               m.app_user_id as mapped_user_id
        from dwd_lingxing_sku_product_info_current p
        left join ops_lingxing_owner_user_mappings m
          on m.source_account_ref = p.source_account_ref
         and m.owner_uid = btrim(p.owner_uid)
        where p.source_account_ref = any(:accounts)
          and nullif(btrim(p.owner_uid), '') is not null
        group by p.source_account_ref, btrim(p.owner_uid), m.app_user_id
        order by p.source_account_ref, owner_name, owner_uid
    """),
            {"accounts": list(access.accounts)},
        )
        .mappings()
        .all()
    )
    result = [
        {
            "source_account_ref": r["source_account_ref"],
            "owner_uid": r["owner_uid"],
            "owner_name": r["owner_name"],
            "product_count": int(r["product_count"]),
            "mapped_user_id": r["mapped_user_id"],
            "eligible": int(r["name_count"]) == 1 and int(r["blank_names"]) == 0,
        }
        for r in rows
    ]
    return success_response(request, data=result, meta=None)


@router.post(
    "/owner-mappings/assign",
    response_model=SuccessEnvelope[dict[str, bool], Any],
    responses=errors,
)
def assign_owner_mapping(
    request: Request,
    payload: OwnerMappingWrite,
    session: db_dep,
    _: mapping_write_dep,
    access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    """Only insert an administrator-confirmed UID; never replace another user's binding."""
    _admin_only(access)
    account = payload.source_account_ref.strip()
    uid = payload.owner_uid.strip()
    access.require_account(account)
    if not uid:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    params = {
        "account": account,
        "uid": uid,
        "target": payload.app_user_id,
        "actor": access.user_id,
    }
    user_exists = bool(
        session.scalar(
            text("""
        select exists(select 1 from app_users where id=:target and is_active=true)
    """),
            params,
        )
    )
    if not user_exists:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    # A mapping must never substitute for the employee's RBAC account scope.
    from app.modules.iam.rbac_repository import RbacRepository

    granted = RbacRepository(session).resolve_user_data_scope(
        user_id=payload.app_user_id, scope_type="source_account"
    )
    if "*" not in granted and account not in granted:
        raise ApiError(
            code=ErrorCode.DATA_SCOPE_DENIED,
            status_code=403,
            message="员工没有对应来源账号的数据范围，请先在用户管理中配置",
        )

    source = (
        session.execute(
            text("""
        select count(*)::int as rows,
               count(distinct nullif(btrim(owner_name), ''))::int as names,
               count(*) filter (where nullif(btrim(owner_name), '') is null)::int as blanks
        from dwd_lingxing_sku_product_info_current
        where source_account_ref=:account and btrim(owner_uid)=:uid
    """),
            params,
        )
        .mappings()
        .one()
    )
    if source["rows"] == 0 or source["names"] != 1 or source["blanks"]:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            message="负责人UID不存在或源姓名存在冲突，必须先核验",
        )

    try:
        inserted = session.scalar(
            text("""
            insert into ops_lingxing_owner_user_mappings
                (source_account_ref, owner_uid, app_user_id, updated_by_user_id)
            values (:account, :uid, :target, :actor)
            on conflict (source_account_ref, owner_uid) do nothing
            returning id
        """),
            params,
        )
        if inserted is None:
            bound = session.scalar(
                text("""
                select app_user_id from ops_lingxing_owner_user_mappings
                where source_account_ref=:account and owner_uid=:uid
            """),
                params,
            )
            if bound != payload.app_user_id:
                raise ApiError(
                    code="OWNER_MAPPING_CONFLICT",
                    status_code=409,
                    message="该负责人UID已绑定其他用户，禁止覆盖",
                )
            session.commit()
            return success_response(request, data={"saved": True, "created": False}, meta=None)

        session.execute(
            text("""
            insert into ops_lingxing_owner_mapping_audit
                (source_account_ref, owner_uid, before_user_id,
                 after_user_id, actor_user_id, action)
            values (:account, :uid, null, :target, :actor, 'assign')
        """),
            params,
        )
        session.commit()
        return success_response(request, data={"saved": True, "created": True}, meta=None)
    except Exception:
        session.rollback()
        raise


@router.delete(
    "/owner-mappings/{owner_uid}",
    response_model=SuccessEnvelope[dict[str, bool], Any],
    responses=errors,
)
def delete_owner_mapping(
    request: Request,
    owner_uid: str,
    source_account_ref: str,
    session: db_dep,
    _: mapping_write_dep,
    access: access_dep,
) -> SuccessEnvelope[dict[str, bool], Any]:
    _admin_only(access)
    access.require_account(source_account_ref)
    params = {
        "account": source_account_ref,
        "owner_uid": owner_uid,
        "actor": access.user_id,
    }
    try:
        old = session.scalar(
            text("""
                delete from ops_lingxing_owner_user_mappings
                where source_account_ref = :account and owner_uid = :owner_uid
                returning app_user_id
            """),
            params,
        )
        if old is not None:
            session.execute(
                text("""
                    insert into ops_lingxing_owner_mapping_audit
                      (source_account_ref, owner_uid, before_user_id,
                       after_user_id, actor_user_id, action)
                    values (:account, :owner_uid, :before, null, :actor, 'revoke')
                """),
                {**params, "before": old},
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return success_response(request, data={"deleted": old is not None}, meta=None)
