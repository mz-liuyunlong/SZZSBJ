from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.warehouse_wfs.schemas import (
    WfsFeeAlertListData,
    WfsFeeAlertRead,
    WfsFeeCaseWrite,
)
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def _app(*permissions: str):
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions),
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({"synthetic-account"})
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _item() -> WfsFeeAlertRead:
    return WfsFeeAlertRead(
        id="00000000-0000-0000-0000-000000000001",
        business_date_la=date(2026, 9, 1),
        store_id="store-1",
        store_name="Walmart US",
        owner_ref="owner-1",
        item_id="item-1",
        msku="msku-1",
        local_sku="sku-1",
        product_name="Synthetic",
        order_count=Decimal("2"),
        sales_qty=Decimal("3"),
        cost_quantity=Decimal("4"),
        expected_fee_amount=Decimal("12"),
        actual_fee_amount=Decimal("15"),
        variance_amount=Decimal("3"),
        variance_rate=Decimal("0.25"),
        expected_unit_amount=Decimal("3"),
        actual_unit_amount=Decimal("3.75"),
        status="未开Case",
        case_no=None,
        reason=None,
        priority="中",
        claim_amount=None,
        recovered_amount=Decimal("0"),
        pending_recovery_amount=Decimal("3"),
        case_opened_at=None,
        next_follow_at=None,
        latest_follow=None,
    )


def test_wfs_fee_alert_routes_are_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/warehouse/wfs-fee-alerts" in paths
    assert "/api/warehouse/wfs-fee-actuals" in paths
    assert "/api/warehouse/wfs-fee-alerts/{mart_id}/case" in paths


def test_wfs_fee_alert_read_requires_permission(monkeypatch: Any) -> None:
    denied = TestClient(_app("products:read")).get("/api/warehouse/wfs-fee-alerts")
    assert denied.status_code == 403

    def list_alerts(
        self: WfsFeeAlertService,
        query: Any,
        account_refs: frozenset[str],
    ) -> tuple[WfsFeeAlertListData, int]:
        assert account_refs == frozenset({"synthetic-account"})
        return WfsFeeAlertListData(items=[_item()]), 1

    monkeypatch.setattr(WfsFeeAlertService, "list_alerts", list_alerts)
    response = TestClient(_app("warehouse:wfs-fee-alert:read")).get(
        "/api/warehouse/wfs-fee-alerts"
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["variance_amount"] == "3"


def test_wfs_case_write_uses_write_permission(monkeypatch: Any) -> None:
    captured: dict[str, object] = {}

    def update_case(
        self: WfsFeeAlertService,
        mart_id: UUID,
        payload: WfsFeeCaseWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        captured.update(
            mart_id=mart_id,
            payload=payload,
            account_refs=account_refs,
            actor_ref=actor_ref,
        )

    monkeypatch.setattr(WfsFeeAlertService, "update_case", update_case)
    response = TestClient(_app("warehouse:wfs-fee-alert:write")).put(
        "/api/warehouse/wfs-fee-alerts/00000000-0000-0000-0000-000000000001/case",
        json={
            "status": "跟进中",
            "case_no": "CASE-1",
            "reason": "WFS actual exceeds expected",
            "priority": "高",
            "recovered_amount": "1.25",
            "latest_follow": "submitted evidence",
        },
    )
    assert response.status_code == 200
    assert captured["actor_ref"] == "synthetic-user"
