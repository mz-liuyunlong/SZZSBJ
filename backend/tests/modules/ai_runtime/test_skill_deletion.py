"""Skill remove semantics do not delete immutable job-pinned revisions."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.ai_runtime import general_routes as routes


class _FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _FakeSession:
    def __init__(self, row):
        self.row = row
        self.statements = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        if sql.lstrip().startswith("SELECT id, status FROM ai_runtime_skill_versions"):
            return _FakeResult(self.row)
        assert sql.lstrip().startswith("UPDATE ai_runtime_skill_versions")
        assert "deleted_at=now()" in sql
        assert "'retired'" in sql
        return _FakeResult(None)

    def commit(self):
        self.committed = True


def _request():
    return Request(
        {"type": "http", "method": "DELETE", "path": "/api/ai-runtime/skills/test", "headers": []}
    )


def test_delete_skill_is_soft_and_historical_jobs_can_keep_version(monkeypatch):
    fake = _FakeSession({"id": uuid4(), "status": "published"})
    monkeypatch.setattr(routes, "get_session_factory", lambda: lambda: fake)
    result = routes.delete_skill(
        fake.row["id"],
        _request(),
        Principal(user_id="synthetic-superadmin", permissions=frozenset({"*"})),
    )
    assert result.data == {"ok": True}
    assert fake.committed
    assert len(fake.statements) == 2
    assert "DELETE FROM" not in fake.statements[1].upper()


def test_delete_missing_skill_is_not_found(monkeypatch):
    fake = _FakeSession(None)
    monkeypatch.setattr(routes, "get_session_factory", lambda: lambda: fake)
    with pytest.raises(ApiError) as err:
        routes.delete_skill(
            uuid4(),
            _request(),
            Principal(user_id="synthetic-superadmin", permissions=frozenset({"*"})),
        )
    assert err.value.status_code == 404
    assert not fake.committed
