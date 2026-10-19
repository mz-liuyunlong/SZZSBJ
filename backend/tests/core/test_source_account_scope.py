from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.integration_sync.repository import IntegrationSyncRepository


def test_real_user_scope_uses_governance_universe_not_preview_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    monkeypatch.setattr(
        IntegrationSyncRepository,
        "list_configured_source_account_refs",
        lambda _repository: frozenset({"account-a", "account-b"}),
    )
    monkeypatch.setattr(
        RbacRepository,
        "resolve_user_data_scope",
        lambda _repository, **_kwargs: {"account-a", "outside-universe"},
    )

    resolved = require_source_account_scope(
        Principal(user_id="41", permissions=frozenset({"page:synthetic:view"})),
        None,
        session,
    )

    assert resolved == frozenset({"account-a"})


def test_real_super_admin_is_limited_to_governance_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    monkeypatch.setattr(
        IntegrationSyncRepository,
        "list_configured_source_account_refs",
        lambda _repository: frozenset({"account-a"}),
    )

    resolved = require_source_account_scope(
        Principal(user_id="1", permissions=frozenset({"*"})),
        None,
        session,
    )

    assert resolved == frozenset({"account-a"})


def test_non_numeric_non_preview_principal_cannot_inherit_registry_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    monkeypatch.setattr(
        IntegrationSyncRepository,
        "list_configured_source_account_refs",
        lambda _repository: frozenset({"account-a"}),
    )

    with pytest.raises(ApiError) as exc_info:
        require_source_account_scope(
            Principal(user_id="synthetic-user", permissions=frozenset({"*"})),
            None,
            session,
        )

    assert getattr(exc_info.value, "status_code", None) == 403
