import inspect
import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.integration_sync.schemas import (
    InterfaceListData,
    RawRequestMetadataListData,
    RawRequestMetadataRead,
    RequestKind,
)
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError, execute_sync_run, scheduler_tick
from app.modules.products.dependencies import get_product_scope_provider
from app.modules.sku_detail.schemas import (
    SkuCostBlock,
    SkuDetailData,
    SkuIdentityRead,
)
from app.modules.sku_detail.service import SkuDetailService

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SKU_ID = UUID("00000000-0000-0000-0000-000000000001")
ALL_PERMISSIONS = frozenset(
    {
        "integrations:read",
        "integrations:update",
        "integrations:execute",
        "integrations:raw_metadata:read",
        "products:read",
        "products:sync_history:read",
        "products:raw_lineage:read",
        "products:cost:read",
        "products:operation_logs:read",
    }
)


def _app(*permissions: str, scope: bool = True) -> FastAPI:
    app = create_app()
    principal = Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions) if permissions else ALL_PERMISSIONS,
    )
    app.dependency_overrides[get_optional_principal] = lambda: principal
    if scope:
        app.dependency_overrides[get_source_account_scope_provider] = lambda: (
            lambda _principal: frozenset({"default"})
        )
    app.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return app


def test_openapi_has_exact_approved_routes() -> None:
    paths = set(create_app().openapi()["paths"])
    expected = {
        "/api/integrations/interfaces",
        "/api/integrations/sync-configs",
        "/api/integrations/sync-configs/{config_id}",
        "/api/integrations/sync-configs/{config_id}/run",
        "/api/integrations/sync-runs/{run_id}/retry",
        "/api/integrations/sync-configs/{config_id}/backfill",
        "/api/integrations/sync-runs",
        "/api/integrations/sync-runs/{run_id}",
        "/api/integrations/sync-runs/{run_id}/work-items",
        "/api/integrations/sync-runs/{run_id}/raw-request-refs",
        "/api/products/skus",
        "/api/products/skus/{sku_id}/detail",
        "/api/products/skus/{sku_id}/sync-history",
        "/api/products/skus/{sku_id}/raw-lineage",
        "/api/products/skus/{sku_id}/platform-listings",
        "/api/products/skus/{sku_id}/cost-history",
        "/api/products/skus/{sku_id}/operation-logs",
    }
    assert expected <= paths
    assert not any(path.startswith("/api/v1/integrations") for path in paths)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/integrations/interfaces", None),
        ("GET", "/api/integrations/sync-configs", None),
        ("PATCH", f"/api/integrations/sync-configs/{SKU_ID}", {"is_enabled": False}),
        ("POST", f"/api/integrations/sync-configs/{SKU_ID}/run", {"reason": "test"}),
        ("POST", f"/api/integrations/sync-runs/{SKU_ID}/retry", {"reason": "test"}),
        (
            "POST",
            f"/api/integrations/sync-configs/{SKU_ID}/backfill",
            {
                "reason": "test",
                "window_start": "2026-01-01T00:00:00Z",
                "window_end": "2026-01-02T00:00:00Z",
            },
        ),
        ("GET", "/api/integrations/sync-runs", None),
        ("GET", f"/api/integrations/sync-runs/{SKU_ID}", None),
        ("GET", f"/api/integrations/sync-runs/{SKU_ID}/work-items", None),
        ("GET", f"/api/integrations/sync-runs/{SKU_ID}/raw-request-refs", None),
        ("GET", "/api/products/skus", None),
        ("GET", f"/api/products/skus/{SKU_ID}/detail", None),
        ("GET", f"/api/products/skus/{SKU_ID}/sync-history", None),
        ("GET", f"/api/products/skus/{SKU_ID}/raw-lineage", None),
        ("GET", f"/api/products/skus/{SKU_ID}/platform-listings", None),
        ("GET", f"/api/products/skus/{SKU_ID}/cost-history", None),
        ("GET", f"/api/products/skus/{SKU_ID}/operation-logs", None),
    ],
)
def test_every_route_fails_without_required_permission(
    method: str, path: str, body: object
) -> None:
    response = TestClient(_app("unrelated:permission")).request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_account_scoped_route_fails_closed_without_scope_provider() -> None:
    response = TestClient(_app(scope=False)).get("/api/integrations/sync-configs")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_interface_catalog_is_global_but_still_permission_protected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        IntegrationSyncService,
        "list_interfaces",
        lambda self, query: (InterfaceListData(items=[]), 0),
    )
    response = TestClient(_app("integrations:read", scope=False)).get(
        "/api/integrations/interfaces"
    )
    assert response.status_code == 200
    assert response.json()["meta"]["source"] == "new_system_postgresql"


