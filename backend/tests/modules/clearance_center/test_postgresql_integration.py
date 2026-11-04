"""Isolated PostgreSQL acceptance of Listing clearance and governed approval.

Runs only against a disposable CI database created by the dedicated workflow.
No production connection, no external Walmart calls and no mock clearance rows.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.clearance_center.schemas import ApplicationWrite, DecisionWrite, ProgressWrite
from app.modules.clearance_center.service import ClearanceService
from app.modules.data_pages.models import (
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)
from app.modules.integration_sync.dependencies import require_source_account_scope

pytestmark = pytest.mark.skipif(
    os.environ.get("CLEARANCE_CI_TEST") != "1",
    reason="Requires disposable PostgreSQL configured by clearance CI workflow",
)


@pytest.fixture
def clearance_db():
    database_url = os.environ["TEST_DATABASE_URL"]
    assert database_url.startswith("postgresql+psycopg://")
    assert "127.0.0.1" in database_url and "clearance_ci" in database_url
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _seed_listing(
    session: Session,
    *,
    account: str,
    store: str,
    item: str,
    available: int = 12,
    captured_at: datetime | None = None,
) -> str:
    now = datetime.now(UTC)
    listing = ListingManagementCurrentMart(
        id=uuid4(),
        source_account_ref=account,
        platform_code="walmart",
        store_id=store,
        item_id=item,
        msku="SYNTHETIC-MSKU",
        local_sku="SYNTHETIC-SKU",
        title="Isolated clearance test listing",
        fulfillment_type="WFS",
        wfs_available_quantity=Decimal(available),
        sales_7d=Decimal(0),
        sales_14d=Decimal(0),
        sales_30d=Decimal(0),
        listing_start_at_utc=now - timedelta(days=120),
        calculated_at=now,
    )
    snapshot = WalmartListingInventoryDailyFact(
        id=uuid4(),
        snapshot_date_la=now.date(),
        source_account_ref=account,
        store_id=store,
        item_id=item,
        msku="SYNTHETIC-MSKU",
        local_sku="SYNTHETIC-SKU",
        wfs_available_quantity=Decimal(available),
        captured_at=captured_at or now,
    )
    session.add_all([listing, snapshot])
    session.commit()
    return str(listing.id)


def _payload(listing_id: str, qty: int) -> ApplicationWrite:
    return ApplicationWrite(
        listing_id=listing_id,
        target_qty=qty,
        methods=["降价", "广告清货"],
        reason="长期滞销",
        remark="隔离数据库清货闭环测试，不执行任何平台动作",
        source="manual",
    )


def test_real_clearance_listing_application_approval_and_progress(clearance_db: Session) -> None:
    account = "clearance-ci-account"
    allowed = frozenset({account})
    listing_id = _seed_listing(clearance_db, account=account, store="ci-store", item="ci-item")
    _seed_listing(
        clearance_db,
        account=account,
        store="ci-store-other",
        item="ci-item",
        available=0,
    )
    service = ClearanceService(clearance_db)

    candidates = service.list_listings(allowed, eligible_only=True)
    assert candidates["total"] == 1
    assert candidates["items"][0]["listing"]["id"] == listing_id
    assert service.list_listings(frozenset({"not-authorized"}), eligible_only=True)["total"] == 0

    with pytest.raises(ApiError) as exceeded:
        service.submit(_payload(listing_id, 13), allowed, "operator-1")
    assert exceeded.value.status_code == 409

    result = service.submit(_payload(listing_id, 4), allowed, "operator-1")
    assert result["status"] == "pending"
    request_id = UUID(result["request_id"])
    approval_id = UUID(result["approval_id"])
    with pytest.raises(ApiError):
        service.submit(_payload(listing_id, 3), allowed, "operator-1")

    detail = service.request_detail(request_id, allowed)
    assert detail["request"]["target_qty"] == 4
    assert detail["request"]["status"] == "pending"
    assert detail["request"]["methods"] == ["降价", "广告清货"]

    with pytest.raises(ApiError):
        service.decide(
            approval_id,
            DecisionWrite(decision="approved", expected_version=1),
            allowed,
            "operator-1"
        )
    decision = service.decide(
        approval_id,
        DecisionWrite(decision="approved", expected_version=1),
        allowed,
        "reviewer-2",
    )
    assert decision["status"] == "approved"
    with pytest.raises(ApiError):
        service.decide(
            approval_id,
            DecisionWrite(decision="approved", expected_version=1),
            allowed,
            "reviewer-3",
        )

    # A request approved for price reductions and ads cannot report WFS removals.
    with pytest.raises(ApiError):
        service.progress(
            request_id,
            ProgressWrite(sold_qty=0, removed_qty=1, disposed_qty=0, expected_version=2),
            allowed,
            "operator-1",
        )

    finished = service.progress(
        request_id,
        ProgressWrite(sold_qty=4, removed_qty=0, disposed_qty=0, expected_version=2),
        allowed,
        "operator-1",
    )
    assert finished["status"] == "done"
    assert service.request_detail(request_id, allowed)["request"]["status"] == "done"
    approval = clearance_db.execute(
        select(ListingManagementCurrentMart).where(
            ListingManagementCurrentMart.id == UUID(listing_id)
        )
    ).scalar_one()
    assert approval.wfs_available_quantity == 12


def test_stale_or_out_of_scope_listing_cannot_be_applied(clearance_db: Session) -> None:
    allowed = frozenset({"clearance-ci-account"})
    fresh_id = _seed_listing(
        clearance_db,
        account="clearance-ci-account",
        store="ci-store-2",
        item="ci-item-2",
        captured_at=datetime.now(UTC) - timedelta(days=4),
    )
    service = ClearanceService(clearance_db)
    rows = service.list_listings(allowed, eligible_only=True)
    assert all(row["listing"]["id"] != fresh_id for row in rows["items"])

    with pytest.raises(ApiError) as stale:
        service.submit(_payload(fresh_id, 1), allowed, "operator-2")
    assert stale.value.status_code == 409
    with pytest.raises(ApiError) as outside:
        service.submit(_payload(fresh_id, 1), frozenset({"outside"}), "operator-2")
    assert outside.value.status_code == 404


def test_clearance_http_contract_and_unified_approval_routes(clearance_db: Session) -> None:
    account = "clearance-ci-account"
    listing_id = _seed_listing(
        clearance_db, account=account, store="ci-api-store", item="ci-api-item"
    )
    app = create_app()
    identity = {"user_id": "operator-31"}

    def db_provider():
        with Session(clearance_db.get_bind()) as session:
            yield session

    app.dependency_overrides[get_db_session] = db_provider
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id=identity["user_id"], permissions=frozenset({"*"})
    )
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    with TestClient(app) as client:
        eligible = client.get(
            "/api/products/clearance-center/eligible-listings",
            params={"store_id": "ci-api-store"},
        )
        assert eligible.status_code == 200
        data = eligible.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["listing"]["id"] == listing_id

        application = client.post(
            "/api/products/clearance-center/requests",
            json={
                "listing_id": listing_id,
                "target_qty": 3,
                "methods": ["降价", "广告清货"],
                "reason": "库存积压",
                "remark": "CI only, no external platform calls",
                "source": "manual",
            },
        )
        assert application.status_code == 200, application.text
        approval_id = application.json()["data"]["approval_id"]
        identity["user_id"] = "reviewer-32"
        detail = client.get(f"/api/approvals/{approval_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["approval_type"] == "clearance_request"
        assert detail.json()["data"]["current_case"]["request"]["target_qty"] == 3

        approved = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"decision": "approved", "note": "", "expected_version": 1},
        )
        assert approved.status_code == 200, approved.text
        task = client.get(
            "/api/products/clearance-center/requests",
            params={"status": "approved", "store_id": "ci-api-store"},
        )
        assert task.status_code == 200, task.text
        assert task.json()["data"]["total"] == 1
