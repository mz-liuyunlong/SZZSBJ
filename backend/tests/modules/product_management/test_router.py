from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.product_management.models import ProductPricingRecalculationRun
from app.modules.product_management.schemas import (
    CostComponentRead,
    ExportRequest,
    PricingBreakdownRead,
    PricingRuleRead,
    PricingRulesData,
    PricingRuleWrite,
    ProductCoreRead,
    ProductManagementDetailData,
    ProductManagementListData,
    ProductManagementListItem,
    ProductManagementOptionsData,
    RecalculatePricingResult,
    UserTableViewRead,
)
from app.modules.product_management.service import ProductManagementService
from app.modules.products.dependencies import get_product_scope_provider

SKU_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
ALL_PERMISSIONS = frozenset(
    {
        "products:read",
        "products:cost:read",
        "products:export",
        "products:pricing_rules:read",
        "products:pricing_rules:update",
        "products:pricing:recalculate",
        "products:table_views:update",
    }
)


def _app(*permissions: str) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions) if permissions else ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({"synthetic-account"})
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _assert_envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def test_openapi_contains_all_ten_product_management_routes() -> None:
    paths = create_app().openapi()["paths"]
    expected = {
        "/api/product-management/skus",
        "/api/product-management/skus/{sku_id}",
        "/api/product-management/options",
        "/api/product-management/skus/export",
        "/api/user-table-views/product-management",
        "/api/product-management/pricing-rules",
        "/api/product-management/skus/recalculate-pricing",
        "/api/product-management/skus/{sku_id}/pricing-breakdown",
    }
    assert expected <= set(paths)
    assert set(paths["/api/user-table-views/product-management"]) >= {"get", "put"}
    assert set(paths["/api/product-management/pricing-rules"]) >= {"get", "put"}


def test_routes_fail_closed_for_auth_permission_and_source_scope() -> None:
    assert TestClient(create_app()).get("/api/product-management/options").status_code == 401
    denied = TestClient(_app("unrelated:permission")).get("/api/product-management/options")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=ALL_PERMISSIONS
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).get("/api/product-management/skus")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_batch_sku_query_is_cleaned_deduplicated_and_case_preserving(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    def list_skus(
        self: ProductManagementService,
        query: Any,
        account_refs: frozenset[str],
        include_costs: bool,
    ) -> tuple[ProductManagementListData, int, datetime | None, datetime | None]:
        captured["sku_batch"] = query.sku_batch
        return ProductManagementListData(items=[]), 0, None, None

    monkeypatch.setattr(ProductManagementService, "list_skus", list_skus)
    response = TestClient(_app()).get(
        "/api/product-management/skus",
        params=[
            ("sku_batch", " Synthetic-A\n\nSynthetic-b "),
            ("sku_batch", "Synthetic-A"),
        ],
    )

    _assert_envelope(response)
    assert captured["sku_batch"] == ["Synthetic-A", "Synthetic-b"]


def test_batch_sku_query_rejects_empty_or_more_than_one_thousand_values() -> None:
    client = TestClient(_app())
    empty = client.get("/api/product-management/skus", params=[("sku_batch", "  \n")])
    too_many = client.get(
        "/api/product-management/skus",
        params=[("sku_batch", f"SYNTHETIC-{index}") for index in range(1001)],
    )

    assert empty.status_code == 422
    assert too_many.status_code == 422


def test_recalculation_preview_rejects_more_than_one_hundred_selected_ids() -> None:
    response = TestClient(_app()).post(
        "/api/product-management/skus/recalculate-pricing",
        json={
            "source_account_ref": "synthetic-account",
            "scope": "selected",
            "sku_ids": [str(UUID(int=index)) for index in range(1, 102)],
            "preview_only": True,
            "reason": "synthetic bounded preview",
            "idempotency_key": "synthetic-preview-boundary",
        },
    )

    assert response.status_code == 422


def test_failed_recalculation_replay_uses_error_envelope(monkeypatch: Any) -> None:
    def replay_failed(self: ProductManagementService, *args: Any, **kwargs: Any) -> Any:
        raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)

    monkeypatch.setattr(ProductManagementService, "recalculate", replay_failed)
    response = TestClient(_app()).post(
        "/api/product-management/skus/recalculate-pricing",
        json={
            "source_account_ref": "synthetic-account",
            "scope": "all",
            "reason": "synthetic failed replay",
            "idempotency_key": "synthetic-denied-replay",
        },
    )

    assert response.status_code == 403
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"

    unknown_code = "UNKNOWN_INTERNAL_RECALCULATION_DETAIL"

    def replay_unknown(
        self: ProductManagementService, payload: Any, *args: Any, **kwargs: Any
    ) -> Any:
        run = MagicMock(spec=ProductPricingRecalculationRun)
        run.request_digest = self._recalculation_request_digest(payload)
        run.status = "failed"
        run.error_code = unknown_code
        return self._recalculation_replay(run, run.request_digest)

    monkeypatch.setattr(ProductManagementService, "recalculate", replay_unknown)
    unknown = TestClient(_app()).post(
        "/api/product-management/skus/recalculate-pricing",
        json={
            "source_account_ref": "synthetic-account",
            "scope": "all",
            "reason": "synthetic unknown failed replay",
            "idempotency_key": "synthetic-unknown-replay",
        },
    )
    assert unknown.status_code == 500
    assert unknown.json()["error"]["code"] == "RECALCULATION_FAILED"
    assert unknown_code not in unknown.text