def test_raw_metadata_response_excludes_payload_and_archive_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = RawRequestMetadataRead(
        id=SKU_ID,
        run_id=SKU_ID,
        work_item_id=SKU_ID,
        raw_blob_id=SKU_ID,
        request_kind=RequestKind.OFFSET_PAGE,
        attempt_no=1,
        request_safe_params={"offset": 0, "length": 1},
        http_status=200,
        provider_code="200",
        is_success=True,
        response_count=1,
        response_hash="0" * 64,
        payload_bytes=10,
        storage_mode="database",
        archive_present=False,
        requested_at=NOW,
        received_at=NOW,
    )
    monkeypatch.setattr(
        IntegrationSyncService,
        "list_raw_request_refs",
        lambda self, run_id, page, page_size, account_refs: (
            RawRequestMetadataListData(items=[item]),
            1,
        ),
    )
    response = TestClient(_app()).get(f"/api/integrations/sync-runs/{SKU_ID}/raw-request-refs")
    assert response.status_code == 200
    assert "payload_json" not in response.text
    assert "archive_uri" not in response.text
    assert response.json()["meta"]["freshness_at"] == "2026-01-01T00:00:00Z"


def test_detail_cost_block_depends_on_cost_permission(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.audit.sku_detail")

    def detail(
        self: SkuDetailService,
        sku_id: UUID,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> SkuDetailData:
        del self, sku_id, account_refs
        return SkuDetailData(
            identity=SkuIdentityRead(
                sku_id=SKU_ID,
                provider="lingxing",
                source_account_ref="default",
                lingxing_sku_code=None,
                mapping_status="unmapped",
                is_active=True,
                first_seen_at=NOW,
                last_seen_at=NOW,
            ),
            detail=None,
            images=[],
            tags=[],
            profile=None,
            costs=(
                SkuCostBlock(
                    purchase_cost_cny=Decimal("1.0000"),
                    purchase_cost_currency_code="CNY",
                    customs_declared_unit_price=None,
                    customs_declared_currency=None,
                    us_first_leg_cost=None,
                    us_first_leg_currency=None,
                )
                if include_costs
                else None
            ),
        )

    monkeypatch.setattr(SkuDetailService, "get_detail", detail)
    without_cost = TestClient(_app("products:read")).get(f"/api/products/skus/{SKU_ID}/detail")
    with_cost = TestClient(_app("products:read", "products:cost:read")).get(
        f"/api/products/skus/{SKU_ID}/detail"
    )
    assert without_cost.json()["data"]["costs"] is None
    assert with_cost.json()["data"]["costs"]["purchase_cost_cny"] == "1.0000"
    assert with_cost.json()["meta"]["freshness_at"] == "2026-01-01T00:00:00Z"
    assert "access_type=detail" in caplog.text
    assert "1.0000" not in caplog.text


def test_celery_task_contract_accepts_only_run_id_and_no_payload() -> None:
    assert list(inspect.signature(execute_sync_run.run).parameters) == ["run_id"]
    assert list(inspect.signature(scheduler_tick.run).parameters) == []
    source = inspect.getsource(execute_sync_run.run)
    assert "payload" not in source
    assert "token" not in source.casefold()


def test_trigger_dispatch_failure_returns_safe_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.integration_sync.schemas import RunStatus, SyncRunCreated, TriggerType

    monkeypatch.setattr(
        IntegrationSyncService,
        "create_manual_run",
        lambda self, config_id, payload, actor_ref, request_id, account_refs: SyncRunCreated(
            run_id=SKU_ID,
            trigger_type=TriggerType.MANUAL,
            status=RunStatus.QUEUED,
        ),
    )

    def unavailable(run_id: UUID) -> None:
        del run_id
        raise TaskDispatchError("safe")

    monkeypatch.setattr(
        "app.modules.integration_sync.router.dispatch_sync_run",
        unavailable,
    )
    response = TestClient(_app("integrations:execute")).post(
        f"/api/integrations/sync-configs/{SKU_ID}/run",
        json={"reason": "synthetic"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TASK_DISPATCH_UNAVAILABLE"
    assert "safe" not in response.text
