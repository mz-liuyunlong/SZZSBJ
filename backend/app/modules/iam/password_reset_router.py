from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.iam.password_reset_service import (
    PasswordResetContext,
    confirm_password_reset,
    request_password_reset,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PasswordResetRequestPayload(BaseModel):
    real_name: str = Field(min_length=2, max_length=64)


class PasswordResetConfirmPayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetMessage(BaseModel):
    message: str


@router.post(
    "/password-reset/request",
    response_model=SuccessEnvelope[PasswordResetMessage, None],
)
def request_reset(
    payload: PasswordResetRequestPayload,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[PasswordResetMessage, None]:
    settings = get_settings()
    message = request_password_reset(
        session,
        real_name=payload.real_name,
        setup_base_url=settings.feishu_password_setup_base_url,
        context=PasswordResetContext(
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
    )
    return success_response(request, data=PasswordResetMessage(message=message), meta=None)


@router.post(
    "/password-reset/confirm",
    response_model=SuccessEnvelope[PasswordResetMessage, None],
)
def confirm_reset(
    payload: PasswordResetConfirmPayload,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[PasswordResetMessage, None]:
    message = confirm_password_reset(
        session,
        token=payload.token,
        new_password=payload.new_password,
    )
    return success_response(request, data=PasswordResetMessage(message=message), meta=None)
