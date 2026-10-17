from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.iam.security import now_utc


class RbacRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_permission_catalog_rows(self) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select
                        permission_key,
                        name,
                        description,
                        permission_type,
                        module_key,
                        page_key,
                        action_key,
                        field_key,
                        risk_level,
                        sort_order
                    from app_permissions
                    where is_active = true
                      and permission_type in ('page', 'action', 'field')
                    order by module_key, page_key, permission_type, sort_order, permission_key
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
                        r.version,
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

    def get_role(self, role_key: str) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    select
                        r.id::text as id,
                        r.role_key,
                        r.name,
                        r.description,
                        r.is_system,
                        r.version,
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
                    where r.role_key = :role_key
                    group by r.id
                    """
                ),
                {"role_key": role_key},
            )
            .mappings()
            .one_or_none()
        )

    def get_user(self, user_id: int) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    select id, username, display_name, is_active, is_super_admin
                    from app_users
                    where id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            .mappings()
            .one_or_none()
        )

    def user_role_keys(self, user_id: int) -> tuple[str, ...]:
        rows = self.session.execute(
            text(
                """
                select r.role_key
                from app_user_roles ur
                join app_roles r on r.id = ur.role_id
                where ur.user_id = :user_id
                order by r.role_key
                """
            ),
            {"user_id": user_id},
        ).scalars()
        return tuple(str(item) for item in rows)

    def role_permission_keys(self, role_key: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select rp.permission_key
                from app_roles r
                join app_role_permissions rp on rp.role_id = r.id
                where r.role_key = :role_key
                """
            ),
            {"role_key": role_key},
        ).scalars()
        return {str(item) for item in rows}

    def permissions_for_roles(self, role_keys: Iterable[str]) -> set[str]:
        values = tuple(dict.fromkeys(role_keys))
        if not values:
            return set()
        rows = self.session.execute(
            text(
                """
                select distinct rp.permission_key
                from app_roles r
                join app_role_permissions rp on rp.role_id = r.id
                where r.role_key = any(:role_keys)
                """
            ),
            {"role_keys": list(values)},
        ).scalars()
        return {str(item) for item in rows}

    def data_scopes_for_roles(self, role_keys: Iterable[str]) -> set[tuple[str, str]]:
        values = tuple(dict.fromkeys(role_keys))
        if not values:
            return set()
        rows = self.session.execute(
            text(
                """
                select distinct s.scope_type, s.scope_value
                from app_roles r
                join app_role_data_scopes s on s.role_id = r.id
                where r.role_key = any(:role_keys)
                """
            ),
            {"role_keys": list(values)},
        ).all()
        return {(str(scope_type), str(scope_value)) for scope_type, scope_value in rows}

    def existing_permission_keys(self, permission_keys: Iterable[str]) -> set[str]:
        values = tuple(dict.fromkeys(permission_keys))
        if not values:
            return set()
        rows = self.session.execute(
            text(
                """
                select permission_key
                from app_permissions
                where permission_key = any(:permission_keys)
                  and is_active = true
                """
            ),
            {"permission_keys": list(values)},
        ).scalars()
        return {str(item) for item in rows}

    def high_risk_permission_keys(self, permission_keys: Iterable[str]) -> set[str]:
        values = tuple(dict.fromkeys(permission_keys))
        if not values:
            return set()
        rows = self.session.execute(
            text(
                """
                select permission_key
                from app_permissions
                where permission_key = any(:permission_keys)
                  and risk_level = 'high'
                  and is_active = true
                """
            ),
            {"permission_keys": list(values)},
        ).scalars()
        return {str(item) for item in rows}

    def existing_role_keys(self, role_keys: Iterable[str]) -> set[str]:
        values = tuple(dict.fromkeys(role_keys))
        if not values:
            return set()
        rows = self.session.execute(
            text(
                """
                select role_key
                from app_roles
                where role_key = any(:role_keys)
                """
            ),
            {"role_keys": list(values)},
        ).scalars()
        return {str(item) for item in rows}

    def set_role_permissions(
        self,
        *,
        role_key: str,
        permission_keys: Iterable[str],
        expected_version: int,
        name: str | None = None,
        description: str | None = None,
    ) -> bool:
        updated = self.session.execute(
            text(
                """
                update app_roles
                set
                    name = coalesce(:name, name),
                    description = coalesce(:description, description),
                    version = version + 1,
                    updated_at = :now
                where role_key = :role_key
                  and version = :expected_version
                returning id
                """
            ),
            {
                "role_key": role_key,
                "expected_version": expected_version,
                "name": name,
                "description": description,
                "now": now_utc(),
            },
        ).one_or_none()
        if updated is None:
            return False
        self.session.execute(
            text(
                """
                delete from app_role_permissions
                where role_id = (select id from app_roles where role_key = :role_key)
                """
            ),
            {"role_key": role_key},
        )
        for permission_key in dict.fromkeys(permission_keys):
            self.session.execute(
                text(
                    """
                    insert into app_role_permissions (role_id, permission_key, created_at)
                    select r.id, :permission_key, :now
                    from app_roles r
                    where r.role_key = :role_key
                    """
                ),
                {
                    "role_key": role_key,
                    "permission_key": permission_key,
                    "now": now_utc(),
                },
            )
        return True

    def set_user_roles(self, *, user_id: int, role_keys: Iterable[str]) -> None:
        self.session.execute(
            text("delete from app_user_roles where user_id = :user_id"),
            {"user_id": user_id},
        )
        for role_key in dict.fromkeys(role_keys):
            self.session.execute(
                text(
                    """
                    insert into app_user_roles (user_id, role_id, created_at)
                    select :user_id, id, :now
                    from app_roles
                    where role_key = :role_key
                    """
                ),
                {"user_id": user_id, "role_key": role_key, "now": now_utc()},
            )

    def list_role_options(self) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select role_key, name, description, is_system
                    from app_roles
                    order by is_system desc, name
                    """
                )
            ).mappings()
        )

    def get_role_data_scopes(self, role_key: str) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select scope_type, scope_value
                    from app_role_data_scopes s
                    join app_roles r on r.id = s.role_id
                    where r.role_key = :role_key
                    order by scope_type, scope_value
                    """
                ),
                {"role_key": role_key},
            ).mappings()
        )

    def set_role_data_scopes(
        self,
        *,
        role_key: str,
        scopes: Iterable[tuple[str, str]],
    ) -> None:
        self.session.execute(
            text(
                """
                delete from app_role_data_scopes
                where role_id = (select id from app_roles where role_key = :role_key)
                """
            ),
            {"role_key": role_key},
        )
        for scope_type, scope_value in dict.fromkeys(scopes):
            self.session.execute(
                text(
                    """
                    insert into app_role_data_scopes (
                        role_id, scope_type, scope_value, created_at
                    )
                    select id, :scope_type, :scope_value, :now
                    from app_roles
                    where role_key = :role_key
                    """
                ),
                {
                    "role_key": role_key,
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "now": now_utc(),
                },
            )

    def get_user_data_scopes(self, user_id: int) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select scope_type, scope_value
                    from app_user_data_scopes
                    where user_id = :user_id
                    order by scope_type, scope_value
                    """
                ),
                {"user_id": user_id},
            ).mappings()
        )

    def get_user_role_data_scopes(self, user_id: int) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select distinct s.scope_type, s.scope_value
                    from app_user_roles ur
                    join app_role_data_scopes s on s.role_id = ur.role_id
                    where ur.user_id = :user_id
                    order by s.scope_type, s.scope_value
                    """
                ),
                {"user_id": user_id},
            ).mappings()
        )

    def set_user_data_scopes(
        self,
        *,
        user_id: int,
        scopes: Iterable[tuple[str, str]],
    ) -> None:
        self.session.execute(
            text("delete from app_user_data_scopes where user_id = :user_id"),
            {"user_id": user_id},
        )
        for scope_type, scope_value in dict.fromkeys(scopes):
            self.session.execute(
                text(
                    """
                    insert into app_user_data_scopes (
                        user_id, scope_type, scope_value, created_at
                    )
                    values (:user_id, :scope_type, :scope_value, :now)
                    """
                ),
                {
                    "user_id": user_id,
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "now": now_utc(),
                },
            )

    def resolve_user_data_scope(self, *, user_id: int, scope_type: str) -> set[str]:
        user_values = {
            str(item)
            for item in self.session.execute(
                text(
                    """
                    select scope_value
                    from app_user_data_scopes
                    where user_id = :user_id
                      and scope_type = :scope_type
                    """
                ),
                {"user_id": user_id, "scope_type": scope_type},
            ).scalars()
        }
        if user_values:
            return user_values
        role_values = self.session.execute(
            text(
                """
                select distinct s.scope_value
                from app_user_roles ur
                join app_role_data_scopes s on s.role_id = ur.role_id
                where ur.user_id = :user_id
                  and s.scope_type = :scope_type
                """
            ),
            {"user_id": user_id, "scope_type": scope_type},
        ).scalars()
        return {str(item) for item in role_values}

    def list_configured_source_account_refs(self) -> set[str]:
        """Return source-account values registered by sync governance."""
        values = self.session.execute(
            text(
                """
                select distinct source_account_ref
                from gov_integration_sync_configs
                where source_account_ref <> ''
                """
            )
        ).scalars()
        return {str(item).strip() for item in values if str(item).strip()}

    def append_audit_event(
        self,
        *,
        actor_user_id: int | None,
        event_type: str,
        target_type: str,
        target_key: str,
        before: object | None,
        after: object | None,
        request_id: str | None,
        request_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self.session.execute(
            text(
                """
                insert into iam_audit_events (
                    id,
                    actor_user_id,
                    event_type,
                    target_type,
                    target_key,
                    before_json,
                    after_json,
                    request_id,
                    request_ip,
                    user_agent,
                    created_at
                )
                values (
                    :id,
                    :actor_user_id,
                    :event_type,
                    :target_type,
                    :target_key,
                    cast(:before_json as jsonb),
                    cast(:after_json as jsonb),
                    :request_id,
                    :request_ip,
                    :user_agent,
                    :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "actor_user_id": actor_user_id,
                "event_type": event_type,
                "target_type": target_type,
                "target_key": target_key,
                "before_json": None if before is None else json.dumps(before, default=str),
                "after_json": None if after is None else json.dumps(after, default=str),
                "request_id": request_id,
                "request_ip": request_ip,
                "user_agent": user_agent,
                "created_at": now_utc(),
            },
        )

    def list_audit_events(self, *, limit: int) -> list[Mapping[str, Any]]:
        return list(
            self.session.execute(
                text(
                    """
                    select
                        id::text as id,
                        actor_user_id,
                        event_type,
                        target_type,
                        target_key,
                        before_json,
                        after_json,
                        request_id,
                        request_ip,
                        user_agent,
                        created_at
                    from iam_audit_events
                    order by created_at desc
                    limit :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
        )
