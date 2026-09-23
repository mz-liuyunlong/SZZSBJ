"""G3-E: PMC purchase board read routes — OpenAPI, fail-closed auth/scope, envelope."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.pmc_purchase.registry import PMC_PURCHASE_API_REGISTRY
from app.modules.pmc_purchase.schemas import (
    BoardListData,
    BoardRowRead,
    BoardSummaryData,
    ItemIdRef,
    OwnerRef,
    PendingPlanListData,
    SkuCycleBrief,
    SkuCycleListData,
    StageRef,
    StoreRef,
)
from app.modules.pmc_purchase.service import PmcPurchaseReadService

READ = "pmc:purchase:read"
NOW = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
ROUTES = [entry.route_path for entry in PMC_PURCHASE_API_REGISTRY.values()]


def _app(*permissions: str, scoped: bool = True) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=frozenset(permissions)
    )
    if scoped:
        application.dependency_overrides[get_source_account_scope_provider] = lambda: (
            lambda _principal: frozenset({"synthetic-account"})
        )
    else:
        application.dependency_overrides[get_source_account_scope_provider] = lambda: None
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def _row() -> BoardRowRead:
    return BoardRowRead(
        purchase_order_sn="PO1",
        order_item_id="L1",
        plan_sn="P1",
        plan_sns=["P1"],
        order_status=2,
        stage=StageRef(
            stage_code="S3",
            stage_start=date(2026, 9, 1),
            stage_start_estimated=False,
            threshold_days=12,
            due_date=date(2026, 9, 13),
            overdue_days=10,
            overdue_kind="arrival",
            alert_due_since=date(2026, 9, 14),
        ),
        store=StoreRef(id="110652398125259264", name="Store A", attributed=True),
        sku="SKU-A",
        product_name="Widget",
        item_id=ItemIdRef(
            item_id="19051502014",
            source="from_plan_remark",
            source_ref="P1",
            matched_at=NOW,
            match_status="matched",
            msku="MSKU-A",
            gtin="00012345678905",
            fulfillment_type="1",
            wfs_not_ready=False,
        ),
        owner=OwnerRef(uid="u-1", name="Owner One"),
        quantity_total=100,
        quantity_allocated=100,
        quantity_received=0,
        progress_ratio=Decimal("0"),
        remaining_quantity=100,
        order_date=date(2026, 9, 1),
        order_create_date=date(2026, 8, 31),
        plan_create_date=date(2026, 8, 29),
        arrival_date=None,
        arrival_receipt_order_sn=None,
        purchase_cycle_days=None,
        approval_cycle_days=2,
        sku_cycle=SkuCycleBrief(
            value_days=Decimal("12.0000"), source="samples", sample_count=5, unstable=True
        ),
        unit_price=Decimal("5.0000"),
        amount_allocated=Decimal("500.0000"),
        amount_total=Decimal("500.0000"),
        currency_code="CNY",
        calculated_at=NOW,
    )


def test_openapi_lists_all_five_read_routes_with_response_models() -> None:
    schema = create_app().openapi()
    for path in ROUTES:
        assert path in schema["paths"], path
        get = schema["paths"][path]["get"]
        assert get["operationId"]
        assert "200" in get["responses"] and "403" in get["responses"]
    # the only write route is the G3-F SKU cycle override
    posts = {p for p in ROUTES if "post" in schema["paths"][p]}
    assert posts == {"/api/pmc/purchase/sku-cycles/{sku}/overrides"}


def test_routes_fail_closed_for_permission_and_scope() -> None:
    # missing permission → 403 FORBIDDEN
    client = TestClient(_app("products:read"))
    for path in ROUTES:
        target = path.replace("{order_sn}", "PO1").replace("{sku}", "SKU-A")
        body = _envelope(client.get(target, params={"sku": "SKU-A"}), 403)
        assert body["error"]["code"] == "FORBIDDEN"
    # right permission but no account scope → 403 DATA_SCOPE_DENIED
    client = TestClient(_app(READ, scoped=False))
    body = _envelope(client.get("/api/pmc/purchase/board"), 403)
    assert body["error"]["code"] == "DATA_SCOPE_DENIED"
    # no principal at all → 401
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: None
    body = _envelope(TestClient(application).get("/api/pmc/purchase/board"), 401)
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_board_list_returns_envelope_meta_and_validates_params(monkeypatch: Any) -> None:
    def fake_list(self: Any, query: Any, accounts: frozenset[str]) -> Any:
        assert accounts == frozenset({"synthetic-account"})
        assert query.normalized_search_values() == ["SKU-A", "SKU-B"]
        assert query.status == ["s3", "overdue"]
        return BoardListData(items=[_row()], total=1), 1, NOW, 1

    monkeypatch.setattr(PmcPurchaseReadService, "list_board", fake_list)
    client = TestClient(_app(READ))
    body = _envelope(
        client.get(
            "/api/pmc/purchase/board",
            params={
                "search_type": "sku",
                "search_values": ["SKU-A, SKU-B", "SKU-A"],
                "status": ["s3", "overdue"],
                "page_size": 50,
            },
        )
    )
    item = body["data"]["items"][0]
    assert item["purchase_order_sn"] == "PO1"
    assert item["stage"]["overdue_kind"] == "arrival"
    assert item["amount_allocated"] == "500.0000"  # money as string
    assert item["item_id"]["source"] == "from_plan_remark"
    assert body["meta"] == {
        "source": "new_system_postgresql",
        "source_objects": ["dws_purchase_board"],
        "freshness_at": "2026-09-23T03:00:00Z",
        "rule_version": 1,
        "page": 1,
        "page_size": 50,
        "total": 1,
    }

    # validation: search_values without search_type, bad range, unknown status
    for params in (
        {"search_values": ["SKU-A"]},
        {"order_date_from": "2026-09-10", "order_date_to": "2026-09-01"},
        {"status": ["late"]},
        {"page_size": 999},
        {"unknown": "x"},
    ):
        body = _envelope(client.get("/api/pmc/purchase/board", params=params), 422)
        assert body["error"]["code"] == "VALIDATION_ERROR"


def test_summary_detail_cycles_and_pending_plans_delegate_to_service(monkeypatch: Any) -> None:
    summary = BoardSummaryData(
        awaiting_arrival_orders=3,
        arrival_overdue_orders=1,
        purchase_overdue_orders=0,
        purchase_overdue_plans=2,
        average_purchase_cycle_days_90d=Decimal("11.5000"),
        month_purchase_amount=[],
        unstable_sku_count=1,
        itemid_pending_lines=4,
        wfs_not_ready_lines=0,
        unattributed_store_lines=2,
        as_of=date(2026, 9, 23),
    )
    monkeypatch.setattr(PmcPurchaseReadService, "summary", lambda self, q, a: (summary, NOW, 1))
    monkeypatch.setattr(
        PmcPurchaseReadService,
        "sku_cycles",
        lambda self, q, a: (SkuCycleListData(items=[], missing=list(q.sku)), None, None),
    )
    monkeypatch.setattr(
        PmcPurchaseReadService,
        "pending_plans",
        lambda self, q, a: (PendingPlanListData(items=[], total=0, threshold_days=7), 0, 1),
    )
    client = TestClient(_app(READ))

    body = _envelope(client.get("/api/pmc/purchase/board/summary", params={"store_id": ["s1"]}))
    assert body["data"]["purchase_overdue_plans"] == 2
    assert body["data"]["average_purchase_cycle_days_90d"] == "11.5000"
    assert "dwd_purchase_plan" in body["meta"]["source_objects"]

    body = _envelope(client.get("/api/pmc/purchase/sku-cycles", params={"sku": ["A", "B"]}))
    assert body["data"] == {"items": [], "missing": ["A", "B"]}
    _envelope(client.get("/api/pmc/purchase/sku-cycles"), 422)  # sku required

    body = _envelope(client.get("/api/pmc/purchase/plans/pending", params={"overdue_only": True}))
    assert body["data"]["threshold_days"] == 7 and body["meta"]["total"] == 0


def test_order_detail_not_found_is_an_envelope(monkeypatch: Any) -> None:
    from app.core.api import ApiError, ErrorCode

    def missing(self: Any, order_sn: str, accounts: frozenset[str]) -> Any:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    monkeypatch.setattr(PmcPurchaseReadService, "order_detail", missing)
    body = _envelope(TestClient(_app(READ)).get("/api/pmc/purchase/orders/NOPE"), 404)
    assert body["error"]["code"] == "NOT_FOUND"
