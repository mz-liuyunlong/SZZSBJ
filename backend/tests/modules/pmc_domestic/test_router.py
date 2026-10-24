"""Domestic batch board routes: OpenAPI, fail-closed auth, envelope."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.registry import DOMESTIC_BATCH_API_REGISTRY
from app.modules.pmc_domestic.schemas import (
    BatchListData,
    BatchRowRead,
    BatchSummaryData,
    BatchTraceData,
    DomesticFilterOptionsData,
    OutboundTrace,
)
from app.modules.pmc_domestic.service import PmcDomesticBatchReadService

READ = "page:pmc:domestic-warehouse-board:view"
NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
BATCH_ID = UUID("11111111-1111-4111-8111-111111111111")
ROUTES = [entry.route_path for entry in DOMESTIC_BATCH_API_REGISTRY.values()]


def _app(*permissions: str, scoped: bool = True) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=frozenset(permissions)
    )
    if scoped:
        application.dependency_overrides[require_source_account_scope] = lambda: frozenset(
            {"synthetic-account"}
        )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def _row() -> BatchRowRead:
    return BatchRowRead(
        id=BATCH_ID,
        source_account_ref="synthetic-account",
        receipt_order_sn="IB-MATCH",
        line_ordinal=0,
        purchase_order_sn="PO1",
        source_warehouse_id="WH1",
        sku="SKU-A",
        received_qty=10,
        receive_time="2026-10-09 08:00:00",
        received_business_date=date(2026, 10, 9),
        days_in_warehouse=10,
        arrival_date_status="known",
        mapping_status="matched",
        links=[],
    )


def test_openapi_lists_the_four_read_routes() -> None:
    schema = create_app().openapi()
    for path in ROUTES:
        assert path in schema["paths"], path
        get = schema["paths"][path]["get"]
        assert get["operationId"]
        assert "200" in get["responses"] and "403" in get["responses"]
        assert "post" not in schema["paths"][path]


def test_filter_options_envelope_scope_and_owner_validation(monkeypatch: Any) -> None:
    def fake_options(self: Any, accounts: frozenset[str]) -> DomesticFilterOptionsData:
        assert accounts == frozenset({"synthetic-account"})
        return DomesticFilterOptionsData.model_validate(
            {
                "stores": [{"value": "001", "label": "店铺"}],
                "owners": [{"value": "002", "label": "当前产品负责人"}],
            }
        )

    monkeypatch.setattr(PmcDomesticBatchReadService, "filter_options", fake_options)
    client = TestClient(_app(READ))
    body = _envelope(client.get("/api/pmc/domestic/filter-options"))
    assert body["data"]["stores"][0]["value"] == "001"
    assert body["data"]["owners"][0]["value"] == "002"
    assert "dim_lingxing_stores" in body["meta"]["source_objects"]
    denied = TestClient(_app(READ, scoped=False))
    assert _envelope(denied.get("/api/pmc/domestic/filter-options"), 403)["error"]["code"] == (
        "DATA_SCOPE_DENIED"
    )
    for path in ("/api/pmc/domestic/batches", "/api/pmc/domestic/batches/summary"):
        for values in ([" "], [""], [str(n) for n in range(51)]):
            assert _envelope(client.get(path, params={"owner_uid": values}), 422)["error"]


def test_routes_fail_closed_for_permission_and_scope() -> None:
    client = TestClient(_app("products:read"))
    for path in ROUTES:
        target = path.replace("{batch_id}", str(BATCH_ID))
        body = _envelope(client.get(target), 403)
        assert body["error"]["code"] == "FORBIDDEN"
    client = TestClient(_app(READ, scoped=False))
    body = _envelope(client.get("/api/pmc/domestic/batches"), 403)
    assert body["error"]["code"] == "DATA_SCOPE_DENIED"
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: None
    body = _envelope(TestClient(application).get("/api/pmc/domestic/batches"), 401)
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_list_and_summary_return_envelope_and_reject_bad_query(monkeypatch: Any) -> None:
    def fake_list(self: Any, query: Any, accounts: frozenset[str]) -> Any:
        assert accounts == frozenset({"synthetic-account"})
        assert query.mapping_status == "matched"
        assert query.warehouse_id == ["WH1"]
        return BatchListData(items=[_row()], total=1), 1, NOW

    def fake_summary(self: Any, query: Any, accounts: frozenset[str]) -> Any:
        return (
            BatchSummaryData(
                receipt_batch_count=4,
                received_qty=25,
                warehouse_count=2,
                matched_batch_count=2,
                unresolved_batch_count=2,
                missing_arrival_date_count=1,
                as_of=date(2026, 10, 19),
            ),
            NOW,
        )

    monkeypatch.setattr(PmcDomesticBatchReadService, "list_batches", fake_list)
    monkeypatch.setattr(PmcDomesticBatchReadService, "summary", fake_summary)
    client = TestClient(_app(READ))
    body = _envelope(
        client.get(
            "/api/pmc/domestic/batches",
            params={"mapping_status": "matched", "warehouse_id": ["WH1"], "page_size": 50},
        )
    )
    assert body["data"]["items"][0]["receipt_order_sn"] == "IB-MATCH"
    assert body["data"]["items"][0]["days_in_warehouse"] == 10
    assert body["meta"]["source"] == "new_system_postgresql"
    assert body["meta"]["source_objects"] == [
        "dwd_domestic_receipt_batch",
        "dwd_domestic_receipt_batch_link",
    ]
    assert body["meta"]["total"] == 1
    body = _envelope(client.get("/api/pmc/domestic/batches/summary"))
    assert body["data"]["receipt_batch_count"] == 4
    assert body["data"]["as_of"] == "2026-10-19"
    for params in (
        {"received_from": "2026-10-10", "received_to": "2026-10-01"},
        {"mapping_status": "pending"},
        {"page_size": 999},
        {"unknown": "x"},
    ):
        body = _envelope(client.get("/api/pmc/domestic/batches", params=params), 422)
        assert body["error"]["code"] == "VALIDATION_ERROR"


def test_detail_and_trace_envelopes_and_not_found(monkeypatch: Any) -> None:
    from app.core.api import ApiError, ErrorCode

    monkeypatch.setattr(
        PmcDomesticBatchReadService, "detail", lambda self, batch_id, accounts: (_row(), NOW)
    )
    monkeypatch.setattr(
        PmcDomesticBatchReadService,
        "trace",
        lambda self, batch_id, accounts: (
            BatchTraceData(batch=_row(), outbound=OutboundTrace()),
            NOW,
        ),
    )
    client = TestClient(_app(READ))
    body = _envelope(client.get(f"/api/pmc/domestic/batches/{BATCH_ID}"))
    assert body["data"]["id"] == str(BATCH_ID)
    body = _envelope(client.get(f"/api/pmc/domestic/batches/{BATCH_ID}/trace"))
    assert body["data"]["outbound"] == {
        "status": "unknown",
        "reason": "source_not_published",
        "events": [],
    }

    def missing(self: Any, batch_id: UUID, accounts: frozenset[str]) -> Any:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    monkeypatch.setattr(PmcDomesticBatchReadService, "detail", missing)
    body = _envelope(client.get(f"/api/pmc/domestic/batches/{BATCH_ID}"), 404)
    assert body["error"]["code"] == "NOT_FOUND"
