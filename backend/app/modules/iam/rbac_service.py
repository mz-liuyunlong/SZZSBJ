from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import Principal
from app.modules.iam.permission_catalog_v2 import MODULE_NAMES
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.iam.rbac_schemas import (
    AuditEventRead,
    DataScopeEntryRead,
    EffectiveDataScopeEntryRead,
    PermissionCatalogRead,
    PermissionItemRead,
    PermissionModuleRead,
    PermissionPageRead,
    RbacRoleCreateRequest,
    RbacRoleRead,
    RbacRoleUpdateRequest,
    RoleDataScopeRead,
    RoleDataScopeUpdateRequest,
    UserDataScopeRead,
    UserDataScopeUpdateRequest,
    UserRoleOptionRead,
    UserRolesUpdateRequest,
)
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import UserCreateRequest, UserRead, UserUpdateRequest
from app.modules.iam.service import IamService, to_user_read


@dataclass(frozen=True, slots=True)
class AuditContext:
    request_id: str | None = None
    request_ip: str | None = None
    user_agent: str | None = None


def _to_role_read(row: dict[str, Any] | Any) -> RbacRoleRead:
    return RbacRoleRead(
        id=str(row["id"]),
        role_key=str(row["role_key"]),
        name=str(row["name"]),
        description=row.get("description"),
        is_system=bool(row.get("is_system")),
        user_count=int(row.get("user_count") or 0),
        permission_keys=[str(item) for item in row.get("permission_keys", [])],
        version=int(row.get("version") or 1),
    )


