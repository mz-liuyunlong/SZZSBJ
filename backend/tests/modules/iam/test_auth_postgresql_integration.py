from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_settings, get_test_database_url
from app.db import session as db_session
from app.main import create_app
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.iam.repository import IamRepository
from app.modules.iam.security import hash_password, token_hash

_USER_IDS = tuple(range(9_320_001, 9_320_007))
_ROLE_IDS = (
    "92300001-0000-4000-8000-000000000001",
    "92300002-0000-4000-8000-000000000002",
)
_PERMISSIONS = ("pr232:alpha", "pr232:beta")
_PASSWORD = "synthetic-password"
_TOKENS = {
    "no_role": "synthetic-pr232-no-role",
    "single": "synthetic-pr232-single",
    "multi": "synthetic-pr232-multi",
    "super": "synthetic-pr232-super",
    "disabled": "synthetic-pr232-disabled",
    "expired": "synthetic-pr232-expired",
    "revoked": "synthetic-pr232-revoked",
}


def _test_database_url() -> URL:
    if os.environ.get("IAM_AUTH_PERFORMANCE_DB_TESTS") != "1":
        pytest.skip("real IAM PostgreSQL tests require explicit opt-in")
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = get_test_database_url(settings)
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    if url.database == "szzsbj_app":
        pytest.fail("refusing to run IAM integration tests against the application database")
    return url


