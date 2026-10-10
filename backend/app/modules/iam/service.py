from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.iam.feishu_directory_service import (
    FeishuDirectoryError,
    FeishuDirectoryService,
    FeishuDirectoryUser,
)
from app.modules.iam.feishu_service import (
    FeishuDeliveryError,
    FeishuEmployeeOffboardingNotice,
    FeishuService,
)
from app.modules.iam.password_reset_service import (
    build_onboarding_guide_url,
    create_employee_onboarding_password_setup,
)
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import (
    CurrentUserRead,
    FeishuDirectorySearchResult,
    FeishuDirectoryUserRead,
    LoginResponse,
    PermissionRead,
    RoleCreateRequest,
    RoleRead,
    RoleUpdateRequest,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
)
from app.modules.iam.security import hash_password, issue_access_token, token_hash, verify_password

logger = logging.getLogger(__name__)


def normalize_username(username: str) -> str:
    value = username.strip()
    if not value:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    return value


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def department_ids_to_text(values: list[str] | None) -> str | None:
    if not values:
        return None
    normalized = [item.strip() for item in values if item.strip()]
    return ",".join(dict.fromkeys(normalized)) or None


def department_ids_from_text(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def to_feishu_user_read(user: FeishuDirectoryUser) -> FeishuDirectoryUserRead:
    return FeishuDirectoryUserRead(
        name=user.name,
        open_id=user.open_id,
        user_id=user.user_id,
        union_id=user.union_id,
        employee_id=user.employee_id,
        department_ids=list(user.department_ids),
    )


def to_user_read(row: Mapping[str, Any]) -> UserRead:
    return UserRead(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=row.get("display_name") or str(row["username"]),
        phone=row.get("phone"),
        email=row.get("email"),
        is_active=int(row.get("is_active") or 0) == 1,
        is_super_admin=int(row.get("is_super_admin") or 0) == 1,
        role_keys=[str(item) for item in row.get("role_keys", [])],
        role_names=[str(item) for item in row.get("role_names", [])],
        feishu_name=row.get("feishu_name"),
        feishu_open_id=row.get("feishu_open_id"),
        feishu_user_id=row.get("feishu_user_id"),
        feishu_union_id=row.get("feishu_union_id"),
        feishu_employee_id=row.get("feishu_employee_id"),
        feishu_department_ids=department_ids_from_text(row.get("feishu_department_ids")),
        feishu_last_synced_at=row.get("feishu_last_synced_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row.get("last_login_at"),
    )


def to_role_read(row: Mapping[str, Any]) -> RoleRead:
    return RoleRead(
        id=str(row["id"]),
        role_key=str(row["role_key"]),
        name=str(row["name"]),
        description=row.get("description"),
        is_system=int(row.get("is_system") or 0) == 1,
        user_count=int(row.get("user_count") or 0),
        permission_keys=[str(item) for item in row.get("permission_keys", [])],
    )


def to_permission_read(row: Mapping[str, Any]) -> PermissionRead:
    return PermissionRead(
        permission_key=str(row["permission_key"]),
        name=str(row["name"]),
        group_key=str(row["group_key"]),
        description=row.get("description"),
    )


class IamService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IamRepository(session)

    def login(self, username: str, password: str) -> LoginResponse:
        user = self.repository.get_user_by_username(normalize_username(username))
        if user is None or not verify_password(password, str(user["password_hash"])):
            raise ApiError(code=ErrorCode.UNAUTHORIZED, status_code=401)
        if int(user["is_active"]) != 1:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

        access_token, access_token_hash, expires_at = issue_access_token()
        self.repository.create_session(
            user_id=int(user["id"]),
            token_hash=access_token_hash,
            expires_at=expires_at,
        )
        self.repository.touch_last_login(int(user["id"]))
        self.session.commit()

        refreshed = self._user_row_or_404(int(user["id"]))
        return LoginResponse(
            access_token=access_token, expires_at=expires_at, user=to_user_read(refreshed)
        )

    def current_user(self, principal: Principal) -> CurrentUserRead:
        user_id = int(principal.user_id)
        row = self._user_row_or_404(user_id)
        user = to_user_read(row)
        permissions = sorted(self.repository.user_permission_keys(user_id))
        return CurrentUserRead(**user.model_dump(), permissions=permissions)

    def logout(self, access_token: str) -> None:
        self.repository.revoke_session(token_hash(access_token))
        self.session.commit()

    def list_users(self) -> list[UserRead]:
        return [to_user_read(row) for row in self.repository.list_users()]

    def search_feishu_users(self, name: str) -> FeishuDirectorySearchResult:
        query_name = name.strip()
        if not query_name:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        try:
            result = FeishuDirectoryService.from_settings(get_settings()).find_users_by_name(
                query_name
            )
        except FeishuDirectoryError as exc:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=502,
                message="飞书通讯录查询失败",
            ) from exc
        return FeishuDirectorySearchResult(
            query_name=result.query_name,
            matched_count=result.matched_count,
            is_unique=result.is_unique,
            users=[to_feishu_user_read(user) for user in result.matches],
        )

    def create_user(self, payload: UserCreateRequest) -> UserRead:
        username = normalize_username(payload.username)
        if self.repository.get_user_by_username(username) is not None:
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=400, message="用户名已存在")

        feishu_open_id = optional_text(payload.feishu_open_id)
        self._ensure_feishu_open_id_available(feishu_open_id)

        password = optional_text(payload.password)
        if password is None and feishu_open_id is None:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                message="未绑定飞书员工时必须填写初始密码",
            )

        user_id = self.repository.create_user(
            username=username,
            password_hash=hash_password(password or secrets.token_urlsafe(32)),
            display_name=(payload.display_name or username).strip(),
            phone=payload.phone.strip() if payload.phone else None,
            email=payload.email.strip() if payload.email else None,
            feishu_name=optional_text(payload.feishu_name),
            feishu_open_id=feishu_open_id,
            feishu_user_id=optional_text(payload.feishu_user_id),
            feishu_union_id=optional_text(payload.feishu_union_id),
            feishu_employee_id=optional_text(payload.feishu_employee_id),
            feishu_department_ids=department_ids_to_text(payload.feishu_department_ids),
        )
        self.repository.set_user_roles(
            user_id=user_id, role_keys=payload.role_keys or ("operations",)
        )
        self.session.commit()

        if feishu_open_id:
            settings = get_settings()
            setup_base_url = settings.feishu_password_setup_base_url
            create_employee_onboarding_password_setup(
                self.session,
                user_id=user_id,
                username=username,
                real_name=optional_text(payload.feishu_name)
                or optional_text(payload.display_name)
                or username,
                setup_base_url=setup_base_url,
                recipient_open_id=feishu_open_id,
                recipient_user_id=optional_text(payload.feishu_user_id),
                onboarding_guide_url=build_onboarding_guide_url(setup_base_url),
            )

        return to_user_read(self._user_row_or_404(user_id))

    def update_user(self, user_id: int, payload: UserUpdateRequest) -> UserRead:
        self._user_row_or_404(user_id)
        feishu_open_id = optional_text(payload.feishu_open_id)
        self._ensure_feishu_open_id_available(feishu_open_id, except_user_id=user_id)
        self.repository.update_user(
            user_id=user_id,
            display_name=payload.display_name.strip() if payload.display_name else None,
            phone=payload.phone.strip() if payload.phone else None,
            email=payload.email.strip() if payload.email else None,
            feishu_name=optional_text(payload.feishu_name),
            feishu_open_id=feishu_open_id,
            feishu_user_id=optional_text(payload.feishu_user_id),
            feishu_union_id=optional_text(payload.feishu_union_id),
            feishu_employee_id=optional_text(payload.feishu_employee_id),
            feishu_department_ids=department_ids_to_text(payload.feishu_department_ids),
            is_active=payload.is_active,
        )
        if payload.role_keys is not None:
            self.repository.set_user_roles(user_id=user_id, role_keys=payload.role_keys)
        self.session.commit()
        return to_user_read(self._user_row_or_404(user_id))

    def reset_password(self, user_id: int, new_password: str) -> UserRead:
        self._user_row_or_404(user_id)
        self.repository.reset_password(user_id=user_id, password_hash=hash_password(new_password))
        self.session.commit()
        return to_user_read(self._user_row_or_404(user_id))

    def deactivate_user(self, user_id: int) -> UserRead:
        user = self._user_row_or_404(user_id)
        self.repository.update_user(
            user_id=user_id,
            display_name=None,
            phone=None,
            email=None,
            feishu_name=None,
            feishu_open_id=None,
            feishu_user_id=None,
            feishu_union_id=None,
            feishu_employee_id=None,
            feishu_department_ids=None,
            is_active=False,
        )
        self.repository.revoke_user_sessions(user_id)
        self.repository.revoke_user_password_setup_tokens(user_id)
        self.session.commit()
        self._send_offboarding_notice(user)
        return to_user_read(self._user_row_or_404(user_id))

    def list_roles(self) -> list[RoleRead]:
        return [to_role_read(row) for row in self.repository.list_roles()]

    def list_permissions(self) -> list[PermissionRead]:
        return [to_permission_read(row) for row in self.repository.list_permissions()]

    def create_role(self, payload: RoleCreateRequest) -> RoleRead:
        self.repository.create_role(
            role_key=payload.role_key,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
        )
        self.repository.set_role_permissions(
            role_key=payload.role_key,
            permission_keys=payload.permission_keys,
        )
        self.session.commit()
        return self._role_or_404(payload.role_key)

    def update_role(self, role_key: str, payload: RoleUpdateRequest) -> RoleRead:
        self._role_or_404(role_key)
        self.repository.update_role(
            role_key=role_key,
            name=payload.name.strip() if payload.name else None,
            description=payload.description.strip() if payload.description else None,
        )
        if payload.permission_keys is not None:
            self.repository.set_role_permissions(
                role_key=role_key,
                permission_keys=payload.permission_keys,
            )
        self.session.commit()
        return self._role_or_404(role_key)

    def _send_offboarding_notice(self, user: Mapping[str, Any]) -> None:
        settings = get_settings()
        recipient_open_id = optional_text(
            getattr(settings, "feishu_offboarding_notice_open_id", None)
        )
        recipient_user_id = optional_text(
            getattr(settings, "feishu_offboarding_notice_user_id", None)
        )

        if not recipient_open_id and not recipient_user_id:
            return

        try:
            FeishuService.from_settings().send_employee_offboarding_notice(
                FeishuEmployeeOffboardingNotice(
                    recipient_open_id=recipient_open_id,
                    recipient_user_id=recipient_user_id,
                    departed_username=str(user.get("username") or ""),
                    departed_name=str(
                        user.get("feishu_name")
                        or user.get("display_name")
                        or user.get("username")
                        or ""
                    ),
                )
            )
        except FeishuDeliveryError as exc:
            logger.warning(
                "Feishu offboarding notice failed after local account deactivation.",
                extra={
                    "user_id": user.get("id"),
                    "reason": str(exc)[:200],
                },
            )

    def _ensure_feishu_open_id_available(
        self,
        feishu_open_id: str | None,
        *,
        except_user_id: int | None = None,
    ) -> None:
        if not feishu_open_id:
            return
        existing = self.repository.get_user_by_feishu_open_id(feishu_open_id)
        if existing is None:
            return
        if except_user_id is not None and int(existing["id"]) == except_user_id:
            return
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=400,
            message="飞书用户已绑定其他系统账号",
        )

    def _user_row_or_404(self, user_id: int) -> Mapping[str, Any]:
        rows = self.repository.list_users()
        for row in rows:
            if int(row["id"]) == user_id:
                return row
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    def _role_or_404(self, role_key: str) -> RoleRead:
        for row in self.repository.list_roles():
            if str(row["role_key"]) == role_key:
                return to_role_read(row)
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)


def resolve_principal_from_token(access_token: str) -> Principal | None:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        repository = IamRepository(session)
        session_user = repository.get_session_user(token_hash(access_token))
        if session_user is None:
            return None
        user_id = int(session_user["id"])
        permissions = repository.user_permission_keys(user_id)
        return Principal(user_id=str(user_id), permissions=frozenset(permissions))
    finally:
        session.close()
