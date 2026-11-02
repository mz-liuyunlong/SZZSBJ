"""Opt-in Listing page acceptance against a disposable PostgreSQL database."""

import os
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import session as database_session
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import (
    ListingArchiveState,
    ListingGptAnalysisLink,
    ListingManagementCurrentMart,
    ListingWfsFirstStock,
    ProductCustomTag,
    ProductCustomTagAssignment,
)
from app.modules.iam.security import token_hash
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncConfig
from app.modules.integration_sync.wfs_first_stock import observe_first_wfs_stock

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to current head",
)


def test_listing_page_and_real_api_with_isolated_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    monkeypatch.setenv("TEST_DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    database_session.dispose_engine()
    with Session(engine) as session:
        assert not session.scalar(select(ListingManagementCurrentMart.id).limit(1)), (
            "Use a fresh disposable DB"
        )
        # A newly observed Listing starts without a date, then records only the
        # first fresh WFS-positive observation. Existing Listings stay unknown.
        first_identity = {
            "source_account_ref": "synthetic-a",
            "store_id": "synthetic-store",
            "item_id": "SYNTHETIC-LISTING-A2",
            "msku": "SYNTHETIC-LISTING-A2-MSKU",
        }
        observe_first_wfs_stock(
            session,
            **first_identity,
            wfs_quantity=Decimal("0"),
            observed_at_utc=datetime(2026, 10, 13, 15, 50, tzinfo=UTC),
        )
        observe_first_wfs_stock(
            session,
            **first_identity,
            wfs_quantity=Decimal("1"),
            observed_at_utc=datetime(2026, 10, 13, 16, 5, tzinfo=UTC),
        )
        observe_first_wfs_stock(
            session,
            **first_identity,
            wfs_quantity=Decimal("9"),
            observed_at_utc=datetime(2026, 10, 14, 16, 5, tzinfo=UTC),
        )
        first_stock = session.scalar(select(ListingWfsFirstStock))
        assert first_stock is not None
        assert first_stock.launch_date_cn.isoformat() == "2026-10-14"
        assert first_stock.first_wfs_seen_at_utc == datetime(2026, 10, 13, 16, 5, tzinfo=UTC)
        for account, sku in (
            ("synthetic-a", "SYNTHETIC-LISTING-A"),
            ("synthetic-a", "SYNTHETIC-LISTING-A2"),
            ("synthetic-b", "SYNTHETIC-LISTING-B"),
        ):
            session.add(
                ListingManagementCurrentMart(
                    source_account_ref=account,
                    store_id="synthetic-store",
                    item_id=sku,
                    local_sku=sku,
                    msku="SYNTHETIC-LISTING-A2-MSKU" if sku.endswith("A2") else None,
                    listing_status="离线" if sku.endswith("A2") else "在线",
                    wfs_available_quantity=9 if sku.endswith("A2") else 0,
                    calculated_at=datetime.now(UTC),
                )
            )
            if sku in {"SYNTHETIC-LISTING-A", "SYNTHETIC-LISTING-B"}:
                session.add(
                    ProductCustomTag(
                        source_account_ref=account,
                        name="SyntheticTag",
                        color="#1677FF",
                        is_active=False,
                    )
                )
        session.flush()
        active_listing = session.scalar(
            select(ListingManagementCurrentMart).where(
                ListingManagementCurrentMart.item_id == "SYNTHETIC-LISTING-A"
            )
        )
        assert active_listing is not None
        active_listing_id = active_listing.id
        session.add(
            ListingArchiveState(
                listing_id=active_listing_id,
                source_account_ref="synthetic-a",
                store_id="synthetic-store",
                item_id="SYNTHETIC-LISTING-A",
                is_archived=False,
            )
        )
        session.commit()

    _seed_real_iam(engine)
    app = create_app()

    def db_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session

    def seed_cross_page_rows() -> dict[str, int]:
        # Test-only endpoint for adding a second page after the first browser flow.
        with Session(engine) as session:
            session.add_all(
                ListingManagementCurrentMart(
                    source_account_ref="synthetic-a",
                    store_id="synthetic-store",
                    item_id=f"SYNTHETIC-LISTING-Z{index:02d}",
                    local_sku=f"SYNTHETIC-LISTING-Z{index:02d}",
                    listing_status="离线",
                    calculated_at=datetime.now(UTC),
                )
                for index in range(49)
            )
            session.commit()
        return {"seeded": 49}

    app.add_api_route("/__listing_test__/seed_extra", seed_cross_page_rows, methods=["POST"])
    with TestClient(app, headers={"Authorization": "Bearer synthetic-listing-a"}) as client:
        with TestClient(app) as anonymous:
            assert anonymous.get("/api/listings/walmart").status_code == 401
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["data"]["username"] == "synthetic_listing_9277001"
        scoped_b = client.get(
            "/api/listings/walmart",
            headers={"Authorization": "Bearer synthetic-listing-b"},
        )
        assert scoped_b.status_code == 200, scoped_b.text
        assert [row["source_account_ref"] for row in scoped_b.json()["data"]["items"]] == [
            "synthetic-b"
        ]
        listing = client.get("/api/listings/walmart")
        assert listing.status_code == 200, listing.text
        assert listing.json()["meta"]["total"] == 2
        assert {row["local_sku"] for row in listing.json()["data"]["items"]} == {
            "SYNTHETIC-LISTING-A",
            "SYNTHETIC-LISTING-A2",
        }
        batch_search = {
            "filters": {"search_field": "sku"},
            "batch_values": [f"SYNTHETIC-NO-MATCH-{index:04d}-%_'\"" for index in range(999)]
            + ["SYNTHETIC-LISTING-A"],
        }
        batch_rows = client.post("/api/listings/walmart/search", json=batch_search)
        assert batch_rows.status_code == 200, batch_rows.text
        assert batch_rows.json()["meta"]["total"] == 1
        assert [row["local_sku"] for row in batch_rows.json()["data"]["items"]] == [
            "SYNTHETIC-LISTING-A"
        ]
        batch_summary = client.post("/api/listings/walmart/summary/search", json=batch_search)
        assert batch_summary.status_code == 200, batch_summary.text
        assert batch_summary.json()["data"]["total"] == 1
        batch_export = client.post(
            "/api/listings/walmart/export/search",
            json={**batch_search, "columns": ["sku"]},
        )
        assert batch_export.status_code == 200, batch_export.text
        assert "SYNTHETIC-LISTING-A" in batch_export.text
        assert "SYNTHETIC-LISTING-A2" not in batch_export.text
        assert "SYNTHETIC-LISTING-B" not in batch_export.text
        listed_dates = {
            row["local_sku"]: row["launch_date_cn"] for row in listing.json()["data"]["items"]
        }
        assert listed_dates == {
            "SYNTHETIC-LISTING-A": None,
            "SYNTHETIC-LISTING-A2": "2026-10-14",
        }
        assert client.get("/api/listings/walmart/summary").json()["data"]["online"] == 1
        assert (
            client.get("/api/listings/walmart", params={"archive_status": "active"}).json()["meta"][
                "total"
            ]
            == 1
        )
        assert (
            client.get("/api/listings/walmart", params={"archive_status": "unknown"}).json()[
                "meta"
            ]["total"]
            == 1
        )
        pages = [
            client.get(
                "/api/listings/walmart",
                params={
                    "page": number,
                    "page_size": 1,
                    "sort_field": "sku",
                    "sort_order": "desc",
                },
            )
            for number in (1, 2)
        ]
        assert all(page.status_code == 200 for page in pages)
        assert [page.json()["data"]["items"][0]["local_sku"] for page in pages] == [
            "SYNTHETIC-LISTING-A2",
            "SYNTHETIC-LISTING-A",
        ]
        tags = client.get("/api/listings/tags")
        assert tags.status_code == 200, tags.text
        assert len(tags.json()["data"]["items"]) == 1
        assert tags.json()["data"]["items"][0]["is_active"] is False
        export = client.get("/api/listings/walmart/export", params={"columns": "sku"})
        assert export.status_code == 200, export.text
        assert "SYNTHETIC-LISTING-A" in export.text
        assert "SYNTHETIC-LISTING-A2" in export.text
        assert "SYNTHETIC-LISTING-B" not in export.text
        with Session(engine) as session:
            foreign_tag = session.scalar(
                select(ProductCustomTag).where(ProductCustomTag.source_account_ref == "synthetic-b")
            )
            assert foreign_tag is not None
            foreign_id = foreign_tag.id
        denied = client.patch(f"/api/listings/tags/{foreign_id}", json={"is_active": True})
        assert denied.status_code == 422
        invalid_batch = client.post(
            "/api/listings/tags/batch-set",
            json={
                "listing_ids": [str(active_listing_id)],
                "tag_ids": [str(foreign_id)],
                "tag_values": ["SyntheticMustNotBeCreated"],
                "mode": "replace",
            },
        )
        assert invalid_batch.status_code == 422
        with Session(engine) as session:
            assert not session.scalar(select(ProductCustomTagAssignment.id).limit(1))
            assert not session.scalar(
                select(ProductCustomTag.id).where(
                    ProductCustomTag.name == "SyntheticMustNotBeCreated"
                )
            )

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        frontend = Path(__file__).resolve().parents[4] / "frontend"
        playwright = frontend / "node_modules/.bin/playwright"
        assert playwright.is_file()
        browser = subprocess.run(
            [str(playwright), "test", "e2e/listing-live-postgres.spec.ts", "--workers=1"],
            cwd=frontend,
            env={**os.environ, "LISTING_LIVE_API_BASE": f"http://127.0.0.1:{port}"},
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        assert browser.returncode == 0, (browser.stdout + browser.stderr)[-6000:]
        with Session(engine) as session:
            session.execute(
                delete(ListingManagementCurrentMart).where(
                    ListingManagementCurrentMart.item_id.like("SYNTHETIC-LISTING-Z%")
                )
            )
            session.commit()
        with TestClient(app) as viewer_client:
            viewer_headers = {"Authorization": "Bearer synthetic-listing-viewer"}
            assert (
                viewer_client.get("/api/listings/walmart", headers=viewer_headers).status_code
                == 200
            )
            assert (
                viewer_client.post(
                    f"/api/listings/walmart/{active_listing_id}/archive",
                    json={"reason": "Synthetic forbidden write"},
                    headers=viewer_headers,
                ).status_code
                == 403
            )
            assert (
                viewer_client.post(
                    f"/api/listings/walmart/{active_listing_id}/restore",
                    headers=viewer_headers,
                ).status_code
                == 403
            )
            assert (
                viewer_client.put(
                    f"/api/listings/walmart/{active_listing_id}/gpt-analysis",
                    json={"keyword_analysis_url": "https://example.invalid/forbidden"},
                    headers=viewer_headers,
                ).status_code
                == 403
            )
            assert (
                viewer_client.post(
                    "/api/listings/tags/batch-set",
                    json={
                        "listing_ids": [str(active_listing_id)],
                        "tag_ids": [],
                        "mode": "replace",
                    },
                    headers=viewer_headers,
                ).status_code
                == 403
            )
        with Session(engine) as session:
            saved_link = session.scalar(
                select(ListingGptAnalysisLink).where(
                    ListingGptAnalysisLink.listing_id == active_listing_id
                )
            )
            assert saved_link is not None
            assert saved_link.keyword_analysis_url == "https://example.invalid/synthetic-keyword"
            assert saved_link.ad_analysis_url == "https://example.invalid/synthetic-ad"
            archive_state = session.scalar(
                select(ListingArchiveState).where(
                    ListingArchiveState.listing_id == active_listing_id
                )
            )
            assert archive_state is not None
            assert archive_state.is_archived is False
            assert archive_state.archive_reason is None
            assert archive_state.archived_at is not None
            assert archive_state.restored_at is not None
            states = dict(
                session.execute(
                    select(
                        ProductCustomTag.source_account_ref,
                        ProductCustomTag.is_active,
                    )
                ).all()
            )
            assert states == {"synthetic-a": True, "synthetic-b": False}
            valid_tag = session.scalar(
                select(ProductCustomTag).where(ProductCustomTag.source_account_ref == "synthetic-a")
            )
            assert valid_tag is not None
            valid_tag_id = valid_tag.id
            second_store_listing = ListingManagementCurrentMart(
                source_account_ref="synthetic-a",
                store_id="synthetic-other-store",
                item_id="SYNTHETIC-LISTING-A",
                local_sku="SYNTHETIC-LISTING-A",
                listing_status="在线",
                calculated_at=datetime.now(UTC),
            )
            session.add(second_store_listing)
            session.commit()
            second_store_listing_id = second_store_listing.id

        with TestClient(app, headers={"Authorization": "Bearer synthetic-listing-a"}) as client:
            mixed_tag_ids = client.post(
                "/api/listings/tags/batch-set",
                json={
                    "listing_ids": [str(active_listing_id)],
                    "tag_ids": [str(valid_tag_id), str(foreign_id)],
                    "tag_values": ["SyntheticMustNotBeCreated"],
                    "mode": "replace",
                },
            )
            assert mixed_tag_ids.status_code == 422
            with Session(engine) as session:
                assert not session.scalar(select(ProductCustomTagAssignment.id).limit(1))
                assert not session.scalar(
                    select(ProductCustomTag.id).where(
                        ProductCustomTag.name == "SyntheticMustNotBeCreated"
                    )
                )

            shared_item = client.post(
                "/api/listings/tags/batch-set",
                json={
                    "listing_ids": [str(active_listing_id), str(second_store_listing_id)],
                    "tag_ids": [str(valid_tag_id)],
                    "mode": "replace",
                },
            )
            assert shared_item.status_code == 200, shared_item.text
            with Session(engine) as session:
                assignments = session.scalars(select(ProductCustomTagAssignment)).all()
                assert len(assignments) == 1
                assert assignments[0].source_account_ref == "synthetic-a"
                assert assignments[0].item_id == "SYNTHETIC-LISTING-A"
                assert assignments[0].tag_id == valid_tag_id
            refreshed = client.get("/api/listings/walmart")
            assert refreshed.status_code == 200, refreshed.text
            shared_rows = [
                row
                for row in refreshed.json()["data"]["items"]
                if row["item_id"] == "SYNTHETIC-LISTING-A"
            ]
            assert {row["store_id"] for row in shared_rows} == {
                "synthetic-store",
                "synthetic-other-store",
            }
            assert all(row["tags"] == ["SyntheticTag"] for row in shared_rows)

            # Equal SKU sort values must still produce stable, non-overlapping pages.
            sorted_pages = [
                client.get(
                    "/api/listings/walmart",
                    params={"page": page, "page_size": 1, "sort_field": "sku"},
                )
                for page in (1, 2, 3)
            ]
            assert all(response.status_code == 200 for response in sorted_pages)
            paged_ids = [response.json()["data"]["items"][0]["id"] for response in sorted_pages]
            assert len(set(paged_ids)) == 3
            assert set(paged_ids) == {
                str(active_listing_id),
                str(second_store_listing_id),
                next(
                    row["id"]
                    for row in refreshed.json()["data"]["items"]
                    if row["item_id"] == "SYNTHETIC-LISTING-A2"
                ),
            }

            cleared = client.post(
                "/api/listings/tags/batch-set",
                json={
                    "listing_ids": [str(active_listing_id), str(second_store_listing_id)],
                    "mode": "replace",
                },
            )
            assert cleared.status_code == 200, cleared.text
            with Session(engine) as session:
                assert not session.scalar(select(ProductCustomTagAssignment.id).limit(1))
            cleared_rows = client.get("/api/listings/walmart").json()["data"]["items"]
            assert all(
                row["tags"] == [] for row in cleared_rows if row["item_id"] == "SYNTHETIC-LISTING-A"
            )

            archived = client.post(
                f"/api/listings/walmart/{active_listing_id}/archive",
                json={"reason": "Synthetic archived reason"},
            )
            assert archived.status_code == 200, archived.text
            assert archived.json()["data"]["is_archived"] is True
            assert archived.json()["data"]["archive_reason"] == "Synthetic archived reason"
            archived_rows = client.get(
                "/api/listings/walmart", params={"archive_status": "archived"}
            ).json()["data"]["items"]
            assert [row["id"] for row in archived_rows] == [str(active_listing_id)]
            restored = client.post(f"/api/listings/walmart/{active_listing_id}/restore")
            assert restored.status_code == 200, restored.text
            assert restored.json()["data"]["is_archived"] is False
            assert restored.json()["data"]["archive_reason"] is None
            current_row = next(
                row
                for row in client.get("/api/listings/walmart").json()["data"]["items"]
                if row["id"] == str(active_listing_id)
            )
            assert current_row["archive_reason"] is None

            link_payload = {
                "keyword_analysis_url": "https://example.invalid/synthetic-keyword",
                "ad_analysis_url": "https://example.invalid/synthetic-ad",
            }
            saved_link = client.put(
                f"/api/listings/walmart/{active_listing_id}/gpt-analysis",
                json=link_payload,
            )
            assert saved_link.status_code == 200, saved_link.text
            link_read = client.get(f"/api/listings/walmart/{active_listing_id}/gpt-analysis")
            assert link_read.status_code == 200, link_read.text
            assert {key: link_read.json()["data"][key] for key in link_payload} == link_payload
            foreign_read = client.get(
                f"/api/listings/walmart/{active_listing_id}/gpt-analysis",
                headers={"authorization": "Bearer synthetic-listing-b"},
            )
            assert foreign_read.status_code == 404
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        app.dependency_overrides.clear()
        database_session.dispose_engine()
        get_settings.cache_clear()
        engine.dispose()


def _seed_real_iam(engine) -> None:
    """Seed test-only IAM sessions and account scopes in the disposable database."""
    now = datetime.now(UTC)
    manager_role_id = uuid4()
    viewer_role_id = uuid4()
    with Session(engine) as session:
        interface = IntegrationInterface(
            provider="synthetic",
            interface_key="synthetic-listing-scope",
            display_name="Synthetic Listing Scope",
            method="POST",
            endpoint_path="/synthetic/listing-scope",
            request_kind="offset_page",
            handler_key="synthetic-listing-scope",
            contract_version="test",
        )
        session.add(interface)
        session.flush()
        session.add_all(
            IntegrationSyncConfig(interface_id=interface.id, source_account_ref=account)
            for account in ("synthetic-a", "synthetic-b")
        )
        permissions = (
            "page:products:listing-management:view",
            "action:products:listing-management:manage-tags",
            "action:products:listing-management:export",
            "action:products:listing-management:archive",
            "action:products:listing-management:restore",
            "action:products:listing-management:edit-analysis-link",
        )
        for permission in permissions:
            session.execute(
                text(
                    """insert into app_permissions
                       (permission_key, name, group_key, permission_type, risk_level,
                        sort_order, is_active, created_at, updated_at)
                       values (:permission, :permission, 'synthetic', 'legacy', 'normal',
                               0, true, :now, :now)
                       on conflict (permission_key) do nothing"""
                ),
                {"permission": permission, "now": now},
            )
        for role_id, role_key in (
            (manager_role_id, "synthetic-listing-manager"),
            (viewer_role_id, "synthetic-listing-viewer"),
        ):
            session.execute(
                text(
                    """insert into app_roles
                       (id, role_key, name, is_system, created_at, updated_at, version)
                       values (:id, :role_key, :role_key, 0, :now, :now, 1)"""
                ),
                {"id": role_id, "role_key": role_key, "now": now},
            )
        for permission in permissions:
            session.execute(
                text(
                    """insert into app_role_permissions (role_id, permission_key, created_at)
                       values (:role_id, :permission, :now)"""
                ),
                {"role_id": manager_role_id, "permission": permission, "now": now},
            )
        session.execute(
            text(
                """insert into app_role_permissions (role_id, permission_key, created_at)
                   values (:role_id, :permission, :now)"""
            ),
            {"role_id": viewer_role_id, "permission": permissions[0], "now": now},
        )
        for user_id, account, token, role_id in (
            (9277001, "synthetic-a", "synthetic-listing-a", manager_role_id),
            (9277002, "synthetic-b", "synthetic-listing-b", manager_role_id),
            (9277003, "synthetic-a", "synthetic-listing-viewer", viewer_role_id),
        ):
            session.execute(
                text(
                    """insert into app_users
                       (id, username, password_hash, is_active, is_super_admin,
                        display_name, created_at, updated_at)
                       values (:id, :username, 'synthetic-unused', 1, 0,
                               :username, :now, :now)"""
                ),
                {"id": user_id, "username": f"synthetic_listing_{user_id}", "now": now},
            )
            session.execute(
                text(
                    """insert into app_user_roles (user_id, role_id, created_at)
                       values (:user_id, :role_id, :now)"""
                ),
                {"user_id": user_id, "role_id": role_id, "now": now},
            )
            session.execute(
                text(
                    """insert into app_user_data_scopes
                       (user_id, scope_type, scope_value, created_at)
                       values (:user_id, 'source_account', :account, :now)"""
                ),
                {"user_id": user_id, "account": account, "now": now},
            )
            session.execute(
                text(
                    """insert into app_sessions
                       (id, user_id, token_hash, created_at, expires_at, last_seen_at)
                       values (:id, :user_id, :token_hash, :now, :expires_at, :now)"""
                ),
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "token_hash": token_hash(token),
                    "now": now,
                    "expires_at": now + timedelta(hours=1),
                },
            )
        session.commit()