def test_read_export_recalculate_and_view_contracts(
    monkeypatch: Any,
) -> None:
    captured_request_ids: list[str] = []
    list_data = ProductManagementListData(
        items=[
            ProductManagementListItem(
                sku_id=SKU_ID,
                sku="SYNTHETIC-SKU",
                product_name="Synthetic Product",
                primary_image=None,
                internal_tags=[],
                category=None,
                purchase_cost_cny=None,
                unit_first_leg_cost=None,
                unit_first_leg_currency_code=None,
                purchase_delivery_days=None,
                data_quality_score=None,
                linked_platform_sku_count=0,
                source_observed_at=NOW,
                product_grade="A",
                grade_reason="calculated_grade_a",
                wfs_fulfillment_fee=None,
                wfs_fulfillment_fee_currency_code=None,
                wfs_daily_storage_fee=None,
                wfs_daily_storage_fee_currency_code=None,
                suggested_price_usd=None,
                minimum_price_usd=None,
                clearance_price_usd=None,
                price_currency_code=None,
                calculation_status="ok",
                calculated_at=NOW,
                rule_version="synthetic-v1",
                costs_visible=False,
            )
        ]
    )
    detail = ProductManagementDetailData(
        sku_id=SKU_ID,
        core=ProductCoreRead(
            product_id=SKU_ID,
            sku="SYNTHETIC-SKU",
            product_name="Synthetic Product",
            category=None,
            product_type=None,
            status=None,
            manual_grade=None,
        ),
        synced_detail=None,
        images=[],
        source_tags=[],
        internal_tags=[],
        pricing=None,
    )
    view = UserTableViewRead(
        applied_column_keys=["sku", "productName"],
        column_widths={"sku": 120},
        schema_version=1,
        view_key="default",
        updated_at=NOW,
    )
    monkeypatch.setattr(
        ProductManagementService,
        "list_skus",
        lambda self, query, account_refs, include_costs: (list_data, 1, NOW, NOW),
    )
    monkeypatch.setattr(
        ProductManagementService,
        "get_sku",
        lambda self, sku_id, account_refs, include_costs: detail,
    )
    monkeypatch.setattr(
        ProductManagementService,
        "options",
        lambda self: ProductManagementOptionsData(
            product_grades=["A", "B", "C", "exception"],
            calculation_statuses=["ok"],
            internal_tags=[],
        ),
    )

    def recalculate(
        self: ProductManagementService,
        payload: Any,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str,
    ) -> RecalculatePricingResult:
        captured_request_ids.append(request_id)
        return RecalculatePricingResult(
            run_id=SKU_ID,
            mode="preview",
            status="previewed",
            matched_count=1,
            eligible_count=1,
            skipped_count=0,
            estimated_affected_count=1,
            affected_count=0,
            failed_count=0,
            idempotent_replay=False,
        )

    monkeypatch.setattr(ProductManagementService, "recalculate", recalculate)
    monkeypatch.setattr(
        ProductManagementService,
        "get_table_view",
        lambda self, principal_ref: view,
    )
    monkeypatch.setattr(
        ProductManagementService,
        "save_table_view",
        lambda self, payload, principal_ref: view,
    )
    client = TestClient(_app())
    responses = [
        client.get("/api/product-management/skus"),
        client.get(f"/api/product-management/skus/{SKU_ID}"),
        client.get("/api/product-management/options"),
        client.post("/api/product-management/skus/export", json={"max_rows": 100}),
        client.post(
            "/api/product-management/skus/recalculate-pricing",
            json={
                "source_account_ref": "synthetic-account",
                "scope": "selected",
                "sku_ids": [str(SKU_ID)],
                "reason": "synthetic test",
                "idempotency_key": "synthetic-key",
            },
        ),
        client.get("/api/user-table-views/product-management"),
        client.put(
            "/api/user-table-views/product-management",
            json={
                "applied_column_keys": ["sku", "productName"],
                "column_widths": {"sku": 120},
            },
        ),
    ]
    for response in responses:
        body = _assert_envelope(response)
        assert body["success"] is True
        assert body["error"] is None
        lowered = response.text.lower()
        assert "payload_json" not in lowered
        assert "authorization" not in lowered
        assert "access_token" not in lowered
        assert "refresh_token" not in lowered

    export_body = responses[3].json()["data"]
    assert export_body == {
        "status": "not_implemented_safe",
        "row_limit": 100,
        "file_created": False,
    }
    assert captured_request_ids == [responses[4].json()["request_id"]]


