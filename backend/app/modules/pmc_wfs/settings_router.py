"""WFS settings routes (PRP ``PRPs/pmc-wfs-settings.md`` §5), prefix
``/api/pmc/wfs/settings``. Read = ``page:pmc:wfs:view``; write =
``action:pmc:wfs-settings:manage`` (not in the read-only preview principal, so 5173 writes
stay off, R-6). Every write records operator and reason.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_wfs.settings_models import SETTINGS_TABLES
from app.modules.pmc_wfs.settings_schemas import (
    ChangeQuery,
    ChannelQuery,
    CreationDefaultsOut,
    CreationDefaultsUpdate,
    FcRegionList,
    FcRegionOut,
    FcRegionQuery,
    FcRegionUpdate,
    LogisticsChannelList,
    RuleRowPage,
    RuleRowQuery,
    RuleSetOut,
    RuleVersionCreate,
    RuleVersionList,
    SettingsChangeList,
)
from app.modules.pmc_wfs.settings_service import WfsSettingsService

PERMISSION_READ = "page:pmc:wfs:view"
PERMISSION_MANAGE = "action:pmc:wfs-settings:manage"

router = APIRouter(prefix="/api/pmc/wfs/settings", tags=["PMC WFS Settings"])
DB = Annotated[Session, Depends(get_db_session)]
Accounts = Annotated[frozenset[str], Depends(require_source_account_scope)]
Read = Annotated[Principal, Depends(require_permission(PERMISSION_READ))]
Manage = Annotated[Principal, Depends(require_permission(PERMISSION_MANAGE))]
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 500, 503)
}


def _meta(**extra: Any) -> dict[str, Any]:
    return {"source": "new_system_postgresql", "source_tables": list(SETTINGS_TABLES), **extra}


def _svc(session: DB, accounts: Accounts) -> WfsSettingsService:
    return WfsSettingsService(session, accounts)


Svc = Annotated[WfsSettingsService, Depends(_svc)]


@router.get(
    "/rules",
    response_model=SuccessEnvelope[RuleSetOut, dict],
    responses=ERRORS,
    operation_id="getPmcWfsSettingsRules",
    summary="当日生效的时效 / 提醒规则（?at= 取某天生效的版本）",
)
def get_rules(
    request: Request, svc: Svc, _: Read, at: Annotated[date | None, Query()] = None
) -> SuccessEnvelope[RuleSetOut, dict]:
    return success_response(request, data=svc.get_effective_rules(at), meta=_meta())


@router.get(
    "/rules/rows",
    response_model=SuccessEnvelope[RuleRowPage, dict],
    responses=ERRORS,
    operation_id="listPmcWfsSettingsRuleRows",
    summary="生效版本的规则行（服务端分页、筛选、排序；保存仍按整版）",
)
def rule_rows(
    request: Request, query: Annotated[RuleRowQuery, Query()], svc: Svc, _: Read
) -> SuccessEnvelope[RuleRowPage, dict]:
    data = svc.page_rule_rows(query)
    return success_response(
        request,
        data=data,
        meta=_meta(page=query.page, page_size=query.page_size, total=data.total),
    )


@router.get(
    "/rules/versions",
    response_model=SuccessEnvelope[RuleVersionList, dict],
    responses=ERRORS,
    operation_id="listPmcWfsSettingsRuleVersions",
    summary="规则版本历史",
)
def list_versions(request: Request, svc: Svc, _: Read) -> SuccessEnvelope[RuleVersionList, dict]:
    return success_response(request, data=RuleVersionList(items=svc.list_versions()), meta=_meta())


@router.post(
    "/rules/versions",
    response_model=SuccessEnvelope[RuleSetOut, dict],
    responses=ERRORS,
    status_code=201,
    operation_id="createPmcWfsSettingsRuleVersion",
    summary="保存新规则版本（整表 + 生效日 + 原因；生效日不早于今天）",
)
def create_version(
    request: Request, cmd: RuleVersionCreate, svc: Svc, actor: Manage
) -> SuccessEnvelope[RuleSetOut, dict]:
    return success_response(request, data=svc.create_version(cmd, actor.user_id), meta=_meta())


@router.get(
    "/fc-regions",
    response_model=SuccessEnvelope[FcRegionList, dict],
    responses=ERRORS,
    operation_id="listPmcWfsSettingsFcRegions",
    summary="Walmart 仓库（FC）与地区（服务端分页、筛选）",
)
def fc_regions(
    request: Request, query: Annotated[FcRegionQuery, Query()], svc: Svc, _: Read
) -> SuccessEnvelope[FcRegionList, dict]:
    items, total, states = svc.page_fc_regions(query)
    return success_response(
        request,
        data=FcRegionList(items=items, total=total, states=states),
        meta=_meta(page=query.page, page_size=query.page_size, total=total),
    )


@router.put(
    "/fc-regions/{fc}",
    response_model=SuccessEnvelope[FcRegionOut, dict],
    responses=ERRORS,
    operation_id="updatePmcWfsSettingsFcRegion",
    summary="改 FC 地区（美西 / 美中 / 美东 / 待定）",
)
def update_fc_region(
    request: Request,
    fc: Annotated[str, Path(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    cmd: FcRegionUpdate,
    svc: Svc,
    actor: Manage,
) -> SuccessEnvelope[FcRegionOut, dict]:
    return success_response(
        request, data=svc.update_fc_region(fc, cmd, actor.user_id), meta=_meta()
    )


@router.get(
    "/creation-defaults",
    response_model=SuccessEnvelope[CreationDefaultsOut, dict],
    responses=ERRORS,
    operation_id="getPmcWfsSettingsCreationDefaults",
    summary="创建货件默认值（本账号未保存时为 8088 默认值）",
)
def creation_defaults(
    request: Request,
    svc: Svc,
    _: Read,
    source_account_ref: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> SuccessEnvelope[CreationDefaultsOut, dict]:
    return success_response(
        request, data=svc.get_creation_defaults(source_account_ref), meta=_meta()
    )


@router.put(
    "/creation-defaults",
    response_model=SuccessEnvelope[CreationDefaultsOut, dict],
    responses=ERRORS,
    operation_id="updatePmcWfsSettingsCreationDefaults",
    summary="改创建货件默认值",
)
def update_creation_defaults(
    request: Request, cmd: CreationDefaultsUpdate, svc: Svc, actor: Manage
) -> SuccessEnvelope[CreationDefaultsOut, dict]:
    return success_response(
        request, data=svc.update_creation_defaults(cmd, actor.user_id), meta=_meta()
    )


@router.get(
    "/logistics-channels",
    response_model=SuccessEnvelope[LogisticsChannelList, dict],
    responses=ERRORS,
    operation_id="listPmcWfsSettingsLogisticsChannels",
    summary="物流商 / 渠道字典（只读，领星渠道文件；服务端分页、筛选）",
)
def logistics_channels(
    request: Request, query: Annotated[ChannelQuery, Query()], svc: Svc, _: Read
) -> SuccessEnvelope[LogisticsChannelList, dict]:
    items, loaded, total, providers, methods = svc.logistics_channels(query)
    return success_response(
        request,
        data=LogisticsChannelList(
            items=items, loaded=loaded, total=total, providers=providers, methods=methods
        ),
        meta=_meta(page=query.page, page_size=query.page_size, total=total),
    )


@router.get(
    "/changes",
    response_model=SuccessEnvelope[SettingsChangeList, dict],
    responses=ERRORS,
    operation_id="listPmcWfsSettingsChanges",
    summary="设置修改记录",
)
def changes(
    request: Request, query: Annotated[ChangeQuery, Query()], svc: Svc, _: Read
) -> SuccessEnvelope[SettingsChangeList, dict]:
    items, total = svc.list_changes(query)
    return success_response(
        request,
        data=SettingsChangeList(items=items, total=total),
        meta=_meta(page=query.page, page_size=query.page_size, total=total),
    )