class RbacService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = RbacRepository(session)
        self.iam_repository = IamRepository(session)
        self.iam_service = IamService(session)

    def permission_catalog(self) -> PermissionCatalogRead:
        rows = self.repository.list_permission_catalog_rows()
        page_rows = {str(row["page_key"]): row for row in rows if row["permission_type"] == "page"}
        child_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in rows:
            permission_type = str(row["permission_type"])
            if permission_type not in {"action", "field"}:
                continue
            page_key = str(row["page_key"])
            child_rows.setdefault(page_key, {"action": [], "field": []})[permission_type].append(
                dict(row)
            )

        modules: dict[str, list[PermissionPageRead]] = {}
        module_sort: dict[str, int] = {}
        for page_key, row in page_rows.items():
            module_key = str(row["module_key"])
            module_sort[module_key] = min(
                module_sort.get(module_key, int(row["sort_order"])),
                int(row["sort_order"]),
            )
            children = child_rows.get(page_key, {"action": [], "field": []})
            modules.setdefault(module_key, []).append(
                PermissionPageRead(
                    page_key=page_key,
                    name=str(row["name"]),
                    permission_key=str(row["permission_key"]),
                    sort_order=int(row["sort_order"]),
                    actions=[self._to_permission_item(item) for item in children["action"]],
                    fields=[self._to_permission_item(item) for item in children["field"]],
                )
            )

        result = [
            PermissionModuleRead(
                module_key=module_key,
                name=MODULE_NAMES.get(module_key, module_key),
                sort_order=module_sort[module_key],
                pages=sorted(pages, key=lambda item: (item.sort_order, item.page_key)),
            )
            for module_key, pages in modules.items()
        ]
        result.sort(key=lambda item: (item.sort_order, item.module_key))
        return PermissionCatalogRead(modules=result)

    def list_roles(self) -> list[RbacRoleRead]:
        return [_to_role_read(row) for row in self.repository.list_roles()]

    def create_role(
        self,
        *,
        actor: Principal,
        payload: RbacRoleCreateRequest,
        audit: AuditContext,
    ) -> RbacRoleRead:
        permission_keys = self._validated_permission_keys(payload.permission_keys)
        self._assert_actor_can_grant(actor, permission_keys)
        self.iam_repository.create_role(
            role_key=payload.role_key,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
        )
        self.iam_repository.set_role_permissions(
            role_key=payload.role_key,
            permission_keys=permission_keys,
        )
        row = self.repository.get_role(payload.role_key)
        if row is None:
            raise ApiError(code=ErrorCode.INTERNAL_ERROR, status_code=500)
        after = _to_role_read(row)
        self._audit(
            actor=actor,
            event_type="role.created",
            target_type="role",
            target_key=payload.role_key,
            before=None,
            after=after.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return after

    def update_role(
        self,
        *,
        actor: Principal,
        role_key: str,
        payload: RbacRoleUpdateRequest,
        audit: AuditContext,
    ) -> RbacRoleRead:
        before_row = self.repository.get_role(role_key)
        if before_row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        before = _to_role_read(before_row)
        if role_key == "admin" and not self._is_super_admin(actor):
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

        permission_keys = self._validated_permission_keys(payload.permission_keys)
        self._assert_actor_can_grant(actor, permission_keys)
        updated = self.repository.set_role_permissions(
            role_key=role_key,
            permission_keys=permission_keys,
            expected_version=payload.expected_version,
            name=payload.name.strip() if payload.name else None,
            description=payload.description.strip() if payload.description else None,
        )
        if not updated:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=409,
                message="角色已被其他管理员修改，请刷新后重试",
                details={"role_key": role_key},
            )
        after_row = self.repository.get_role(role_key)
        if after_row is None:
            raise ApiError(code=ErrorCode.INTERNAL_ERROR, status_code=500)
        after = _to_role_read(after_row)
        self._audit(
            actor=actor,
            event_type="role.permissions.updated",
            target_type="role",
            target_key=role_key,
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return after

    def user_role_options(self, actor: Principal) -> list[UserRoleOptionRead]:
        is_super_admin = self._is_super_admin(actor)
        result: list[UserRoleOptionRead] = []
        for row in self.repository.list_role_options():
            role_key = str(row["role_key"])
            assignable = is_super_admin or self._role_assignment_is_within_actor_scope(
                actor,
                (role_key,),
            )
            result.append(
                UserRoleOptionRead(
                    role_key=role_key,
                    name=str(row["name"]),
                    description=row.get("description"),
                    is_system=bool(row.get("is_system")),
                    assignable=assignable,
                )
            )
        return result

    def assign_user_roles(
        self,
        *,
        actor: Principal,
        user_id: int,
        payload: UserRolesUpdateRequest,
        audit: AuditContext,
    ) -> UserRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        self._assert_can_manage_target(actor, target, allow_self=False)
        role_keys = self._validated_role_keys(payload.role_keys)
        self._assert_actor_can_assign_roles(actor, role_keys)
        before = {
            "user_id": user_id,
            "role_keys": list(self.repository.user_role_keys(user_id)),
        }
        self.repository.set_user_roles(user_id=user_id, role_keys=role_keys)
        after = {"user_id": user_id, "role_keys": list(role_keys)}
        self._audit(
            actor=actor,
            event_type="user.roles.updated",
            target_type="user",
            target_key=str(user_id),
            before=before,
            after=after,
            context=audit,
        )
        self.session.commit()
        refreshed = self.iam_repository.list_users()
        for row in refreshed:
            if int(row["id"]) == user_id:
                return to_user_read(row)
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    def create_user(
        self,
        *,
        actor: Principal,
        payload: UserCreateRequest,
        audit: AuditContext,
    ) -> UserRead:
        role_keys = self._validated_role_keys(payload.role_keys or ["operations"])
        self._assert_actor_can_assign_roles(actor, role_keys)
        normalized = payload.model_copy(update={"role_keys": list(role_keys)})
        created = self.iam_service.create_user(normalized)

        self._audit(
            actor=actor,
            event_type="user.created",
            target_type="user",
            target_key=str(created.id),
            before=None,
            after=created.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return created

    def update_user(
        self,
        *,
        actor: Principal,
        user_id: int,
        payload: UserUpdateRequest,
        audit: AuditContext,
    ) -> UserRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        self._assert_can_manage_target(actor, target, allow_self=True)
        if payload.is_active is False and int(actor.user_id) == user_id:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=400,
                message="不能停用当前登录账号",
            )
        if payload.role_keys is not None:
            role_keys = self._validated_role_keys(payload.role_keys)
            self._assert_actor_can_assign_roles(actor, role_keys)
        before = self.iam_service._user_row_or_404(user_id)  # noqa: SLF001
        updated = self.iam_service.update_user(user_id, payload)
        if payload.is_active is False:
            self.iam_repository.revoke_user_sessions(user_id)
            self.iam_repository.revoke_user_password_setup_tokens(user_id)
        self._audit(
            actor=actor,
            event_type="user.updated",
            target_type="user",
            target_key=str(user_id),
            before=to_user_read(before).model_dump(mode="json"),
            after=updated.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return updated

    def reset_user_password(
        self,
        *,
        actor: Principal,
        user_id: int,
        new_password: str,
        audit: AuditContext,
    ) -> UserRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        self._assert_can_manage_target(actor, target, allow_self=True)
        updated = self.iam_service.reset_password(user_id, new_password)
        self.iam_repository.revoke_user_sessions(user_id)
        self.iam_repository.revoke_user_password_setup_tokens(user_id)
        self._audit(
            actor=actor,
            event_type="user.password.reset",
            target_type="user",
            target_key=str(user_id),
            before=None,
            after={"sessions_revoked": True},
            context=audit,
        )
        self.session.commit()
        return updated

    def hard_delete_user(
        self,
        *,
        actor: Principal,
        user_id: int,
        audit: AuditContext,
    ) -> UserRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        self._assert_can_manage_target(actor, target, allow_self=False)
        before = self.iam_service._user_row_or_404(user_id)  # noqa: SLF001
        deleted = self.iam_service.hard_delete_user(
            user_id,
            actor_user_id=int(actor.user_id),
        )
        self._audit(
            actor=actor,
            event_type="user.deleted",
            target_type="user",
            target_key=str(user_id),
            before=to_user_read(before).model_dump(mode="json"),
            after={"deleted": True},
            context=audit,
        )
        self.session.commit()
        return deleted

    def role_data_scopes(self, role_key: str) -> RoleDataScopeRead:
        if self.repository.get_role(role_key) is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        items = [
            DataScopeEntryRead(
                scope_type=row["scope_type"],
                scope_value=str(row["scope_value"]),
            )
            for row in self.repository.get_role_data_scopes(role_key)
        ]
        return RoleDataScopeRead(role_key=role_key, items=items)

    def update_role_data_scopes(
        self,
        *,
        actor: Principal,
        role_key: str,
        payload: RoleDataScopeUpdateRequest,
        audit: AuditContext,
    ) -> RoleDataScopeRead:
        before = self.role_data_scopes(role_key)
        if role_key == "admin" and not self._is_super_admin(actor):
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        scopes = tuple(
            (item.scope_type, item.scope_value.strip())
            for item in payload.items
            if item.scope_value.strip()
        )
        self._assert_actor_can_grant_scopes(actor, scopes)
        self.repository.set_role_data_scopes(role_key=role_key, scopes=scopes)
        after = RoleDataScopeRead(
            role_key=role_key,
            items=[
                DataScopeEntryRead(scope_type=scope_type, scope_value=scope_value)
                for scope_type, scope_value in scopes
            ],
        )
        self._audit(
            actor=actor,
            event_type="role.data-scopes.updated",
            target_type="role",
            target_key=role_key,
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return after

    def user_data_scopes(
        self,
        user_id: int,
        *,
        actor: Principal | None = None,
    ) -> UserDataScopeRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if actor is not None:
            self._assert_can_manage_target(actor, target, allow_self=True)
        user_rows = self.repository.get_user_data_scopes(user_id)
        role_rows = self.repository.get_user_role_data_scopes(user_id)
        items = [
            DataScopeEntryRead(
                scope_type=row["scope_type"],
                scope_value=str(row["scope_value"]),
            )
            for row in user_rows
        ]
        role_items = [
            DataScopeEntryRead(
                scope_type=row["scope_type"],
                scope_value=str(row["scope_value"]),
            )
            for row in role_rows
        ]
        user_types = {item.scope_type for item in items}
        effective_items = [
            EffectiveDataScopeEntryRead(
                scope_type=item.scope_type,
                scope_value=item.scope_value,
                source="user",
            )
            for item in items
        ] + [
            EffectiveDataScopeEntryRead(
                scope_type=item.scope_type,
                scope_value=item.scope_value,
                source="role",
            )
            for item in role_items
            if item.scope_type not in user_types
        ]
        return UserDataScopeRead(
            user_id=user_id,
            items=items,
            role_items=role_items,
            effective_items=effective_items,
        )

    def update_user_data_scopes(
        self,
        *,
        actor: Principal,
        user_id: int,
        payload: UserDataScopeUpdateRequest,
        audit: AuditContext,
    ) -> UserDataScopeRead:
        target = self.repository.get_user(user_id)
        if target is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        self._assert_can_manage_target(actor, target, allow_self=False)
        before = self.user_data_scopes(user_id)
        scopes = tuple(
            (item.scope_type, item.scope_value.strip())
            for item in payload.items
            if item.scope_value.strip()
        )
        self._assert_actor_can_grant_scopes(actor, scopes)
        self.repository.set_user_data_scopes(user_id=user_id, scopes=scopes)
        after = self.user_data_scopes(user_id)
        self._audit(
            actor=actor,
            event_type="user.data-scopes.updated",
            target_type="user",
            target_key=str(user_id),
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
            context=audit,
        )
        self.session.commit()
        return after

    def audit_events(self, *, limit: int) -> list[AuditEventRead]:
        return [
            AuditEventRead(
                id=str(row["id"]),
                actor_user_id=row.get("actor_user_id"),
                event_type=str(row["event_type"]),
                target_type=str(row["target_type"]),
                target_key=str(row["target_key"]),
                before=row.get("before_json"),
                after=row.get("after_json"),
                request_id=row.get("request_id"),
                request_ip=row.get("request_ip"),
                user_agent=row.get("user_agent"),
                created_at=row["created_at"],
            )
            for row in self.repository.list_audit_events(limit=limit)
        ]

    @staticmethod
    def _to_permission_item(row: dict[str, Any]) -> PermissionItemRead:
        return PermissionItemRead(
            permission_key=str(row["permission_key"]),
            name=str(row["name"]),
            description=row.get("description"),
            permission_type=row["permission_type"],
            module_key=str(row["module_key"]),
            page_key=str(row["page_key"]),
            action_key=row.get("action_key"),
            field_key=row.get("field_key"),
            risk_level=row["risk_level"],
            sort_order=int(row["sort_order"]),
        )

    def _validated_permission_keys(self, permission_keys: list[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in permission_keys if item.strip()))
        existing = self.repository.existing_permission_keys(normalized)
        invalid = sorted(set(normalized) - existing)
        if invalid:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                message="包含不存在或已停用的权限",
                details={"invalid_permission_keys": invalid},
            )
        return normalized

    def _validated_role_keys(self, role_keys: list[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in role_keys if item.strip()))
        if not normalized:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                message="用户至少需要一个角色",
            )
        existing = self.repository.existing_role_keys(normalized)
        invalid = sorted(set(normalized) - existing)
        if invalid:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                message="包含不存在的角色",
                details={"invalid_role_keys": invalid},
            )
        return normalized

    def _actor_permissions(self, actor: Principal) -> set[str]:
        if "*" in actor.permissions:
            return {"*"}
        return set(actor.permissions)

    def _is_super_admin(self, actor: Principal) -> bool:
        return "*" in actor.permissions

    def _assert_actor_can_grant(self, actor: Principal, permission_keys: tuple[str, ...]) -> None:
        if self._is_super_admin(actor):
            return
        actor_permissions = self._actor_permissions(actor)
        missing = sorted(set(permission_keys) - actor_permissions)
        high_risk = sorted(self.repository.high_risk_permission_keys(permission_keys))
        if missing or high_risk:
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                message="不能授予自己不具备的权限或高危权限",
                details={
                    "missing_permission_keys": missing,
                    "high_risk_permission_keys": high_risk,
                },
            )

    def _assert_actor_can_assign_roles(
        self,
        actor: Principal,
        role_keys: tuple[str, ...],
    ) -> None:
        if self._is_super_admin(actor):
            return
        if not self._role_assignment_is_within_actor_scope(actor, role_keys):
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                message="不能分配权限或数据范围高于当前账号的角色",
                details={"role_keys": sorted(role_keys)},
            )

    def _role_assignment_is_within_actor_scope(
        self,
        actor: Principal,
        role_keys: tuple[str, ...],
    ) -> bool:
        """Prevent permission and latent role-scope escalation in one decision."""

        if self._is_super_admin(actor):
            return True
        if "admin" in role_keys:
            return False
        requested_permissions = self.repository.permissions_for_roles(role_keys)
        if not requested_permissions.issubset(self._actor_permissions(actor)):
            return False
        if self.repository.high_risk_permission_keys(requested_permissions):
            return False
        try:
            actor_id = int(actor.user_id)
        except (TypeError, ValueError):
            return False

        requested_scopes = self.repository.data_scopes_for_roles(role_keys)
        if any(scope_value == "*" for _scope_type, scope_value in requested_scopes):
            return False
        by_type: dict[str, set[str]] = {}
        for scope_type, scope_value in requested_scopes:
            by_type.setdefault(scope_type, set()).add(scope_value)
        for scope_type, requested_values in by_type.items():
            actor_values = self.repository.resolve_user_data_scope(
                user_id=actor_id,
                scope_type=scope_type,
            )
            if "*" not in actor_values and not requested_values.issubset(actor_values):
                return False
        return True

    def _assert_actor_can_grant_scopes(
        self,
        actor: Principal,
        scopes: tuple[tuple[str, str], ...],
    ) -> None:
        requested_source_accounts = {
            scope_value
            for scope_type, scope_value in scopes
            if scope_type == "source_account" and scope_value != "*"
        }
        if requested_source_accounts:
            configured_source_accounts = self.repository.list_configured_source_account_refs()
            invalid_source_accounts = sorted(requested_source_accounts - configured_source_accounts)
            if invalid_source_accounts:
                raise ApiError(
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=422,
                    message="包含未在同步治理配置中登记的数据源账号",
                    details={"invalid_source_account_refs": invalid_source_accounts},
                )
        if self._is_super_admin(actor):
            return
        if any(scope_value == "*" for _scope_type, scope_value in scopes):
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                message="只有超级管理员可以授予全部数据范围",
            )
        try:
            actor_id = int(actor.user_id)
        except ValueError as exc:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403) from exc
        for scope_type, scope_value in scopes:
            actor_values = self.repository.resolve_user_data_scope(
                user_id=actor_id,
                scope_type=scope_type,
            )
            if "*" not in actor_values and scope_value not in actor_values:
                raise ApiError(
                    code=ErrorCode.FORBIDDEN,
                    status_code=403,
                    message="不能授予超出当前账号的数据范围",
                )

    def _assert_can_manage_target(
        self,
        actor: Principal,
        target: Any,
        *,
        allow_self: bool,
    ) -> None:
        actor_id = int(actor.user_id)
        target_id = int(target["id"])
        if actor_id == target_id and not allow_self:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=400,
                message="不能修改当前登录账号的角色",
            )
        if bool(target.get("is_super_admin")) and not self._is_super_admin(actor):
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                message="超级管理员账号受保护",
            )

    def _audit(
        self,
        *,
        actor: Principal,
        event_type: str,
        target_type: str,
        target_key: str,
        before: object | None,
        after: object | None,
        context: AuditContext,
    ) -> None:
        self.repository.append_audit_event(
            actor_user_id=int(actor.user_id),
            event_type=event_type,
            target_type=target_type,
            target_key=target_key,
            before=before,
            after=after,
            request_id=context.request_id,
            request_ip=context.request_ip,
            user_agent=context.user_agent,
        )