def test_pricing_rule_and_table_view_inputs_reject_unknown_or_business_data() -> None:
    client = TestClient(_app())
    view = client.put(
        "/api/user-table-views/product-management",
        json={
            "applied_column_keys": ["sku"],
            "column_widths": {},
            "selected_skus": ["must-not-be-stored"],
        },
    )
    assert view.status_code == 422
    assert "must-not-be-stored" not in view.text

    rule = client.put(
        "/api/product-management/pricing-rules",
        json={
            "version": "synthetic-v1",
            "source_account_ref": "synthetic-account",
            "effective_from": "2026-01-01T00:00:00Z",
            "wfs_source_url": (
                "https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"
            ),
            "wfs_confirmed_at": "2026-01-01T00:00:00Z",
            "wfs_confirmed_by": "synthetic-reviewer",
            "change_reason": "synthetic test",
            "approval_ref": "synthetic-approval",
            "unknown_provider_payload": "must-not-be-returned",
        },
    )
    assert rule.status_code == 422
    assert "must-not-be-returned" not in rule.text


def test_pricing_breakdown_cost_access_is_audited_without_amounts(
    monkeypatch: Any,
) -> None:
    components = [
        CostComponentRead(
            name=name,
            amount=None,
            currency="CNY",
            source="missing",
            included=True,
            status="missing",
        )
        for name in (
            "purchase_cost",
            "first_leg",
            "wfs_fulfillment",
            "estimated_storage",
            "other_fixed_cost",
            "commission",
        )
    ]
    breakdown = PricingBreakdownRead(
        sku_id=SKU_ID,
        calculation_status="missing_purchase_cost",
        wfs_calc_status="missing_rate",
        wfs_calc_reason="rate_config_not_available",
        wfs_fee_source="calculated_rule",
        storage_calc_status="missing_rate",
        first_leg_calc_status="not_calculated",
        product_grade="exception",
        grade_reason="missing_purchase_cost",
        commission_source="default_zero",
        rule_version="synthetic-v1",
        calc_version="product_management_pricing_v1",
        pricing_effective_at=NOW,
        calculated_at=NOW,
        wfs_fulfillment_fee_usd=None,
        wfs_fulfillment_fee_cny=None,
        package_volume_cuft=None,
        daily_storage_fee_per_unit_usd=None,
        daily_storage_fee_per_unit_cny=None,
        estimated_storage_fee_usd=None,
        estimated_storage_fee_cny=None,
        suggested_price_usd=None,
        minimum_price_usd=None,
        clearance_price_usd=None,
        price_currency_code=None,
        suggested_gross_margin_rate=None,
        suggested_roi=None,
        components=components,
    )
    monkeypatch.setattr(
        ProductManagementService,
        "pricing_breakdown",
        lambda self, sku_id, account_refs, include_costs: breakdown,
    )
    audit = MagicMock()
    monkeypatch.setattr("app.modules.product_management.router.audit_logger.info", audit)

    response = TestClient(_app()).get(
        f"/api/product-management/skus/{SKU_ID}/pricing-breakdown",
        headers={"X-Request-ID": "synthetic-breakdown-request"},
    )

    _assert_envelope(response)
    assert "synthetic-breakdown-request" in repr(audit.call_args)
    assert "amount" not in repr(audit.call_args)


