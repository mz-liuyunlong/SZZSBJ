from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.auth import (
    WALMART_MONITOR_TARGETS_PRINCIPAL_ID,
    WALMART_MONITOR_TARGETS_READ_PERMISSION,
)
from app.core.config import Settings, SettingsError, get_settings
from app.main import create_app
from app.modules.walmart_monitor_targets.repository import (
    MonitorTargetRecord,
    WalmartMonitorTargetRepository,
)
from app.modules.walmart_monitor_targets.router import get_walmart_monitor_target_service
from app.modules.walmart_monitor_targets.schemas import MonitorTargetQuery
from app.modules.walmart_monitor_targets.service import WalmartMonitorTargetService

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
SYNTHETIC_TOKEN = "synthetic-target-token-value-000000000000"


@pytest.fixture(autouse=True)
def target_source_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", SYNTHETIC_DATABASE_URL)
    monkeypatch.setenv("WALMART_MONITOR_TARGETS_TOKEN", SYNTHETIC_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeRepository:
    def list_page(self, *, page: int, page_size: int):
        assert page == 2
        assert page_size == 1
        return (
            [
                MonitorTargetRecord(
                    source_account_ref="synthetic-account",
                    store_id="synthetic-store",
                    item_id="synthetic-item",
                    store_name="Synthetic Store",
                    sku="SYNTHETIC-SKU",
                    msku="SYNTHETIC-MSKU",
                    owner="synthetic-owner",
                    product_name="Synthetic product",
                    product_category="Synthetic > Category",
                    wfs_inventory=None,
                )
            ],
            2,
            datetime(2026, 1, 15, tzinfo=UTC),
        )


def _service() -> WalmartMonitorTargetService:
    return WalmartMonitorTargetService(MagicMock(spec=Session), repository=FakeRepository())


def test_service_maps_category_nullable_inventory_and_fixed_eligibility() -> None:
    data, meta = _service().list_targets(MonitorTargetQuery(page=2, page_size=1))

    assert data.total == 2
    assert data.items[0].product_category == "Synthetic > Category"
    assert data.items[0].wfs_inventory is None
    assert data.items[0].monitoring_eligible is True
    assert meta.source_tables == ["mart_listing_management_current", "listing_archive_states"]


def test_repository_excludes_archived_rows_from_count_and_page() -> None:
    session = MagicMock(spec=Session)
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = (1, datetime(2026, 1, 15, tzinfo=UTC))
    page_result = MagicMock()
    page_result.mappings.return_value.all.return_value = [
        {
            "source_account_ref": "synthetic-account",
            "store_id": "synthetic-store",
            "item_id": "synthetic-item",
            "store_name": None,
            "sku": None,
            "msku": None,
            "owner": None,
            "product_name": None,
            "product_category": None,
            "wfs_inventory": Decimal("5.0000"),
        }
    ]
    session.execute.side_effect = [aggregate_result, page_result]

    rows, total, _ = WalmartMonitorTargetRepository(session).list_page(page=2, page_size=10)

    assert total == 1
    assert rows[0].wfs_inventory == Decimal("5.0000")
    count_statement, page_statement = (call.args[0] for call in session.execute.call_args_list)
    count_sql = str(count_statement.compile(dialect=postgresql.dialect())).lower()
    sql = str(page_statement.compile(dialect=postgresql.dialect())).lower()
    for statement_sql in (count_sql, sql):
        assert "not (exists" in statement_sql
        assert (
            "listing_archive_states.listing_id = mart_listing_management_current.id"
            in statement_sql
        )
        assert "listing_archive_states.is_archived is true" in statement_sql
    assert "order by mart_listing_management_current.source_account_ref" in sql
    assert "mart_listing_management_current.store_id" in sql
    assert "mart_listing_management_current.item_id" in sql
    for forbidden in ("gross_profit", "gpt_analysis", "item_url", "picture_url"):
        assert forbidden not in sql


def test_target_route_requires_exact_machine_token_and_returns_unified_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_walmart_monitor_target_service] = _service
    with TestClient(app) as client:
        missing = client.get("/api/integrations/walmart-monitor/targets?page=2&page_size=1")
        wrong = client.get(
            "/api/integrations/walmart-monitor/targets?page=2&page_size=1",
            headers={"Authorization": "Bearer wrong-token"},
        )
        response = client.get(
            "/api/integrations/walmart-monitor/targets?page=2&page_size=1",
            headers={"Authorization": f"Bearer {SYNTHETIC_TOKEN}"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["items"][0]["wfs_inventory"] is None
    assert body["data"]["items"][0]["monitoring_eligible"] is True
    assert body["meta"]["source"] == "listing_management"
    assert body["request_id"]


def test_target_token_is_read_only_and_settings_fail_closed() -> None:
    settings = Settings(
        APP_ENV="test",
        TEST_DATABASE_URL=SYNTHETIC_DATABASE_URL,
        WALMART_MONITOR_TARGETS_TOKEN=SYNTHETIC_TOKEN,
    )
    assert settings.walmart_monitor_targets_configured is True
    assert settings.walmart_monitor_targets_token is not None
    assert SYNTHETIC_TOKEN not in repr(settings)
    with pytest.raises(SettingsError, match="target source settings are invalid"):
        Settings(
            APP_ENV="test",
            TEST_DATABASE_URL=SYNTHETIC_DATABASE_URL,
            WALMART_MONITOR_TARGETS_TOKEN="short",
        )


def test_machine_principal_contract_is_minimum_read_only_scope() -> None:
    assert WALMART_MONITOR_TARGETS_PRINCIPAL_ID == "walmart-monitor-targets-service"
    assert WALMART_MONITOR_TARGETS_READ_PERMISSION == "integrations:walmart-monitor:read"
