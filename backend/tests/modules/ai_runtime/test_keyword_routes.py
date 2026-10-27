"""Idempotent keyword task requests must not disclose other users' jobs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.modules.ai_runtime import keyword_routes


def test_idempotency_replay_requires_same_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyword_routes, "has_permission", lambda *_: False)
    with pytest.raises(ApiError):
        keyword_routes._assert_job_owner("owner-a", SimpleNamespace(user_id="owner-b"))


def test_idempotency_replay_allows_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyword_routes, "has_permission", lambda *_: False)
    keyword_routes._assert_job_owner("owner-a", SimpleNamespace(user_id="owner-a"))


def test_idempotency_replay_allows_authorized_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyword_routes, "has_permission", lambda *_: True)
    keyword_routes._assert_job_owner("owner-a", SimpleNamespace(user_id="manager"))
