from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync import (
    LingxingWfsSettlementSyncHandler,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
)
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
NOW = datetime(2026, 10, 18, tzinfo=UTC)


class FakeClient:
    def __init__(self, envelopes: list[LingxingRawEnvelope]) -> None:
        self.envelopes = envelopes
        self.calls: list[tuple[str, int, int]] = []

    def fetch_wfs_settlement_page(self, **kwargs: object) -> LingxingRawEnvelope:
        self.calls.append(
            (
                str(kwargs["store_id"]),
                int(str(kwargs["offset"])),
                int(str(kwargs["length"])),
            )
        )
        return self.envelopes.pop(0)


def settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "WFS_AUTO_DETECT_ENABLED": True,
            "WFS_AUTO_CASE_CREATE_ENABLED": False,
        }
    )


def envelope(
    store: str,
    page: int,
    rows: list[dict[str, JsonValue]],
    total: int,
) -> LingxingRawEnvelope:
    payload: JsonValue = {"code": 0, "data": {"list": rows, "total": total}}
    return LingxingRawEnvelope(
        api_path="/basicOpen/multiplatform/profit/report/order",
        request_body_json={"offset": (page - 1) * 2, "length": 2, "sids": store},
        response_json=payload,
        response_code=200,
        is_success=True,
        pulled_at=NOW,
        page_no=page,
        page_size=2,
        store_id=store,
        object_type="wfs_settlement_profit_order",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="work-fixture",
        attempt_no=1,
    )


def row(store_name: str, index: int) -> dict[str, JsonValue]:
    return {
        "storeName": store_name,
        "msku": "SKU-A",
        "settlementDate": "2026-10-10",
        "uniqueId": f"source-{store_name}-{index}",
        "rowIndex": index,
        "platformOrderNo": f"order-{store_name}-{index}",
        "salesNum": 1,
        "platformLogisticsAmount": "-6.95",
        "currencyCode": "USD",
    }


def run() -> IntegrationSyncRun:
    return IntegrationSyncRun(
        id=uuid4(),
        config_id=uuid4(),
        interface_id=uuid4(),
        provider="lingxing",
        interface_key="wfsProfitOrder",
        source_account_ref="primary",
        trigger_type="manual",
        status="running",
        idempotency_key="wfs-fixture",
        window_start=date(2026, 8, 19),
        window_end=date(2026, 10, 17),
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )


def interface(run: IntegrationSyncRun) -> IntegrationInterface:
    return IntegrationInterface(
        id=run.interface_id,
        provider="lingxing",
        interface_key="wfsProfitOrder",
        display_name="WFS",
        method="POST",
        endpoint_path="/basicOpen/multiplatform/profit/report/order",
        request_kind="offset_page",
        handler_key="lingxing.wfs.profit_order.v1",
        contract_version="v1",
        outbound_enabled=True,
    )


def configured_handler(
    client: FakeClient,
    *,
    heartbeat: MagicMock | None = None,
) -> tuple[LingxingWfsSettlementSyncHandler, MagicMock]:
    session = MagicMock(spec=Session)
    handler = LingxingWfsSettlementSyncHandler(
        session,
        client=client,
        settings=settings(),
        heartbeat=heartbeat,
    )
    handler.repository = MagicMock()
    handler.repository.get_config.return_value = IntegrationSyncConfig(
        id=uuid4(),
        interface_id=uuid4(),
        source_account_ref="primary",
        is_enabled=True,
        schedule_enabled=False,
        page_size=2,
        max_pages=10,
        max_attempts=2,
    )
    handler.repository.get_retention_policy.return_value = RawRetentionPolicy(
        id=uuid4(),
        policy_key="lingxing-wfs-profit-order-v1",
        provider="lingxing",
        interface_key="wfsProfitOrder",
        hot_retention_days=365,
        archive_required=False,
        legal_hold=False,
        is_active=True,
    )
    handler.repository.add_raw_blob.side_effect = lambda value: value
    handler.repository.add_raw_request_ref.side_effect = lambda value: value
    return handler, session


def test_multi_store_full_pagination_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        [
            envelope("1", 1, [row("A", 1), row("A", 2)], 3),
            envelope("1", 2, [row("A", 3)], 3),
            envelope("2", 1, [row("B", 1), row("B", 2)], 3),
            envelope("2", 2, [row("B", 3)], 3),
        ]
    )
    heartbeat = MagicMock()
    handler, session = configured_handler(client, heartbeat=heartbeat)
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.discover_walmart_stores",
        lambda *_args, **_kwargs: (
            WfsSettlementStore("primary", "1", "A", "1"),
            WfsSettlementStore("primary", "2", "B", "2"),
        ),
    )
    upsert = MagicMock(return_value=2)
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.WfsSettlementRepository.upsert_rows",
        upsert,
    )
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.detect_store_from_persisted_evidence",
        lambda *_args, **_kwargs: SimpleNamespace(would_create=1),
    )
    selected_run = run()

    result = handler.execute(selected_run, interface(selected_run))

    assert result.status == "completed"
    assert result.stores_completed == 2
    assert result.stores_failed == 0
    assert client.calls == [("1", 0, 2), ("1", 2, 2), ("2", 0, 2), ("2", 2, 2)]
    assert upsert.call_count == 4
    assert heartbeat.call_count == 8
    assert session.commit.call_count > 0


def test_duplicate_line_across_pages_fails_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = row("A", 1)
    client = FakeClient(
        [
            envelope("1", 1, [duplicate, row("A", 2)], 3),
            envelope("1", 2, [duplicate], 3),
        ]
    )
    handler, _ = configured_handler(client)
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.discover_walmart_stores",
        lambda *_args, **_kwargs: (WfsSettlementStore("primary", "1", "A", "1"),),
    )
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.WfsSettlementRepository.upsert_rows",
        lambda *_args, **_kwargs: 2,
    )
    detect = MagicMock()
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.detect_store_from_persisted_evidence",
        detect,
    )
    selected_run = run()

    result = handler.execute(selected_run, interface(selected_run))

    assert result.status == "failed"
    assert result.stores_failed == 1
    detect.assert_not_called()


def test_partial_store_failure_marks_run_failed_and_never_detects_failed_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        [
            envelope("1", 1, [row("A", 1)], 1),
            envelope("2", 1, [], 1),
        ]
    )
    handler, _ = configured_handler(client)
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.discover_walmart_stores",
        lambda *_args, **_kwargs: (
            WfsSettlementStore("primary", "1", "A", "1"),
            WfsSettlementStore("primary", "2", "B", "2"),
        ),
    )
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.WfsSettlementRepository.upsert_rows",
        lambda *_args, **_kwargs: 1,
    )
    detect = MagicMock(return_value=SimpleNamespace(would_create=0))
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_wfs_settlement_sync.detect_store_from_persisted_evidence",
        detect,
    )
    selected_run = run()

    result = handler.execute(selected_run, interface(selected_run))

    assert result.status == "completed_with_warnings"
    assert result.stores_completed == 1
    assert result.stores_failed == 1
    assert selected_run.status == "failed"
    assert selected_run.error_code == "SYNC_WFS_STORE_PARTIAL"
    assert detect.call_count == 1
    assert detect.call_args.kwargs["store_id"] == "1"
    assert detect.call_args.kwargs["collection_verified"] is True
