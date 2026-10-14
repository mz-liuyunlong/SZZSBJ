from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.db.session import get_db_session
from app.modules.iam.schemas import (
    CurrentUserRead,
    FeishuDirectorySearchResult,
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    PermissionRead,
    RoleCreateRequest,
    RoleRead,
    RoleUpdateRequest,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
)
from app.modules.iam.service import IamService

router = APIRouter(tags=["iam"])


def require_permission(permission_key: str):
    def dependency(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> Principal:
        if "*" in principal.permissions or permission_key in principal.permissions:
            return principal
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    return dependency


def bearer_token_from_header(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
    return token


@router.post("/api/auth/login", response_model=SuccessEnvelope[LoginResponse, None])
def login(
    request: Request,
    payload: LoginRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[LoginResponse, None]:
    data = IamService(session).login(payload.username, payload.password)
    return success_response(request, data=data, meta=None)


@router.get("/api/auth/me", response_model=SuccessEnvelope[CurrentUserRead, None])
def me(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[CurrentUserRead, None]:
    data = IamService(session).current_user(principal)
    return success_response(request, data=data, meta=None)


@router.post("/api/auth/logout", response_model=SuccessEnvelope[dict[str, bool], None])
def logout(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> SuccessEnvelope[dict[str, bool], None]:
    IamService(session).logout(bearer_token_from_header(authorization))
    return success_response(request, data={"revoked": True}, meta=None)


@router.get("/api/settings/users", response_model=SuccessEnvelope[list[UserRead], None])
def list_users(
    request: Request,
    _: Annotated[Principal, Depends(require_permission("settings:users:read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[list[UserRead], None]:
    return success_response(request, data=IamService(session).list_users(), meta=None)


@router.get(
    "/api/settings/users/feishu/search",
    response_model=SuccessEnvelope[FeishuDirectorySearchResult, None],
)
def search_feishu_users(
    request: Request,
    name: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[Principal, Depends(require_permission("settings:users:read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[FeishuDirectorySearchResult, None]:
    return success_response(
        request,
        data=IamService(session).search_feishu_users(name),
        meta=None,
    )


@router.post("/api/settings/users", response_model=SuccessEnvelope[UserRead, None])
def create_user(
    request: Request,
    payload: UserCreateRequest,
    _: Annotated[Principal, Depends(require_permission("settings:users:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(request, data=IamService(session).create_user(payload), meta=None)


@router.patch("/api/settings/users/{user_id}", response_model=SuccessEnvelope[UserRead, None])
def update_user(
    request: Request,
    user_id: int,
    payload: UserUpdateRequest,
    _: Annotated[Principal, Depends(require_permission("settings:users:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request, data=IamService(session).update_user(user_id, payload), meta=None
    )


@router.post(
    "/api/settings/users/{user_id}/reset-password", response_model=SuccessEnvelope[UserRead, None]
)
def reset_password(
    request: Request,
    user_id: int,
    payload: PasswordResetRequest,
    _: Annotated[Principal, Depends(require_permission("settings:users:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request,
        data=IamService(session).reset_password(user_id, payload.new_password),
        meta=None,
    )


@router.delete("/api/settings/users/{user_id}", response_model=SuccessEnvelope[UserRead, None])
def delete_user(
    request: Request,
    user_id: int,
    _: Annotated[Principal, Depends(require_permission("settings:users:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(request, data=IamService(session).deactivate_user(user_id), meta=None)


@router.get("/api/settings/roles", response_model=SuccessEnvelope[list[RoleRead], None])
def list_roles(
    request: Request,
    _: Annotated[Principal, Depends(require_permission("settings:roles:read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[list[RoleRead], None]:
    return success_response(request, data=IamService(session).list_roles(), meta=None)


@router.post("/api/settings/roles", response_model=SuccessEnvelope[RoleRead, None])
def create_role(
    request: Request,
    payload: RoleCreateRequest,
    _: Annotated[Principal, Depends(require_permission("settings:roles:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[RoleRead, None]:
    return success_response(request, data=IamService(session).create_role(payload), meta=None)


@router.patch("/api/settings/roles/{role_key}", response_model=SuccessEnvelope[RoleRead, None])
def update_role(
    request: Request,
    role_key: str,
    payload: RoleUpdateRequest,
    _: Annotated[Principal, Depends(require_permission("settings:roles:write"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[RoleRead, None]:
    return success_response(
        request, data=IamService(session).update_role(role_key, payload), meta=None
    )


@router.get("/api/settings/permissions", response_model=SuccessEnvelope[list[PermissionRead], None])
def list_permissions(
    request: Request,
    _: Annotated[Principal, Depends(require_permission("settings:roles:read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[list[PermissionRead], None]:
    return success_response(request, data=IamService(session).list_permissions(), meta=None)
