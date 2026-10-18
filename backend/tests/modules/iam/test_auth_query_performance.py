from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.auth import Principal
from app.modules.iam import service as iam_service
from app.modules.iam.repository import IamRepository
from app.modules.iam.service import IamService, resolve_principal_from_token


class _MappingResult:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self.row = row

    def one_or_none(self) -> Mapping[str, Any] | None:
        return self.row


class _Result:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> _MappingResult:
        return _MappingResult(self.row)


class _CountingSession:
    def __init__(self, *rows: Mapping[str, Any] | None) -> None:
        self.rows = list(rows)
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.closed = False

    def execute(
        self,
        statement: object,
        params: dict[str, object] | None = None,
    ) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(dict(params or {}))
        return _Result(self.rows.pop(0))

    def close(self) -> None:
        self.closed = True


def _user_row() -> dict[str, object]:
    now = datetime(2026, 10, 18, tzinfo=UTC)
    return {
        "id": 7,
        "username": "synthetic-user",
        "display_name": "Synthetic User",
        "phone": None,
        "email": None,
        "is_active": 1,
        "is_super_admin": 0,
        "role_keys": ["operator"],
        "role_names": ["Operator"],
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }


def test_session_principal_uses_one_query_and_keeps_session_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _CountingSession({"id": 7, "permission_keys": ["products:read"]})
    monkeypatch.setattr(iam_service, "get_session_factory", lambda: lambda: session)

    principal = resolve_principal_from_token("synthetic-session")

    assert principal == Principal(user_id="7", permissions=frozenset({"products:read"}))
    assert len(session.statements) == 1
    statement = session.statements[0]
    assert "s.revoked_at is null" in statement
    assert "s.expires_at > now()" in statement
    assert "u.is_active = 1" in statement
    assert "app_role_permissions" in statement
    assert session.closed is True


def test_invalid_session_fails_closed_after_one_query(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _CountingSession(None)
    monkeypatch.setattr(iam_service, "get_session_factory", lambda: lambda: session)

    assert resolve_principal_from_token("synthetic-invalid-session") is None
    assert len(session.statements) == 1


def test_current_user_uses_one_bounded_query_and_reuses_principal_permissions() -> None:
    session = _CountingSession(_user_row())
    principal = Principal(user_id="7", permissions=frozenset({"products:read"}))

    current_user = IamService(session).current_user(principal)  # type: ignore[arg-type]

    assert current_user.id == 7
    assert current_user.permissions == ["products:read"]
    assert len(session.statements) == 1
    assert "where u.id = :user_id" in session.statements[0]
    assert "order by u.is_active" not in session.statements[0]
    assert session.parameters == [{"user_id": 7}]


def test_user_directory_list_semantics_remain_separate_from_bounded_lookup() -> None:
    session = _CountingSession(_user_row())
    row = IamRepository(session).get_user_read_by_id(7)  # type: ignore[arg-type]

    assert row is not None
    assert row["id"] == 7
    assert len(session.statements) == 1
    assert "where u.id = :user_id" in session.statements[0]


def test_auth_me_query_budget_is_two_database_round_trips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_session = _CountingSession({"id": 7, "permission_keys": ["products:read"]})
    me_session = _CountingSession(_user_row())
    monkeypatch.setattr(iam_service, "get_session_factory", lambda: lambda: auth_session)

    principal = resolve_principal_from_token("synthetic-session")
    assert principal is not None
    current_user = IamService(me_session).current_user(principal)  # type: ignore[arg-type]

    assert current_user.id == 7
    assert len(auth_session.statements) + len(me_session.statements) == 2
    # The origin/main implementation executed 3 statements while resolving the
    # principal and another 3 for /auth/me. This assertion locks the optimized
    # request budget without adding a cross-request permission cache.
    assert (3 + 3) > (len(auth_session.statements) + len(me_session.statements))
