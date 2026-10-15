from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, get_request_id, success_response
from app.core.auth import Principal
from app.core.permissions import require_any_permission, require_permission
from app.db.session import get_db_session
from app.modules.iam.rbac_schemas import (
    AuditEventRead,
    PermissionCatalogRead,
    RbacRoleCreateRequest,
    RbacRoleRead,
    RbacRoleUpdateRequest,
    RoleDataScopeRead,
    RoleDataScopeUpdateRequest,
    UserRoleOptionRead,
    UserRolesUpdateRequest,
)
from app.modules.iam.rbac_service import AuditContext, RbacService
from app.modules.iam.schemas import UserRead

router = APIRouter(tags=["iam-rbac-v2"])
db_session = Annotated[Session, Depends(get_db_session)]
role_read_principal = Annotated[
    Principal,
    Depends(
        require_any_permission(
            "page:settings:role-management:view",
            "settings:roles:read",
        )
    ),
]
user_read_principal = Annotated[
    Principal,
    Depends(
        require_any_permission(
            "page:settings:user-management:view",
            "settings:users:read",
        )
    ),
]


def _audit_context(request: Request) -> AuditContext:
    return AuditContext(
        request_id=get_request_id(request),
        request_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.get(
    "/api/settings/rbac/catalog",
    response_model=SuccessEnvelope[PermissionCatalogRead, None],
)
def get_permission_catalog(
    request: Request,
    _: role_read_principal,
    session: db_session,
) -> SuccessEnvelope[PermissionCatalogRead, None]:
    return success_response(
        request,
        data=RbacService(session).permission_catalog(),
        meta=None,
    )


@router.get(
    "/api/settings/rbac/roles",
    response_model=SuccessEnvelope[list[RbacRoleRead], None],
)
def list_rbac_roles(
    request: Request,
    _: role_read_principal,
    session: db_session,
) -> SuccessEnvelope[list[RbacRoleRead], None]:
    return success_response(request, data=RbacService(session).list_roles(), meta=None)


@router.post(
    "/api/settings/rbac/roles",
    response_model=SuccessEnvelope[RbacRoleRead, None],
)
def create_rbac_role(
    request: Request,
    payload: RbacRoleCreateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:role-management:create",
                "settings:roles:write",
            )
        ),
    ],
    session: db_session,
) -> SuccessEnvelope[RbacRoleRead, None]:
    return success_response(
        request,
        data=RbacService(session).create_role(
            actor=principal,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.patch(
    "/api/settings/rbac/roles/{role_key}",
    response_model=SuccessEnvelope[RbacRoleRead, None],
)
def update_rbac_role(
    request: Request,
    role_key: str,
    payload: RbacRoleUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:role-management:configure-permissions",
                "settings:roles:write",
            )
        ),
    ],
    session: db_session,
) -> SuccessEnvelope[RbacRoleRead, None]:
    return success_response(
        request,
        data=RbacService(session).update_role(
            actor=principal,
            role_key=role_key,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.get(
    "/api/settings/user-role-options",
    response_model=SuccessEnvelope[list[UserRoleOptionRead], None],
)
def list_user_role_options(
    request: Request,
    principal: user_read_principal,
    session: db_session,
) -> SuccessEnvelope[list[UserRoleOptionRead], None]:
    return success_response(
        request,
        data=RbacService(session).user_role_options(principal),
        meta=None,
    )


@router.put(
    "/api/settings/users/{user_id}/roles",
    response_model=SuccessEnvelope[UserRead, None],
)
def update_user_roles(
    request: Request,
    user_id: int,
    payload: UserRolesUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "action:settings:user-management:assign-role",
                "settings:users:write",
            )
        ),
    ],
    session: db_session,
) -> SuccessEnvelope[UserRead, None]:
    return success_response(
        request,
        data=RbacService(session).assign_user_roles(
            actor=principal,
            user_id=user_id,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.get(
    "/api/settings/rbac/roles/{role_key}/data-scopes",
    response_model=SuccessEnvelope[RoleDataScopeRead, None],
)
def get_role_data_scopes(
    request: Request,
    role_key: str,
    _: role_read_principal,
    session: db_session,
) -> SuccessEnvelope[RoleDataScopeRead, None]:
    return success_response(
        request,
        data=RbacService(session).role_data_scopes(role_key),
        meta=None,
    )


@router.put(
    "/api/settings/rbac/roles/{role_key}/data-scopes",
    response_model=SuccessEnvelope[RoleDataScopeRead, None],
)
def update_role_data_scopes(
    request: Request,
    role_key: str,
    payload: RoleDataScopeUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(
            require_permission(
                "action:settings:role-management:configure-data-scope"
            )
        ),
    ],
    session: db_session,
) -> SuccessEnvelope[RoleDataScopeRead, None]:
    return success_response(
        request,
        data=RbacService(session).update_role_data_scopes(
            actor=principal,
            role_key=role_key,
            payload=payload,
            audit=_audit_context(request),
        ),
        meta=None,
    )


@router.get(
    "/api/settings/rbac/audit-events",
    response_model=SuccessEnvelope[list[AuditEventRead], None],
)
def list_rbac_audit_events(
    request: Request,
    _: Annotated[
        Principal,
        Depends(require_permission("action:settings:role-management:view-audit")),
    ],
    session: db_session,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessEnvelope[list[AuditEventRead], None]:
    return success_response(
        request,
        data=RbacService(session).audit_events(limit=limit),
        meta=None,
    )
