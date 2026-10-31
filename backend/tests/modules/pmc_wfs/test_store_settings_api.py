"""WFS settings · store settings API on the local PostgreSQL dev DB (cloned schema)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.dependencies import require_source_account_scope
from scripts.wfs_pending_local_schema import local_url

CLONED_TABLES = ("dim_lingxing_stores", "ops_wfs_store_settings")


@pytest.fixture(scope="module")
def engine():
    url = local_url()
    get_settings.cache_clear()
    schema = "wfssettings_test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as c:
        assert c.scalar(text("select current_database()")) == "szzsbj_dev"
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_engine = create_engine(url, hide_parameters=True)

    @event.listens_for(db_engine, "connect")
    def set_path(conn, _):
        with conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()

    try:
        register_productlist_sync_models()
        with db_engine.begin() as c:
            for name in CLONED_TABLES:
                assert c.scalar(text("select to_regclass(:n)"), {"n": f"public.{name}"}), name
                c.execute(text(f'CREATE TABLE "{name}" (LIKE public."{name}" INCLUDING ALL)'))
        yield db_engine
    finally:
        db_engine.dispose()
        assert schema.startswith("wfssettings_test_") and len(schema) == 49
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def db(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        with Session(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
        transaction.rollback()


def _store(db, account, store_id, name):
    db.add(
        LingxingStoreDimension(
            source_account_ref=account,
            platform_code_raw="walmart",
            store_id=store_id,
            store_name=name,
            synced_at=datetime.now(UTC),
        )
    )
    db.flush()


def _client(app, db, account, permissions):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    actor = Principal(user_id="fixture-user", permissions=frozenset(permissions))
    app.dependency_overrides[get_optional_principal] = lambda: actor
    return TestClient(app)


def test_list_then_upsert_then_conflicts(db, monkeypatch):
    monkeypatch.delenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", raising=False)
    account = "wfs-settings-" + uuid4().hex
    _store(db, account, "110711149920800256", "HK2614-李镜麟(凡米智航）")
    _store(db, account, "110711149541688320", "HK2613-李思成(拓美恒）")
    app = create_app()
    with _client(app, db, account, {"*"}) as client:
        listed = client.get("/api/pmc/wfs/settings/stores")
        assert listed.status_code == 200, listed.text
        items = listed.json()["data"]["items"]
        assert [i["suggested_code"] for i in items] == ["HK2613", "HK2614"]
        assert all(i["mapping_state"] == "unset" and not i["its_enabled"] for i in items)

        body = {
            "source_account_ref": account,
            "walmart_store_code": "HK2614",
            "its_enabled": True,
            "creation_enabled": True,
            "note": "Rocky: 八店均有 ITS",
        }
        saved = client.put("/api/pmc/wfs/settings/stores/110711149920800256", json=body)
        assert saved.status_code == 200, saved.text
        data = saved.json()["data"]
        assert data["walmart_store_code"] == "HK2614" and data["its_enabled"] is True
        assert data["actor_uid"] == "fixture-user" and data["mapping_state"] == "unreviewed"

        # Same code for a different store is refused.
        dup = client.put("/api/pmc/wfs/settings/stores/110711149541688320", json=body)
        assert dup.status_code == 409 and dup.json()["error"]["code"] == "WFS_STORE_CODE_TAKEN"
        # Unknown store in this account -> 404.
        missing = client.put("/api/pmc/wfs/settings/stores/999", json=body)
        assert missing.status_code == 404
        # Bad code format -> 422 from the schema.
        bad = client.put(
            "/api/pmc/wfs/settings/stores/110711149541688320",
            json={**body, "walmart_store_code": "US1"},
        )
        assert bad.status_code == 422

    # Reviewed server map agreeing -> ok; disagreeing -> conflict.
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", '{"110711149920800256": "HK2614"}')
    with _client(app, db, account, {"*"}) as client:
        items = client.get("/api/pmc/wfs/settings/stores").json()["data"]["items"]
        by_id = {i["store_id"]: i for i in items}
        assert by_id["110711149920800256"]["mapping_state"] == "ok"
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", '{"110711149920800256": "HK2615"}')
    with _client(app, db, account, {"*"}) as client:
        items = client.get("/api/pmc/wfs/settings/stores").json()["data"]["items"]
        assert {i["store_id"]: i["mapping_state"] for i in items}["110711149920800256"] == (
            "conflict"
        )
    # View-only principal cannot write (permission check happens before any scope lookup).
    with _client(app, db, account, {"page:pmc:wfs:view"}) as client:
        denied = client.put(
            "/api/pmc/wfs/settings/stores/110711149920800256",
            json={
                "source_account_ref": account,
                "walmart_store_code": "HK2614",
                "its_enabled": False,
                "creation_enabled": False,
            },
        )
        assert denied.status_code == 403
