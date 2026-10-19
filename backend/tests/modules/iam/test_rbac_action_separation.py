from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.iam.rbac_service import RbacService
from app.modules.iam.schemas import UserRead


def _user() -> UserRead:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return UserRead(
        id=41,
        username="synthetic-user",
        display_name="Synthetic User",
        phone=None,
        email=None,
        is_active=True,
        is_super_admin=False,
        role_keys=[],
        role_names=[],
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )


def _client(monkeypatch: pytest.MonkeyPatch, permission: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="7",
        permissions=frozenset({permission}),
    )
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    monkeypatch.setattr(RbacService, "update_user", lambda *_args, **_kwargs: _user())
    return TestClient(app)


def test_enable_disable_action_cannot_edit_profile_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(
        monkeypatch,
        "action:settings:user-management:enable-disable",
    ).patch("/api/settings/users/41", json={"display_name": "Changed"})

    assert response.status_code == 403


def test_edit_action_cannot_change_account_status(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(
        monkeypatch,
        "action:settings:user-management:edit",
    ).patch("/api/settings/users/41", json={"is_active": False})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("permission", "payload"),
    [
        ("action:settings:user-management:edit", {"display_name": "Changed"}),
        ("action:settings:user-management:enable-disable", {"is_active": False}),
    ],
)
def test_user_actions_allow_only_their_own_fields(
    monkeypatch: pytest.MonkeyPatch,
    permission: str,
    payload: dict[str, object],
) -> None:
    response = _client(monkeypatch, permission).patch(
        "/api/settings/users/41",
        json=payload,
    )

    assert response.status_code == 200