def _cleanup(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("delete from app_users where id = any(:user_ids)"),
            {"user_ids": list(_USER_IDS)},
        )
        connection.execute(
            text("delete from app_roles where id = any(cast(:role_ids as uuid[]))"),
            {"role_ids": list(_ROLE_IDS)},
        )
        connection.execute(
            text("delete from app_permissions where permission_key = any(:permission_keys)"),
            {"permission_keys": list(_PERMISSIONS)},
        )


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    engine = create_engine(
        _test_database_url(),
        poolclass=NullPool,
        hide_parameters=True,
    )
    _cleanup(engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        for permission_key in _PERMISSIONS:
            connection.execute(
                text(
                    """
                    insert into app_permissions (
                        permission_key, name, group_key, description, permission_type,
                        risk_level, sort_order, is_active, created_at, updated_at
                    ) values (
                        :permission_key, :permission_key, 'pr232', null, 'legacy',
                        'normal', 0, true, :now, :now
                    )
                    """
                ),
                {"permission_key": permission_key, "now": now},
            )
        for role_id, role_key, name in (
            (_ROLE_IDS[0], "pr232-alpha", "PR232 Alpha"),
            (_ROLE_IDS[1], "pr232-beta", "PR232 Beta"),
        ):
            connection.execute(
                text(
                    """
                    insert into app_roles (
                        id, role_key, name, description, is_system,
                        created_at, updated_at, version
                    ) values (
                        cast(:id as uuid), :role_key, :name, null, 0, :now, :now, 1
                    )
                    """
                ),
                {"id": role_id, "role_key": role_key, "name": name, "now": now},
            )
        for role_id, permission_key in (
            (_ROLE_IDS[0], _PERMISSIONS[0]),
            (_ROLE_IDS[1], _PERMISSIONS[0]),
            (_ROLE_IDS[1], _PERMISSIONS[1]),
        ):
            connection.execute(
                text(
                    """
                    insert into app_role_permissions (role_id, permission_key, created_at)
                    values (cast(:role_id as uuid), :permission_key, :now)
                    """
                ),
                {"role_id": role_id, "permission_key": permission_key, "now": now},
            )

        password_hash = hash_password(_PASSWORD)
        user_rows = (
            (_USER_IDS[0], "normal", 1, 0),
            (_USER_IDS[1], "no-role", 1, 0),
            (_USER_IDS[2], "single", 1, 0),
            (_USER_IDS[3], "multi", 1, 0),
            (_USER_IDS[4], "super", 1, 1),
            (_USER_IDS[5], "disabled", 0, 0),
        )
        for user_id, suffix, is_active, is_super_admin in user_rows:
            connection.execute(
                text(
                    """
                    insert into app_users (
                        id, username, password_hash, is_active, is_super_admin,
                        display_name, created_at, updated_at
                    ) values (
                        :id, :username, :password_hash, :is_active, :is_super_admin,
                        :display_name, :now, :now
                    )
                    """
                ),
                {
                    "id": user_id,
                    "username": f"pr232_{suffix}",
                    "password_hash": password_hash,
                    "is_active": is_active,
                    "is_super_admin": is_super_admin,
                    "display_name": f"PR232 {suffix}",
                    "now": now,
                },
            )
        for user_id, role_id in (
            (_USER_IDS[0], _ROLE_IDS[0]),
            (_USER_IDS[2], _ROLE_IDS[0]),
            (_USER_IDS[3], _ROLE_IDS[0]),
            (_USER_IDS[3], _ROLE_IDS[1]),
            (_USER_IDS[5], _ROLE_IDS[0]),
        ):
            connection.execute(
                text(
                    """
                    insert into app_user_roles (user_id, role_id, created_at)
                    values (:user_id, cast(:role_id as uuid), :now)
                    """
                ),
                {"user_id": user_id, "role_id": role_id, "now": now},
            )

        sessions = (
            (_TOKENS["no_role"], _USER_IDS[1], now + timedelta(hours=1), None),
            (_TOKENS["single"], _USER_IDS[2], now + timedelta(hours=1), None),
            (_TOKENS["multi"], _USER_IDS[3], now + timedelta(hours=1), None),
            (_TOKENS["super"], _USER_IDS[4], now + timedelta(hours=1), None),
            (_TOKENS["disabled"], _USER_IDS[5], now + timedelta(hours=1), None),
            (_TOKENS["expired"], _USER_IDS[2], now - timedelta(seconds=1), None),
            (_TOKENS["revoked"], _USER_IDS[2], now + timedelta(hours=1), now),
        )
        for index, (token, user_id, expires_at, revoked_at) in enumerate(sessions, start=1):
            connection.execute(
                text(
                    """
                    insert into app_sessions (
                        id, user_id, token_hash, created_at, expires_at, last_seen_at, revoked_at
                    ) values (
                        cast(:id as uuid), :user_id, :token_hash, :now,
                        :expires_at, :now, :revoked_at
                    )
                    """
                ),
                {
                    "id": f"92300100-0000-4000-8000-{index:012d}",
                    "user_id": user_id,
                    "token_hash": token_hash(token),
                    "now": now,
                    "expires_at": expires_at,
                    "revoked_at": revoked_at,
                },
            )
    try:
        yield engine
    finally:
        db_session.dispose_engine()
        get_settings.cache_clear()
        _cleanup(engine)
        engine.dispose()


def test_real_postgresql_session_and_role_semantics(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        repository = IamRepository(session)
        expected = {
            "no_role": [],
            "single": [_PERMISSIONS[0]],
            "multi": list(_PERMISSIONS),
            "super": ["*"],
        }
        for token_key, permission_keys in expected.items():
            row = repository.get_session_principal(token_hash(_TOKENS[token_key]))
            assert row is not None
            assert list(row["permission_keys"]) == permission_keys

        assert repository.get_session_principal(token_hash(_TOKENS["disabled"])) is None
        assert repository.get_session_principal(token_hash(_TOKENS["expired"])) is None
        assert repository.get_session_principal(token_hash(_TOKENS["revoked"])) is None

        no_role_user = repository.get_user_read_by_id(_USER_IDS[1])
        assert no_role_user is not None
        assert list(no_role_user["role_keys"]) == []

        multi_role_user = repository.get_user_read_by_id(_USER_IDS[3])
        assert multi_role_user is not None
        assert list(multi_role_user["role_keys"]) == ["pr232-alpha", "pr232-beta"]


def test_real_postgresql_source_account_scope_precedence(postgres_engine: Engine) -> None:
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into app_role_data_scopes (role_id, scope_type, scope_value, created_at)
                values
                    (cast(:alpha as uuid), 'source_account', 'role-account', :now),
                    (cast(:beta as uuid), 'source_account', 'role-account', :now)
                """
            ),
            {"alpha": _ROLE_IDS[0], "beta": _ROLE_IDS[1], "now": now},
        )

    with Session(postgres_engine) as session:
        repository = RbacRepository(session)
        assert repository.resolve_user_data_scope(
            user_id=_USER_IDS[3], scope_type="source_account"
        ) == {"role-account"}

    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into app_user_data_scopes (user_id, scope_type, scope_value, created_at)
                values (:user_id, 'source_account', 'user-account', :now)
                """
            ),
            {"user_id": _USER_IDS[3], "now": now},
        )

    with Session(postgres_engine) as session:
        repository = RbacRepository(session)
        assert repository.resolve_user_data_scope(
            user_id=_USER_IDS[3], scope_type="source_account"
        ) == {"user-account"}


