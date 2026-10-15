from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import (
    has_permission,
    require_any_permission,
    require_super_admin,
)
from app.db.session import get_db_session
from app.modules.iam.rbac_schemas import RbacRoleCreateRequest, RbacRoleUpdateRequest
from app.modules.iam.rbac_service import AuditContext, RbacService
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


def bearer_token_from_header(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
    return token


def _audit_context(request: Request) -> AuditContext:
    return AuditContext(
        request_id=get_request_id(request),
        request_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


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
    _: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "page:settings:user-management:view",
                "settings:users:read",
            )
        ),
    ],
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
    _: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "page:settings:user-management:view",
                "settings:users:read",
            )
        ),
    ],
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
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:user-management:create",
                "settings:users:write",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request,
        data=RbacService(session).create_user(
            actor=principal,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.patch("/api/settings/users/{user_id}", response_model=SuccessEnvelope[UserRead, None])
def update_user(
    request: Request,
    user_id: int,
    payload: UserUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:user-management:edit",
                "action:settings:user-management:enable-disable",
                "settings:users:write",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    if payload.role_keys is not None and not (
        has_permission(principal, "action:settings:user-management:assign-role")
        or has_permission(principal, "settings:users:write")
    ):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    return success_response(
        request,
        data=RbacService(session).update_user(
            actor=principal,
            user_id=user_id,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.post(
    "/api/settings/users/{user_id}/reset-password",
    response_model=SuccessEnvelope[UserRead, None],
)
def reset_password(
    request: Request,
    user_id: int,
    payload: PasswordResetRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:user-management:reset-password",
                "settings:users:write",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request,
        data=RbacService(session).reset_user_password(
            actor=principal,
            user_id=user_id,
            new_password=payload.new_password,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.delete("/api/settings/users/{user_id}", response_model=SuccessEnvelope[UserRead, None])
def delete_user(
    request: Request,
    user_id: int,
    principal: Annotated[Principal, Depends(require_super_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request,
        data=RbacService(session).hard_delete_user(
            actor=principal,
            user_id=user_id,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.get("/api/settings/roles", response_model=SuccessEnvelope[list[RoleRead], None])
def list_roles(
    request: Request,
    _: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "page:settings:role-management:view",
                "settings:roles:read",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[list[RoleRead], None]:
    return success_response(request, data=IamService(session).list_roles(), meta=None)


@router.post("/api/settings/roles", response_model=SuccessEnvelope[RoleRead, None])
def create_role(
    request: Request,
    payload: RoleCreateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:role-management:create",
                "settings:roles:write",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[RoleRead, None]:
    created = RbacService(session).create_role(
        actor=principal,
        payload=RbacRoleCreateRequest(
            role_key=payload.role_key,
            name=payload.name,
            description=payload.description,
            permission_keys=payload.permission_keys,
        ),
        audit=_audit_context(request),
    )
    return success_response(
        request,
        data=RoleRead(
            id=created.id,
            role_key=created.role_key,
            name=created.name,
            description=created.description,
            is_system=created.is_system,
            user_count=created.user_count,
            permission_keys=created.permission_keys,
        ),
        meta=None,
    )


@router.patch("/api/settings/roles/{role_key}", response_model=SuccessEnvelope[RoleRead, None])
def update_role(
    request: Request,
    role_key: str,
    payload: RoleUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:role-management:configure-permissions",
                "settings:roles:write",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[RoleRead, None]:
    rbac = RbacService(session)
    current = rbac.repository.get_role(role_key)
    if current is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    updated = rbac.update_role(
        actor=principal,
        role_key=role_key,
        payload=RbacRoleUpdateRequest(
            permission_keys=(
                payload.permission_keys
                if payload.permission_keys is not None
                else [str(item) for item in current["permission_keys"]]
            ),
            expected_version=int(current.get("version") or 1),
            name=payload.name,
            description=payload.description,
        ),
        audit=_audit_context(request),
    )
    return success_response(
        request,
        data=RoleRead(
            id=updated.id,
            role_key=updated.role_key,
            name=updated.name,
            description=updated.description,
            is_system=updated.is_system,
            user_count=updated.user_count,
            permission_keys=updated.permission_keys,
        ),
        meta=None,
    )


@router.get("/api/settings/permissions", response_model=SuccessEnvelope[list[PermissionRead], None])
def list_permissions(
    request: Request,
    _: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "page:settings:role-management:view",
                "settings:roles:read",
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SuccessEnvelope[list[PermissionRead], None]:
    return success_response(request, data=IamService(session).list_permissions(), meta=None)
