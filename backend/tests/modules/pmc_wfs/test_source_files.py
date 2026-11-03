"""File-sourced WFS facts (migration 0076, loader, board facts). PostgreSQL opt-in only."""

from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_wfs.board_facts import load_board_facts, source_tables_ready
from app.modules.pmc_wfs.source_loader import SourceLoadError, WfsSourceLoader
from app.modules.pmc_wfs.source_models import (
    SOURCE_FILE_TABLES,
    PmcWfsSourceFile,
    WalmartWfsReceiptOds,
)
from tests.modules.pmc_wfs.schema_support import integration_target

MIGRATION = "20261103_0076_wfs_source_files.py"
STORE = "110000000000000001"


def _opt_in() -> None:
    if os.environ.get("WFS_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required (WFS_LOCAL_INTEGRATION=1)")


def test_migration_0076_matches_orm_metadata():
    """0076 is frozen explicit DDL. It must create exactly what ``source_models`` declares;
    downgrade refuses while any row exists and drops all seven tables once empty."""
    _opt_in()
    from app.db.base import Base
    from tests.modules.pmc_wfs.schema_support import run_migration, table_structure

    register_productlist_sync_models()
    url, database = integration_target()
    token = uuid4().hex[:12]
    mig, orm = f"wfs_mig0076_{token}", f"wfs_orm0076_{token}"
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
            Base.metadata.create_all(
                c, tables=[Base.metadata.tables[name] for name in SOURCE_FILE_TABLES]
            )
        with admin.connect() as c:
            migrated = table_structure(c, mig, SOURCE_FILE_TABLES)
            declared = table_structure(c, orm, SOURCE_FILE_TABLES)
        assert migrated == declared
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(
                text(
                    "INSERT INTO raw_pmc_wfs_source_files (id, source, endpoint, scope_key,"
                    " batch_label, source_path, sha256, byte_size, row_count, loaded_rows,"
                    " is_current, loaded_by, loaded_at) VALUES (gen_random_uuid(), 'zhongyi',"
                    " 'orders_track', 'all', 'fixture', 'x.csv', 'abc', 1, 0, 0, true, 't',"
                    " now())"
                )
            )
        with pytest.raises(RuntimeError, match="retain WFS source evidence"):
            with admin.begin() as c:
                c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
                run_migration(c, MIGRATION, "downgrade")
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(text("DELETE FROM raw_pmc_wfs_source_files"))
            run_migration(c, MIGRATION, "downgrade")
            exists = text("select to_regclass(:n)")
            left = [n for n in SOURCE_FILE_TABLES if c.scalar(exists, {"n": n})]
            assert left == []
    finally:
        with admin.begin() as c:
            for schema in (mig, orm):
                assert schema.startswith("wfs_") and token in schema
                c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture()
