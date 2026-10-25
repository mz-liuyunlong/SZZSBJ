"""Listing management grade rule configuration and audit read API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ErrorEnvelope, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.listing_rule_config.schemas import (
    ListingGradeRuleHistoryData,
    ListingGradeRuleRead,
    ListingGradeRuleUpdate,
)
from app.modules.listing_rule_config.service import ListingGradeRuleService

router = APIRouter(prefix="/api/listings/rule-config", tags=["Listing Rule Configuration"])
DB = Annotated[Session, Depends(get_db_session)]
READ = "page:products:listing-management:view"
WRITE = "action:products:listing-management:configure-rules"
read_principal = Annotated[Principal, Depends(require_permission(READ))]
write_principal = Annotated[Principal, Depends(require_permission(WRITE))]
ERRORS = {401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope},
          409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope},
          500: {"model": ErrorEnvelope}}


@router.get(
    "", response_model=SuccessEnvelope[ListingGradeRuleRead, dict[str, str]],
    responses=ERRORS, summary="读取最新保存的 Listing 评级配置",
)
def get_rule(request: Request, session: DB, principal: read_principal):
    result = ListingGradeRuleService(session).get(
        can_edit=has_permission(principal, WRITE),
    )
    return success_response(request, data=result, meta={"source": result.source})


@router.put(
    "", response_model=SuccessEnvelope[ListingGradeRuleRead, dict[str, str]],
    responses=ERRORS, summary="创建下一生效周期的评级规则版本",
)
def update_rule(request: Request, payload: ListingGradeRuleUpdate, session: DB,
                principal: write_principal):
    result = ListingGradeRuleService(session).update(
        request=payload, actor=principal.user_id,
    )
    return success_response(request, data=result, meta={"source": "database"})


@router.get(
    "/history", response_model=SuccessEnvelope[ListingGradeRuleHistoryData, dict[str, str]],
    responses=ERRORS, summary="查看 Listing 评级配置版本历史",
)
def get_history(request: Request, session: DB, _principal: read_principal,
                limit: Annotated[int, Query(ge=1, le=100)] = 20,
                offset: Annotated[int, Query(ge=0)] = 0):
    result = ListingGradeRuleService(session).history(limit=limit, offset=offset)
    return success_response(request, data=result, meta={"source": "database"})
