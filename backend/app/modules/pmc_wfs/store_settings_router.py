"""WFS settings · per-store Walmart creation settings (step 4, first slice).

GET lists every Lingxing store in the caller's account/store scope with its current setting;
PUT upserts one store's setting and records who changed it. No external calls.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.packing_models import now
from app.modules.pmc_wfs.store_settings_models import WfsStoreSetting
from app.modules.pmc_wfs.walmart_gateway import STORE_CODE, reviewed_store_map

router = APIRouter(prefix="/api/pmc/wfs/settings", tags=["PMC WFS Settings"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission("page:pmc:wfs:view"))]
Manage = Annotated[Principal, Depends(require_permission("action:pmc:wfs-settings:manage"))]
ERRORS = {code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500, 503)}
_CODE_PREFIX = re.compile(r"^((?:HK|CN)[0-9]{4})-")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StoreSettingRead(Strict):
    source_account_ref: str
    store_id: str
    store_name: str | None
    suggested_code: str | None
    walmart_store_code: str | None
    reviewed_code: str | None
    mapping_state: Literal["unset", "ok", "conflict", "unreviewed"]
    its_enabled: bool
    creation_enabled: bool
    note: str | None
    actor_uid: str | None
    updated_at: datetime | None


class StoreSettingList(Strict):
    items: list[StoreSettingRead]
    total: int


class StoreSettingCommand(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    walmart_store_code: str = Field(pattern=r"^(HK|CN)[0-9]{4}$")
    its_enabled: bool
    creation_enabled: bool
    note: str | None = Field(default=None, max_length=500)


def _store_scope(session: Session, actor: Principal) -> frozenset[str] | None:
    if "*" in actor.permissions:
        return None
    try:
        uid = int(actor.user_id)
    except ValueError:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
    values = RbacRepository(session).resolve_user_data_scope(user_id=uid, scope_type="store")
    if "*" in values:
        return None
    if not values:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    return frozenset(values)


def _stores(session: Session, accounts: frozenset[str], scope: frozenset[str] | None):
    name = func.max(func.nullif(func.trim(Store.store_name), ""))
    stmt = (
        select(Store.source_account_ref, Store.store_id, name)
        .where(Store.source_account_ref.in_(accounts), func.trim(Store.store_id) != "")
        .group_by(Store.source_account_ref, Store.store_id)
        .order_by(Store.store_id)
    )
    if scope is not None:
        stmt = stmt.where(Store.store_id.in_(scope))
    return session.execute(stmt).all()


def _read(
    account: str, store_id: str, store_name: str | None, setting: WfsStoreSetting | None
) -> StoreSettingRead:
    reviewed = reviewed_store_map().get(store_id)
    match = _CODE_PREFIX.match(store_name or "")
    code = setting.walmart_store_code if setting else None
    if code is None:
        state: Literal["unset", "ok", "conflict", "unreviewed"] = "unset"
    elif reviewed is None:
        state = "unreviewed"
    elif reviewed == code:
        state = "ok"
    else:
        state = "conflict"
    return StoreSettingRead(
        source_account_ref=account,
        store_id=store_id,
        store_name=store_name,
        suggested_code=match.group(1) if match else None,
        walmart_store_code=code,
        reviewed_code=reviewed,
        mapping_state=state,
        its_enabled=bool(setting.its_enabled) if setting else False,
        creation_enabled=bool(setting.creation_enabled) if setting else False,
        note=setting.note if setting else None,
        actor_uid=setting.actor_uid if setting else None,
        updated_at=setting.updated_at if setting else None,
    )


def _meta() -> dict:
    return {
        "source": "new_system_postgresql",
        "source_tables": ["ops_wfs_store_settings", "dim_lingxing_stores"],
        "reviewed_map_present": bool(reviewed_store_map()),
    }


@router.get("/stores", response_model=SuccessEnvelope[StoreSettingList, dict], responses=ERRORS)
def list_stores(request: Request, session: DB, accounts: Accounts, actor: Read):
    scope = _store_scope(session, actor)
    rows = _stores(session, accounts, scope)
    settings = {
        (s.source_account_ref, s.store_id): s
        for s in session.scalars(
            select(WfsStoreSetting).where(WfsStoreSetting.source_account_ref.in_(accounts))
        )
    }
    items = [_read(a, sid, name, settings.get((a, sid))) for a, sid, name in rows]
    return success_response(
        request, data=StoreSettingList(items=items, total=len(items)), meta=_meta()
    )


@router.put(
    "/stores/{store_id}",
    response_model=SuccessEnvelope[StoreSettingRead, dict],
    responses=ERRORS,
)
def upsert_store(
    request: Request,
    store_id: str,
    body: StoreSettingCommand,
    session: DB,
    accounts: Accounts,
    actor: Manage,
):
    if body.source_account_ref not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    scope = _store_scope(session, actor)
    if scope is not None and store_id not in scope:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    known = {sid: name for _, sid, name in _stores(session, {body.source_account_ref}, None)}
    if store_id not in known:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    if not STORE_CODE.fullmatch(body.walmart_store_code):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    duplicate = session.scalar(
        select(WfsStoreSetting).where(
            WfsStoreSetting.source_account_ref == body.source_account_ref,
            WfsStoreSetting.walmart_store_code == body.walmart_store_code,
            WfsStoreSetting.store_id != store_id,
        )
    )
    if duplicate is not None:
        raise ApiError(
            code="WFS_STORE_CODE_TAKEN",
            status_code=409,
            message=f"店铺代码 {body.walmart_store_code} 已被另一个店铺使用",
        )
    setting = session.scalar(
        select(WfsStoreSetting).where(
            WfsStoreSetting.source_account_ref == body.source_account_ref,
            WfsStoreSetting.store_id == store_id,
        )
    )
    if setting is None:
        setting = WfsStoreSetting(
            source_account_ref=body.source_account_ref,
            store_id=store_id,
            actor_uid=str(actor.user_id),
        )
        session.add(setting)
    setting.walmart_store_code = body.walmart_store_code
    setting.its_enabled = body.its_enabled
    setting.creation_enabled = body.creation_enabled
    setting.note = body.note
    setting.actor_uid = str(actor.user_id)
    setting.updated_at = now()
    session.commit()
    session.refresh(setting)
    return success_response(
        request,
        data=_read(body.source_account_ref, store_id, known[store_id], setting),
        meta=_meta(),
    )
