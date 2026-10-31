"""Opt-in Listing page acceptance against a disposable PostgreSQL database."""

import os
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import (
    ListingArchiveState,
    ListingManagementCurrentMart,
    ProductCustomTag,
)
from app.modules.integration_sync.dependencies import require_source_account_scope

pytestmark = pytest.mark.skipif(
    not os.getenv("LISTING_LIVE_TEST_DATABASE_URL"),
    reason="Requires a disposable PostgreSQL database migrated to 0070",
)


def test_listing_page_and_real_api_with_isolated_postgres() -> None:
    url = make_url(os.environ["LISTING_LIVE_TEST_DATABASE_URL"])
    assert os.getenv("APP_ENV") == "test"
    assert url.database and url.database.startswith("pr277_listing_")
    assert url.query.get("host", "").startswith("/tmp/szzsbj-pr277-pg.")
    engine = create_engine(url)
    with Session(engine) as session:
        assert not session.scalar(select(ListingManagementCurrentMart.id).limit(1)), (
            "Use a fresh disposable DB"
        )
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
        session.add(
            ListingArchiveState(
                listing_id=active_listing.id,
                source_account_ref="synthetic-a",
                store_id="synthetic-store",
                item_id="SYNTHETIC-LISTING-A",
                is_archived=False,
            )
        )
        session.commit()

    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="1",
        permissions=frozenset(
            {
                "page:products:listing-management:view",
                "action:products:listing-management:manage-tags",
                "action:products:listing-management:export",
            }
        ),
    )

    def account_scope(request: Request) -> frozenset[str]:
        account = (
            "synthetic-b"
            if request.headers.get("authorization") == "Bearer synthetic-listing-b"
            else "synthetic-a"
        )
        return frozenset({account})

    app.dependency_overrides[require_source_account_scope] = account_scope

    def db_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session
    with TestClient(app) as client:
        listing = client.get("/api/listings/walmart")
        assert listing.status_code == 200, listing.text
        assert listing.json()["meta"]["total"] == 2
        assert {row["local_sku"] for row in listing.json()["data"]["items"]} == {
            "SYNTHETIC-LISTING-A",
            "SYNTHETIC-LISTING-A2",
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
            states = dict(
                session.execute(
                    select(
                        ProductCustomTag.source_account_ref,
                        ProductCustomTag.is_active,
                    )
                ).all()
            )
            assert states == {"synthetic-a": True, "synthetic-b": False}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        app.dependency_overrides.clear()
        engine.dispose()
