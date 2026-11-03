"""WFS settings (PRP pmc-wfs-settings PR-S2, migration 0077). PostgreSQL opt-in only."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_wfs.lingxing_models import WfsBoardPublication, WfsShipmentBoardRow
from app.modules.pmc_wfs.settings_models import SETTINGS_TABLES
from app.modules.pmc_wfs.settings_service import parse_fc_address
from app.modules.pmc_wfs.source_models import SOURCE_FILE_TABLES
from tests.modules.pmc_wfs.schema_support import integration_target, run_migration

MIGRATION = "20261103_0077_wfs_settings.py"
ACCOUNT = "acct-wfs-settings"
READ = "page:pmc:wfs:view"
MANAGE = "action:pmc:wfs-settings:manage"
BOARD_TABLES = ("gov_wfs_board_publications", "mart_wfs_shipment_board")


def _opt_in() -> None:
    if os.environ.get("WFS_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required (WFS_LOCAL_INTEGRATION=1)")


def test_parse_fc_address() -> None:
    assert parse_fc_address("1 Main St, Mira Loma, CA, 91752, US") == ("Mira Loma", "CA", "91752")
    assert parse_fc_address("only line") == (None, None, None)
    assert parse_fc_address(None) == (None, None, None)


def test_migration_0077_matches_orm_metadata():
    """0077 is frozen explicit DDL equal to ``settings_models``; it seeds version 1 with the
    11 8088 rows; downgrade refuses once a saved setting exists and drops all five once not."""
    _opt_in()
    from tests.modules.pmc_wfs.schema_support import table_structure

    register_productlist_sync_models()
    url, database = integration_target()
    token = uuid4().hex[:12]
    mig, orm = f"wfs_mig0077_{token}", f"wfs_orm0077_{token}"
    admin = create_engine(url, hide_parameters=True)
    try:
        with admin.begin() as c:
            assert c.scalar(text("select current_database()")) == database
            for schema in (mig, orm):
                c.execute(text(f'CREATE SCHEMA "{schema}"'))
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            run_migration(c, MIGRATION)
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{orm}"'))
            Base.metadata.create_all(c, tables=[Base.metadata.tables[n] for n in SETTINGS_TABLES])
        with admin.connect() as c:
            assert table_structure(c, mig, SETTINGS_TABLES) == table_structure(
                c, orm, SETTINGS_TABLES
            )
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            assert c.scalar(text("select count(*) from ref_wfs_rule_settings")) == 11
            assert (
                c.scalar(text("select count(*) from ref_wfs_rule_settings where not decided")) == 5
            )
            c.execute(
                text(
                    "INSERT INTO ref_wfs_fc_regions (fc, region, updated_by, updated_at)"
                    " VALUES ('LAX9', '美西', 't', now())"
                )
            )
        with pytest.raises(RuntimeError, match="keep WFS settings history"):
            with admin.begin() as c:
                c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
                run_migration(c, MIGRATION, "downgrade")
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(text("DELETE FROM ref_wfs_fc_regions"))
            run_migration(c, MIGRATION, "downgrade")
        with admin.connect() as c:
            left = c.scalar(
                text("select count(*) from information_schema.tables where table_schema = :s"),
                {"s": mig},
            )
            assert left == 0
    finally:
        with admin.begin() as c:
            for schema in (mig, orm):
                assert schema.startswith("wfs_") and token in schema
                c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture()
def db():
    _opt_in()
    url, database = integration_target()
    get_settings.cache_clear()
    register_productlist_sync_models()
    schema = "wfsset_test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as c:
        assert c.scalar(text("select current_database()")) == database
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def set_path(conn, _):
        with conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()

    try:
        with engine.begin() as c:
            run_migration(c, MIGRATION)
            Base.metadata.create_all(
                c,
                tables=[Base.metadata.tables[n] for n in (*SOURCE_FILE_TABLES, *BOARD_TABLES)],
            )
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        with admin.begin() as c:
            assert schema.startswith("wfsset_test_")
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _client(db, *permissions: str, accounts=frozenset({ACCOUNT})) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=frozenset(permissions)
    )
    app.dependency_overrides[require_source_account_scope] = lambda: accounts
    app.dependency_overrides[get_db_session] = lambda: db
    return TestClient(app)


def _ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is True
    return body["data"]


def _board(db, fcs: dict[str, str]) -> None:
    pub = uuid4()
    db.add(
        WfsBoardPublication(
            id=pub,
            source_account_ref=ACCOUNT,
            status="published",
            is_current=True,
            cargo_run_id=uuid4(),
            coverage_start=date(2026, 6, 1),
            coverage_end=date(2026, 11, 2),
            source_observed_at=datetime.now(UTC),
            builder_version="wfs_board.v1",
            quality_report={},
        )
    )
    db.flush()
    for i, (fc, address) in enumerate(fcs.items()):
        db.add(
            WfsShipmentBoardRow(
                publication_id=pub,
                source_account_ref=ACCOUNT,
                cargo_id=f"C{i}",
                logistics_code=fc,
                sku_count=1,
                shipping_codes=[],
                logistics_numbers=[],
                payload_json={"cargo": {"distribution_addresses": address}},
            )
        )
    db.commit()


def test_rules_seed_versions_and_effective_date(db):
    client = _client(db, READ, MANAGE)
    rules = _ok(client.get("/api/pmc/wfs/settings/rules"))
    assert rules["version"]["version_no"] == 1
    assert len(rules["rows"]) == 11 and rules["sample_rows"] == 5
    by_key = {r["rule_key"]: r for r in rules["rows"]}
    assert by_key["deliveredNotSigned"]["days"] == 3
    assert by_key["etaOverdue"]["decided"] is False

    rows = rules["rows"]
    rows[0]["days"] = 4
    past = (date.today() - timedelta(days=1)).isoformat()
    resp = client.post(
        "/api/pmc/wfs/settings/rules/versions",
        json={"effective_date": past, "reason": "测试过去日期", "rows": rows},
    )
    assert resp.status_code == 422
    future = date.today() + timedelta(days=3)
    created = _ok(
        client.post(
            "/api/pmc/wfs/settings/rules/versions",
            json={"effective_date": future.isoformat(), "reason": "测试新版本", "rows": rows},
        ),
        201,
    )
    assert created["version"]["version_no"] == 2
    assert created["version"]["created_by"] == "synthetic-user"
    today = _ok(client.get("/api/pmc/wfs/settings/rules"))
    assert today["version"]["version_no"] == 1
    later = _ok(client.get("/api/pmc/wfs/settings/rules", params={"at": future.isoformat()}))
    assert later["version"]["version_no"] == 2 and later["rows"][0]["days"] == 4
    early = _ok(client.get("/api/pmc/wfs/settings/rules", params={"at": "2026-01-01"}))
    assert early["version"]["version_no"] == 1
    versions = _ok(client.get("/api/pmc/wfs/settings/rules/versions"))["items"]
    assert [v["version_no"] for v in versions] == [2, 1]
    changes = _ok(client.get("/api/pmc/wfs/settings/changes", params={"entity": "rules"}))
    assert changes["total"] == 1 and changes["items"][0]["reason"] == "测试新版本"


def test_fc_regions_default_by_state_then_saved(db):
    _board(
        db,
        {
            "LAX9T": "1 A St, Mira Loma, CA, 91752, US",
            "ATL2": "2 B Rd, Atlanta, GA, 30336, US",
        },
    )
    client = _client(db, READ, MANAGE)
    items = {i["fc"]: i for i in _ok(client.get("/api/pmc/wfs/settings/fc-regions"))["items"]}
    assert items["LAX9T"]["region"] == "美西" and items["LAX9T"]["region_source"] == "state"
    assert items["LAX9T"]["zip"] == "91752" and items["ATL2"]["state"] == "GA"
    saved = _ok(
        client.put(
            "/api/pmc/wfs/settings/fc-regions/ATL2",
            json={"region": "美中", "reason": "测试改地区"},
        )
    )
    assert saved["region"] == "美中" and saved["region_source"] == "saved"
    resp = client.put(
        "/api/pmc/wfs/settings/fc-regions/NOPE1", json={"region": "美西", "reason": "不存在"}
    )
    assert resp.status_code == 404
    resp = client.put(
        "/api/pmc/wfs/settings/fc-regions/ATL2", json={"region": "欧洲", "reason": "非法值"}
    )
    assert resp.status_code == 422


def test_creation_defaults_and_scope(db):
    client = _client(db, READ, MANAGE)
    path = "/api/pmc/wfs/settings/creation-defaults"
    first = _ok(client.get(path, params={"source_account_ref": ACCOUNT}))
    assert first["saved"] is False and first["pallet_boxes"] == 16 and first["transport"] == "LTL"
    body = {
        "source_account_ref": ACCOUNT,
        "transport": "FTL",
        "ship_date_offset": 10,
        "pallet_boxes": 20,
        "mixed_boxes": 1,
        "carrier_opt": "wm",
        "reason": "测试默认值",
    }
    saved = _ok(client.put(path, json=body))
    assert saved["saved"] is True and saved["pallet_boxes"] == 20
    assert client.put(path, json={**body, "pallet_boxes": 0}).status_code == 422
    assert client.get(path, params={"source_account_ref": "other"}).status_code == 403
    assert _ok(client.get(path))["source_account_ref"] == ACCOUNT  # single account in scope
    two = _client(db, READ, accounts=frozenset({ACCOUNT, "other"}))
    assert two.get(path).status_code == 422
    log = _ok(client.get("/api/pmc/wfs/settings/changes"))["items"]
    assert log[0]["entity"] == "creation_defaults" and log[0]["before"] is None


def test_logistics_channels_empty_until_loaded(db):
    data = _ok(_client(db, READ).get("/api/pmc/wfs/settings/logistics-channels"))
    assert data == {"items": [], "loaded": False}


def test_writes_need_manage_permission(db):
    client = _client(db, READ)
    rules = _ok(client.get("/api/pmc/wfs/settings/rules"))
    resp = client.post(
        "/api/pmc/wfs/settings/rules/versions",
        json={
            "effective_date": (date.today() + timedelta(days=1)).isoformat(),
            "reason": "无权限",
            "rows": rules["rows"],
        },
    )
    assert resp.status_code == 403
    assert _client(db).get("/api/pmc/wfs/settings/rules").status_code == 403
