from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.data_pages.repository import (
    ListingManagementRepository,
    ListingManagementRowProjection,
)
from app.modules.data_pages.service import ListingManagementService
from app.modules.walmart_monitor.models import RawWalmartMonitorEvent
from app.modules.walmart_monitor.projection import (
    WalmartMonitorProjectionService,
    parse_monitor_listing_values,
)
from app.modules.walmart_monitor.schemas import MonitorTarget

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _target() -> MonitorTarget:
    return MonitorTarget(
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        product_category="Internal > Source Category",
        monitoring_eligible=True,
    )


def _raw_event(*, target_count: int = 1, outcome: str = "SUCCESS") -> RawWalmartMonitorEvent:
    targets = [
        {
            "source_account_ref": f"synthetic-account-{index}",
            "store_id": f"synthetic-store-{index}",
            "item_id": "synthetic-item",
            "product_category": f"Source Category {index}",
            "monitoring_eligible": True,
        }
        for index in range(target_count)
    ]
    return RawWalmartMonitorEvent(
        id=uuid4(),
        payload_json={
            "schema_version": "walmart-monitor.raw.v1",
            "event_id": "walmart-monitor:synthetic:check:1",
            "captured_at": "2026-01-15T01:02:03+00:00",
            "requested_provider": "SYNTHETIC",
            "producer": {"instance_id": "synthetic", "check_id": "1"},
            "targets": targets,
            "attempts": [
                {
                    "attempt_no": 1,
                    "provider": "SYNTHETIC",
                    "outcome": outcome,
                    "source_payloads": [],
                }
            ],
            "final_observation": {
                "outcome": outcome,
                "data_source": "SYNTHETIC",
                "error_code": None if outcome == "SUCCESS" else "SYNTHETIC_FAILURE",
                "duration_ms": 1,
                "parsed_result": {"productTitle": "Observed title"},
            },
        },
    )


def test_parser_maps_monitor_fields_without_inferring_hijack() -> None:
    values = parse_monitor_listing_values(
        {
            "productTitle": " Monitored title ",
            "strikethroughPriceCents": 4599,
            "currentPrice": "39.99",
            "currency": "usd",
            "cartStatus": "PRIMARY",
            "sellerName": "Owned seller",
            "otherSellersPresent": True,
            "ratingSummary": {"rating": "4.6", "reviewCount": 27},
            "productBrand": "Synthetic Brand",
            "walmartCategory": {"path": [{"name": "Home"}, {"name": "Storage"}]},
            "productImageUrls": ["https://example.invalid/one.jpg", ""],
        },
        target=_target(),
    )

    assert values.title == "Monitored title"
    assert values.strike_price_amount == Decimal("45.99")
    assert values.sale_price_amount == Decimal("39.99")
    assert values.strike_price_currency_code == "USD"
    assert values.category == "Home > Storage"
    assert values.source_category_raw == "Internal > Source Category"
    assert values.average_rating == Decimal("4.6")
    assert values.review_count == 27
    assert values.is_hijacked is None
    assert values.image_urls_json == ["https://example.invalid/one.jpg"]


def test_parser_accepts_explicit_false_hijack_and_rejects_invalid_numbers() -> None:
    values = parse_monitor_listing_values(
        {
            "isHijacked": False,
            "currentPrice": "not-a-number",
            "rating": "8",
            "reviewCount": -1,
        },
        target=_target(),
    )

    assert values.is_hijacked is False
    assert values.sale_price_amount is None
    assert values.sale_price_currency_code is None
    assert values.average_rating is None
    assert values.review_count is None


def test_projection_expands_one_item_observation_to_every_stable_target() -> None:
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [uuid4(), uuid4()]

    projected = WalmartMonitorProjectionService(session).project(_raw_event(target_count=2))

    assert projected == 2
    assert session.scalar.call_count == 2
    assert session.execute.call_count == 2


def test_failed_observation_does_not_publish_stale_business_values() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = uuid4()

    projected = WalmartMonitorProjectionService(session).project(_raw_event(outcome="FAILED"))

    assert projected == 1
    statement = session.scalar.call_args.args[0]
    assert statement.compile().params["title"] is None
    session.execute.assert_not_called()


def test_listing_projection_uses_effective_monitor_values_and_keeps_fallbacks() -> None:
    listing = SimpleNamespace(title="ERP title", brand="ERP brand", is_hijacked=True)
    row = ListingManagementRowProjection(
        listing=listing,  # type: ignore[arg-type]
        listing_start_source_raw=None,
        owner_uid=None,
        owner_name=None,
        product_developer_uid=None,
        product_developer_name=None,
        effective_title="Monitor title",
        effective_brand="ERP brand",
        effective_is_hijacked=False,
    )

    assert row.title == "Monitor title"
    assert row.brand == "ERP brand"
    assert row.is_hijacked is False


def test_listing_response_uses_monitor_values_without_erasing_listing_fallbacks() -> None:
    listing = ListingManagementCurrentMart(
        id=uuid4(),
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        title="ERP title",
        brand="ERP brand",
        is_hijacked=True,
        tags_json=[],
        sales_7d=Decimal("0"),
        sales_14d=Decimal("0"),
        sales_30d=Decimal("0"),
        calculated_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    row = ListingManagementRowProjection(
        listing=listing,
        listing_start_source_raw=None,
        owner_uid=None,
        owner_name=None,
        product_developer_uid=None,
        product_developer_name=None,
        effective_title="Monitor title",
        effective_brand="ERP brand",
        effective_is_hijacked=False,
    )

    item = ListingManagementService(MagicMock(spec=Session))._to_read(row)

    assert item.title == "Monitor title"
    assert item.brand == "ERP brand"
    assert item.is_hijacked is False


def test_listing_query_joins_monitor_current_and_uses_effective_columns() -> None:
    repository = ListingManagementRepository(MagicMock(spec=Session))
    statement = repository._filtered_listing_statement(
        account_refs=frozenset({"synthetic-account"}),
        store_id=None,
        owner_ref="",
        product_type="",
        status="",
        tag="",
        summary_filter="buybox",
        search_field="title",
        keyword="synthetic",
        batch_values="",
    )
    sql = str(statement.compile())

    assert "LEFT OUTER JOIN mart_walmart_monitor_listing_current" in sql
    assert "coalesce(mart_walmart_monitor_listing_current.title" in sql.lower()
    assert "effective_buybox_status" in sql


def test_projection_migration_is_additive_and_does_not_update_listing_mart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://synthetic@db.invalid/synthetic",
    )
    get_settings.cache_clear()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(
        config,
        "20261028_0065_listing_evaluation_runs:20261028_0066_walmart_monitor_listing_projection",
        sql=True,
    )
    sql = buffer.getvalue()

    assert "CREATE TABLE std_walmart_monitor_listing_observations" in sql
    assert "CREATE TABLE mart_walmart_monitor_listing_current" in sql
    assert "ALTER TABLE mart_listing_management_current" not in sql
    assert "UPDATE mart_listing_management_current" not in sql