def test_pricing_rules_read_contract_can_return_empty_state(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        ProductManagementService,
        "list_rules",
        lambda self, source_account_ref, account_refs: PricingRulesData(
            items=[], active_rule_id=None
        ),
    )
    body = _assert_envelope(
        TestClient(_app()).get(
            "/api/product-management/pricing-rules",
            params={"source_account_ref": "synthetic-account"},
        )
    )
    assert body["data"] == {"items": [], "active_rule_id": None}


def test_pricing_rule_put_publishes_a_new_synthetic_version(monkeypatch: Any) -> None:
    payload = {
        "source_account_ref": "synthetic-account",
        "version": "synthetic-v1",
        "effective_from": "2026-01-01T00:00:00Z",
        "wfs_source_url": ("https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"),
        "wfs_confirmed_at": "2026-01-01T00:00:00Z",
        "wfs_confirmed_by": "synthetic-reviewer",
        "change_reason": "synthetic test",
        "approval_ref": "synthetic-approval",
    }
    parsed = PricingRuleWrite.model_validate(payload)
    published = PricingRuleRead(
        id=SKU_ID,
        rule_key="product_management",
        is_active=True,
        approved_by="synthetic-user",
        approved_at=NOW,
        actor_ref="synthetic-user",
        request_id="synthetic-request",
        action="publish_pricing_rule",
        status="succeeded",
        created_at=NOW,
        updated_at=NOW,
        **parsed.model_dump(),
    )
    captured: dict[str, str] = {}

    def publish_rule(
        self: ProductManagementService,
        body: PricingRuleWrite,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str,
    ) -> PricingRuleRead:
        captured["request_id"] = request_id
        return published

    monkeypatch.setattr(ProductManagementService, "publish_rule", publish_rule)

    body = _assert_envelope(
        TestClient(_app()).put("/api/product-management/pricing-rules", json=payload)
    )

    assert body["data"]["version"] == "synthetic-v1"
    assert body["data"]["is_active"] is True
    assert captured["request_id"] == body["request_id"]


def test_pricing_rule_put_rejects_naive_datetimes() -> None:
    response = TestClient(_app()).put(
        "/api/product-management/pricing-rules",
        json={
            "source_account_ref": "synthetic-account",
            "version": "synthetic-v1",
            "effective_from": "2026-01-01T00:00:00",
            "wfs_source_url": (
                "https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"
            ),
            "wfs_confirmed_at": "2026-01-01T00:00:00Z",
            "wfs_confirmed_by": "synthetic-reviewer",
            "change_reason": "synthetic test",
            "approval_ref": "synthetic-approval",
        },
    )

    assert response.status_code == 422


def test_export_service_is_a_safe_placeholder() -> None:
    result = ProductManagementService.export(ExportRequest())
    assert result.status == "not_implemented_safe"
    assert result.file_created is False
