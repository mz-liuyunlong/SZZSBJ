from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.warehouse_wfs.legacy_identity import (
    LEGACY_IDENTITY_CTE,
    LEGACY_IDENTITY_PREFLIGHT_SQL,
)
from app.modules.warehouse_wfs.schemas import WfsFeeCaseWrite
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def test_account_resolution_refuses_ambiguous_store_identity() -> None:
    assert "count(distinct a.source_account_ref)" in LEGACY_IDENTITY_CTE
    assert "l.matched_accounts = 1" in LEGACY_IDENTITY_CTE
    assert "dim_walmart_listings" in LEGACY_IDENTITY_CTE
    assert "mart_daily_sales_item_day" in LEGACY_IDENTITY_CTE
    assert "ambiguous_identities" in LEGACY_IDENTITY_PREFLIGHT_SQL
    assert "duplicate_identities" in LEGACY_IDENTITY_PREFLIGHT_SQL


def test_upsert_does_not_override_manually_edited_case() -> None:
    query = WfsFeeAlertService(MagicMock(spec=Session))._legacy_upsert_sql()
    assert "ops_wfs_fee_anomaly_cases.updated_by = 'legacy_mirror'" in query
    assert "ops_wfs_fee_anomaly_cases.legacy_case_id = excluded.legacy_case_id" in query
    assert "on conflict (source_account_ref, store_id, item_id, msku)" in query


def test_legacy_follow_cannot_mark_recovered_or_archived(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    service = WfsFeeAlertService(session)
    monkeypatch.setattr(service, "_assert_case_visible", lambda *_args: None)
    for status in ("已追回", "已关闭", "驳回"):
        with pytest.raises(ApiError) as raised:
            service.update_case(
                UUID("00000000-0000-0000-0000-000000000001"),
                WfsFeeCaseWrite(status=status),
                frozenset({"account-1"}),
                "user-1",
            )
        assert raised.value.status_code == 422
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_high_risk_routes_require_distinct_permissions() -> None:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"warehouse:wfs-fee-alert:write"}),
    )
    app.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({"account-1"})
    )
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    client = TestClient(app)
    case_id = "00000000-0000-0000-0000-000000000001"
    assert client.post("/api/warehouse/wfs-fee-cases/sync-legacy-execute").status_code == 403
    assert client.post("/api/warehouse/wfs-fee-cases/sync-legacy-preview").status_code == 403
    assert client.get("/api/warehouse/wfs-fee-cases/legacy-compare").status_code == 403
    assert client.post(
        f"/api/warehouse/wfs-fee-cases/{case_id}/archive-review",
        json={"decision": "approved"},
    ).status_code == 403
    assert client.post(
        f"/api/warehouse/wfs-fee-cases/{case_id}/mark-recovered",
        json={"recovered_amount": "1.00"},
    ).status_code == 403


def test_migration_registers_action_permissions() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "20261015_0036_formalize_wfs_fee_cases.py"
    ).read_text()
    for suffix in ("write", "review", "recover", "sync"):
        assert f"warehouse:wfs-fee-alert:{suffix}" in migration
