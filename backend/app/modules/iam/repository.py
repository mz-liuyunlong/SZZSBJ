from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.iam.security import now_utc


class IamRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_username(self, username: str) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                select
                    id, username, password_hash, is_active,
                    display_name, phone, email,
                    feishu_name, feishu_open_id, feishu_user_id, feishu_union_id,
                    feishu_employee_id, feishu_department_ids, feishu_last_synced_at,
                    is_super_admin,
                    created_at, updated_at, last_login_at
                from app_users
                where username = :username
                """
                ),
                {"username": username},
            )
            .mappings()
            .one_or_none()
        )

    def get_user_by_id(self, user_id: int) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                select
                    id, username, password_hash, is_active,
                    display_name, phone, email,
                    feishu_name, feishu_open_id, feishu_user_id, feishu_union_id,
                    feishu_employee_id, feishu_department_ids, feishu_last_synced_at,
                    is_super_admin,
                    created_at, updated_at, last_login_at
                from app_users
                where id = :user_id
                """
                ),
                {"user_id": user_id},
            )
            .mappings()
            .one_or_none()
        )

    def get_user_by_feishu_open_id(self, feishu_open_id: str) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    select id, username, feishu_open_id
                    from app_users
                    where feishu_open_id = :feishu_open_id
                    """
                ),
                {"feishu_open_id": feishu_open_id},
            )
            .mappings()
            .one_or_none()
        )

    def list_users(self) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select
                        u.id,
                        u.username,
                        u.display_name,
                        u.phone,
                        u.email,
                        u.feishu_name,
                        u.feishu_open_id,
                        u.feishu_user_id,
                        u.feishu_union_id,
                        u.feishu_employee_id,
                        u.feishu_department_ids,
                        u.feishu_last_synced_at,
                        u.is_active,
                        u.is_super_admin,
                        u.created_at,
                        u.updated_at,
                        u.last_login_at,
                        coalesce(
                            array_remove(array_agg(r.role_key order by r.name), null),
                            '{}'::varchar[]
                        ) as role_keys,
                        coalesce(
                            array_remove(array_agg(r.name order by r.name), null),
                            '{}'::varchar[]
                        ) as role_names
                    from app_users u
                    left join app_user_roles ur on ur.user_id = u.id
                    left join app_roles r on r.id = ur.role_id
                    group by u.id
                    order by u.is_active desc, u.id
                    """
                )
            ).mappings()
        )

    def list_roles(self) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select
                        r.id::text as id,
                        r.role_key,
                        r.name,
                        r.description,
                        r.is_system,
                        count(distinct ur.user_id)::int as user_count,
                        coalesce(
                            array_remove(
                                array_agg(rp.permission_key order by rp.permission_key),
                                null
                            ),
                            '{}'::varchar[]
                        ) as permission_keys
                    from app_roles r
                    left join app_user_roles ur on ur.role_id = r.id
                    left join app_role_permissions rp on rp.role_id = r.id
                    group by r.id
                    order by r.is_system desc, r.name
                    """
                )
            ).mappings()
        )

    def list_permissions(self) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select permission_key, name, group_key, description
                    from app_permissions
                    order by group_key, permission_key
                    """
                )
            ).mappings()
        )

    def user_permission_keys(self, user_id: int) -> set[str]:
        user = self.get_user_by_id(user_id)
        if user is None or int(user["is_active"]) != 1:
            return set()
        if int(user.get("is_super_admin") or 0) == 1:
            return {"*"}
        rows = (
            self.session.execute(
                text(
                    """
                select distinct rp.permission_key
                from app_user_roles ur
                join app_role_permissions rp on rp.role_id = ur.role_id
                where ur.user_id = :user_id
                """
                ),
                {"user_id": user_id},
            )
            .scalars()
            .all()
        )
        return {str(row) for row in rows}

    def create_session(self, *, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.session.execute(
            text(
                """
                insert into app_sessions
                    (id, user_id, token_hash, created_at, expires_at, last_seen_at)
                values
                    (:id, :user_id, :token_hash, :created_at, :expires_at, :last_seen_at)
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "token_hash": token_hash,
                "created_at": now_utc(),
                "expires_at": expires_at,
                "last_seen_at": now_utc(),
            },
        )

    def get_session_user(self, token_hash: str) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                select u.id
                from app_sessions s
                join app_users u on u.id = s.user_id
                where s.token_hash = :token_hash
                  and s.revoked_at is null
                  and s.expires_at > now()
                  and u.is_active = 1
                """
                ),
                {"token_hash": token_hash},
            )
            .mappings()
            .one_or_none()
        )

    def revoke_user_sessions(self, user_id: int) -> None:
        self.session.execute(
            text(
                """
                update app_sessions
                set revoked_at = :now
                where user_id = :user_id
                  and revoked_at is null
                """
            ),
            {"user_id": user_id, "now": now_utc()},
        )

    def revoke_user_password_setup_tokens(self, user_id: int) -> None:
        self.session.execute(
            text(
                """
                update iam_password_reset_tokens
                set is_revoked = true
                where user_id = :user_id
                  and used_at is null
                  and is_revoked = false
                """
            ),
            {"user_id": user_id},
        )

    def revoke_session(self, token_hash: str) -> None:
        self.session.execute(
            text(
                """
                update app_sessions
                set revoked_at = :revoked_at
                where token_hash = :token_hash
                  and revoked_at is null
                """
            ),
            {"token_hash": token_hash, "revoked_at": now_utc()},
        )

    def touch_last_login(self, user_id: int) -> None:
        self.session.execute(
            text(
                """
                update app_users
                set last_login_at = :now, updated_at = :now
                where id = :user_id
                """
            ),
            {"user_id": user_id, "now": now_utc()},
        )

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str | None,
        phone: str | None,
        email: str | None,
        feishu_name: str | None,
        feishu_open_id: str | None,
        feishu_user_id: str | None,
        feishu_union_id: str | None,
        feishu_employee_id: str | None,
        feishu_department_ids: str | None,
        is_active: bool = True,
    ) -> int:
        row = self.session.execute(
            text(
                """
                insert into app_users
                    (
                        username, password_hash, display_name, phone, email,
                        feishu_name, feishu_open_id, feishu_user_id, feishu_union_id,
                        feishu_employee_id, feishu_department_ids, feishu_last_synced_at,
                        is_active, is_super_admin, password_updated_at, created_at, updated_at
                    )
                values
                    (
                        :username, :password_hash, :display_name, :phone, :email,
                        :feishu_name, :feishu_open_id, :feishu_user_id, :feishu_union_id,
                        :feishu_employee_id, :feishu_department_ids, :feishu_last_synced_at,
                        :is_active, 0, :now, :now, :now
                    )
                returning id
                """
            ),
            {
                "username": username,
                "password_hash": password_hash,
                "display_name": display_name,
                "phone": phone,
                "email": email,
                "feishu_name": feishu_name,
                "feishu_open_id": feishu_open_id,
                "feishu_user_id": feishu_user_id,
                "feishu_union_id": feishu_union_id,
                "feishu_employee_id": feishu_employee_id,
                "feishu_department_ids": feishu_department_ids,
                "feishu_last_synced_at": now_utc() if feishu_open_id else None,
                "is_active": 1 if is_active else 0,
                "now": now_utc(),
            },
        ).one()
        return int(row[0])

    def update_user(
        self,
        *,
        user_id: int,
        display_name: str | None,
        phone: str | None,
        email: str | None,
        feishu_name: str | None,
        feishu_open_id: str | None,
        feishu_user_id: str | None,
        feishu_union_id: str | None,
        feishu_employee_id: str | None,
        feishu_department_ids: str | None,
        is_active: bool | None,
    ) -> None:
        self.session.execute(
            text(
                """
                update app_users
                set
                    display_name = coalesce(:display_name, display_name),
                    phone = coalesce(:phone, phone),
                    email = coalesce(:email, email),
                    feishu_name = coalesce(:feishu_name, feishu_name),
                    feishu_open_id = coalesce(:feishu_open_id, feishu_open_id),
                    feishu_user_id = coalesce(:feishu_user_id, feishu_user_id),
                    feishu_union_id = coalesce(:feishu_union_id, feishu_union_id),
                    feishu_employee_id = coalesce(:feishu_employee_id, feishu_employee_id),
                    feishu_department_ids = coalesce(:feishu_department_ids, feishu_department_ids),
                    feishu_last_synced_at = case
                        when :feishu_open_id is not null then :now
                        else feishu_last_synced_at
                    end,
                    is_active = coalesce(:is_active, is_active),
                    updated_at = :now
                where id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "display_name": display_name,
                "phone": phone,
                "email": email,
                "feishu_name": feishu_name,
                "feishu_open_id": feishu_open_id,
                "feishu_user_id": feishu_user_id,
                "feishu_union_id": feishu_union_id,
                "feishu_employee_id": feishu_employee_id,
                "feishu_department_ids": feishu_department_ids,
                "is_active": None if is_active is None else (1 if is_active else 0),
                "now": now_utc(),
            },
        )

    def reset_password(self, *, user_id: int, password_hash: str) -> None:
        self.session.execute(
            text(
                """
                update app_users
                set password_hash = :password_hash,
                    password_updated_at = :now,
                    updated_at = :now
                where id = :user_id
                """
            ),
            {"user_id": user_id, "password_hash": password_hash, "now": now_utc()},
        )

    def set_user_roles(self, *, user_id: int, role_keys: Iterable[str]) -> None:
        self.session.execute(
            text("delete from app_user_roles where user_id = :user_id"), {"user_id": user_id}
        )
        for role_key in role_keys:
            self.session.execute(
                text(
                    """
                    insert into app_user_roles (user_id, role_id, created_at)
                    select :user_id, id, :now
                    from app_roles
                    where role_key = :role_key
                    on conflict do nothing
                    """
                ),
                {"user_id": user_id, "role_key": role_key, "now": now_utc()},
            )

    def create_role(
        self,
        *,
        role_key: str,
        name: str,
        description: str | None,
    ) -> str:
        role_id = str(uuid4())
        self.session.execute(
            text(
                """
                insert into app_roles
                    (id, role_key, name, description, is_system, created_at, updated_at)
                values
                    (:id, :role_key, :name, :description, 0, :now, :now)
                """
            ),
            {
                "id": role_id,
                "role_key": role_key,
                "name": name,
                "description": description,
                "now": now_utc(),
            },
        )
        return role_id

    def update_role(
        self,
        *,
        role_key: str,
        name: str | None,
        description: str | None,
    ) -> None:
        self.session.execute(
            text(
                """
                update app_roles
                set
                    name = coalesce(:name, name),
                    description = coalesce(:description, description),
                    updated_at = :now
                where role_key = :role_key
                """
            ),
            {
                "role_key": role_key,
                "name": name,
                "description": description,
                "now": now_utc(),
            },
        )

    def set_role_permissions(self, *, role_key: str, permission_keys: Iterable[str]) -> None:
        self.session.execute(
            text(
                """
                delete from app_role_permissions
                where role_id = (select id from app_roles where role_key = :role_key)
                """
            ),
            {"role_key": role_key},
        )
        for permission_key in permission_keys:
            self.session.execute(
                text(
                    """
                    insert into app_role_permissions (role_id, permission_key, created_at)
                    select r.id, p.permission_key, :now
                    from app_roles r
                    join app_permissions p on p.permission_key = :permission_key
                    where r.role_key = :role_key
                    on conflict do nothing
                    """
                ),
                {"role_key": role_key, "permission_key": permission_key, "now": now_utc()},
            )