def db():
    _opt_in()
    from app.db.base import Base

    url, database = integration_target()
    get_settings.cache_clear()
    register_productlist_sync_models()
    schema = "wfssrc_test_" + uuid4().hex
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
            Base.metadata.create_all(
                c, tables=[Base.metadata.tables[name] for name in SOURCE_FILE_TABLES]
            )
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        with admin.begin() as c:
            assert schema.startswith("wfssrc_test_")
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _daily(root: Path, *, receipt_units: str = "6") -> Path:
    wm = root / "walmart" / STORE
    _csv(
        wm / "shipments.csv",
        [
            {
                "shipmentId": "1000001WFB",
                "status": "RECEIVING_IN_PROGRESS",
                "actualDeliveryDate": "2026-10-20T00:00:00Z",
                "shipmentUnits": "10",
                "receivedUnits": "8",
            }
        ],
    )
    _csv(
        wm / "items.csv",
        [
            {
                "shipmentId": "1000001WFB",
                "gtin": "G1",
                "itemQty": "10",
                "receivedQty": "8",
                "damagedQty": "1",
            }
        ],
    )
    _csv(
        wm / "inventory_log.csv",
        [
            {
                "shipmentId": "1000001WFB",
                "gtin": "G1",
                "transactionType": "Receipt",
                "transactionTime": "2026-10-22T03:00:00Z",
                "changedUnits": receipt_units,
            },
            {
                "shipmentId": "1000001WFB",
                "gtin": "G1",
                "transactionType": "Receipt",
                "transactionTime": "2026-10-23T03:00:00Z",
                "changedUnits": "2",
            },
            {
                "shipmentId": "",
                "gtin": "G1",
                "transactionType": "Ship",
                "transactionTime": "2026-10-24T03:00:00Z",
                "changedUnits": "-1",
            },
        ],
    )
    _csv(
        root / "zhongyi" / "orders_summary.csv",
        [{"number": "ZY1", "customerNumber": "1000001WFB", "status": "签收"}],
    )
    _csv(
        root / "zhongyi" / "orders_track.csv",
        [
            {"orderNumber": "ZY1", "trackTime": "2026-10-01 08:00:00", "name": "已开船"},
            {"orderNumber": "ZY1", "trackTime": "2026-10-19 22:00:00", "name": "签收完成"},
        ],
    )
    _csv(
        root / "lingxing" / "logistics_channels.csv",
        [{"channel_id": "11918", "channel_name": "WFS-FedEx", "raw_json": "{}"}],
    )
    return root


def test_loader_is_idempotent_and_feeds_board_facts(db, tmp_path):
    assert source_tables_ready(db)
    daily = _daily(tmp_path / "20261102")
    loaded = WfsSourceLoader(db, actor="test", batch_label="20261102").load_directory(daily)
    assert [(f.endpoint, f.loaded_rows, f.skipped) for f in loaded] == [
        ("inbound_shipments", 1, False),
        ("inbound_shipment_items", 1, False),
        ("inventory_log", 2, False),
        ("orders_summary", 1, False),
        ("orders_track", 2, False),
        ("logistics_channels", 1, False),
    ]
    again = WfsSourceLoader(db, actor="test", batch_label="20261102").load_directory(daily)
    assert all(f.skipped for f in again)
    assert db.scalar(select(func.count()).select_from(PmcWfsSourceFile)) == 6

    facts = load_board_facts(db)
    wm = facts.walmart
    assert wm.signed == {"1000001WFB": date(2026, 10, 20)}
    assert wm.first_receipt["1000001WFB"] == date(2026, 10, 22)
    assert wm.last_receipt["1000001WFB"] == date(2026, 10, 23)
    assert wm.receipt_units == {"1000001WFB": 8}
    assert wm.receipt_units_by_gtin == {"1000001WFB": {"G1": 8}}
    assert wm.item_received == {"1000001WFB": {"G1": 8}}
    assert wm.item_damaged == {"1000001WFB": {"G1": 1}}
    assert facts.channel_names == {"11918": "WFS-FedEx"}
    assert facts.carrier_number_by_customer == {"1000001WFB": "ZY1"}
    assert facts.carrier_delivered_by_customer == {"1000001WFB": "2026-10-19 22:00"}
    assert facts.carrier_by_number["ZY1"].delivered == date(2026, 10, 19)

    # A changed file becomes the current one; the old file stays for audit.
    changed = _daily(tmp_path / "20261103", receipt_units="7")
    WfsSourceLoader(db, actor="test", batch_label="20261103").load_directory(changed)
    current = db.scalars(
        select(PmcWfsSourceFile).where(
            PmcWfsSourceFile.endpoint == "inventory_log", PmcWfsSourceFile.is_current.is_(True)
        )
    ).all()
    assert [f.batch_label for f in current] == ["20261103"]
    assert db.scalar(select(func.count()).select_from(WalmartWfsReceiptOds)) == 4
    assert load_board_facts(db).walmart.receipt_units == {"1000001WFB": 9}


def test_loader_refuses_symlinked_root(db, tmp_path):
    real = _daily(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(SourceLoadError, match="WFS_SOURCE_ROOT_INVALID"):
        WfsSourceLoader(db, actor="test", batch_label="x").load_directory(link)