class _SqlMetrics:
    def __init__(self) -> None:
        self.count = 0
        self.elapsed_seconds = 0.0

    def reset(self) -> None:
        self.count = 0
        self.elapsed_seconds = 0.0

    def before(
        self,
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        context.pr232_started_at = perf_counter()

    def after(
        self,
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        self.count += 1
        self.elapsed_seconds += perf_counter() - context.pr232_started_at


def test_real_postgresql_auth_me_semantics_and_benchmark(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url().render_as_string(hide_password=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    get_settings.cache_clear()
    db_session.dispose_engine()
    application_engine = db_session.get_engine()
    metrics = _SqlMetrics()
    event.listen(application_engine, "before_cursor_execute", metrics.before)
    event.listen(application_engine, "after_cursor_execute", metrics.after)

    try:
        with TestClient(create_app()) as client:
            login_started_at = perf_counter()
            login_response = client.post(
                "/api/auth/login",
                json={"username": "pr232_normal", "password": _PASSWORD},
            )
            login_elapsed = perf_counter() - login_started_at
            assert login_response.status_code == 200
            access_token = login_response.json()["data"]["access_token"]
            assert metrics.count == 4
            login_sql_elapsed = metrics.elapsed_seconds

            metrics.reset()
            me_started_at = perf_counter()
            me_response = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            me_elapsed = perf_counter() - me_started_at
            assert me_response.status_code == 200
            assert me_response.json()["data"]["permissions"] == [_PERMISSIONS[0]]
            assert metrics.count == 2
            me_sql_elapsed = metrics.elapsed_seconds

            with postgres_engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        delete from app_role_permissions
                        where role_id = cast(:role_id as uuid)
                          and permission_key = :permission_key
                        """
                    ),
                    {"role_id": _ROLE_IDS[0], "permission_key": _PERMISSIONS[0]},
                )
            revoked_permission_response = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert revoked_permission_response.status_code == 200
            assert revoked_permission_response.json()["data"]["permissions"] == []

            with postgres_engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        insert into app_role_permissions (role_id, permission_key, created_at)
                        values (cast(:role_id as uuid), :permission_key, now())
                        """
                    ),
                    {"role_id": _ROLE_IDS[0], "permission_key": _PERMISSIONS[0]},
                )
                connection.execute(
                    text(
                        """
                        delete from app_user_roles
                        where user_id = :user_id and role_id = cast(:role_id as uuid)
                        """
                    ),
                    {"user_id": _USER_IDS[0], "role_id": _ROLE_IDS[0]},
                )
            removed_role_response = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert removed_role_response.status_code == 200
            assert removed_role_response.json()["data"]["permissions"] == []

            for token_key in ("expired", "revoked", "disabled"):
                response = client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {_TOKENS[token_key]}"},
                )
                assert response.status_code == 401

        print(
            "IAM_REAL_POSTGRES_BENCHMARK "
            + json.dumps(
                {
                    "login_sql_count": 4,
                    "login_sql_ms": round(login_sql_elapsed * 1000, 3),
                    "login_request_ms": round(login_elapsed * 1000, 3),
                    "auth_me_sql_count": 2,
                    "auth_me_sql_ms": round(me_sql_elapsed * 1000, 3),
                    "auth_me_request_ms": round(me_elapsed * 1000, 3),
                },
                sort_keys=True,
            )
        )
    finally:
        event.remove(application_engine, "before_cursor_execute", metrics.before)
        event.remove(application_engine, "after_cursor_execute", metrics.after)
        db_session.dispose_engine()
        get_settings.cache_clear()
