"""Shipment board M2: Lingxing-published cargos joined with creation facts.

Runs against the local PostgreSQL dev database in a process-owned schema that clones only the
tables this board reads. It does not depend on the WFS draft tables, which exist only through
``scripts/wfs_pending_local_schema.py`` and are not part of the Alembic chain.
"""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication, DomesticInboundBoard
from app.modules.pmc_domestic.packing_models import PackingOrder, now
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.lingxing_models import WfsBoardPublication, WfsShipmentBoardRow
from app.modules.pmc_wfs.shipment_board_schemas import ShipmentBoardQuery
from app.modules.pmc_wfs.shipment_board_service import ShipmentBoardService
from tests.modules.pmc_wfs.schema_support import (
    ensure_manual_approval_columns,
    integration_target,
)

T0 = datetime(2026, 10, 16, 7, 23, 28, tzinfo=UTC)

# Cloned structure only (LIKE ... INCLUDING ALL): no foreign keys, no business rows.
CLONED_TABLES = (
    "dim_lingxing_stores",
    "gov_domestic_board_publications",
    "mart_domestic_inbound_batch_board",
    "ops_domestic_packing_orders",
    "ops_wfs_creation_operations",
    "ops_wfs_creation_tickets",
    "ops_wfs_box_holds",
    "evt_wfs_creation_events",
    "gov_wfs_board_publications",
    "mart_wfs_shipment_board",
    "ops_wfs_exception_cases",
    "evt_wfs_exception_detections",
    "evt_wfs_exception_actions",
)


@pytest.fixture(scope="module")
def engine():
    # Same opt-in pattern as PACKING_LOCAL_INTEGRATION: these tests create a throwaway
    # schema inside the verified local development database, which CI does not have.
    if os.environ.get("WFS_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required (WFS_LOCAL_INTEGRATION=1)")
    url, database = integration_target()
    get_settings.cache_clear()
    schema = "wfsboard_test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as c:
        assert c.scalar(text("select current_database()")) == database
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_engine = create_engine(url, hide_parameters=True)

    @event.listens_for(db_engine, "connect")
    def set_path(conn, _):
        # No public fallback: a missing fixture table must fail, never read business data.
        with conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()

    try:
        register_productlist_sync_models()
        with db_engine.begin() as c:
            for name in CLONED_TABLES:
                assert c.scalar(text("select to_regclass(:n)"), {"n": f"public.{name}"}), name
                c.execute(text(f'CREATE TABLE "{name}" (LIKE public."{name}" INCLUDING ALL)'))
            # The board reads whole WfsCreation rows; add 0073's columns if the
            # development DB predates them.
            ensure_manual_approval_columns(c)
        yield db_engine
    finally:
        db_engine.dispose()
        assert schema.startswith("wfsboard_test_") and len(schema) == 46
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


def _seed_order(db):
    """Minimal approved packing order the creation facts point at (mirrors test_pending.seed)."""
    account = "wfs-board-fixture-" + uuid4().hex
    pub = DomesticBoardPublication(
        id=uuid4(),
        source_account_ref=account,
        source_warehouse_id="16168",
        status="published",
        is_current=True,
        batch_run_id=uuid4(),
        statement_run_ids=[],
        coverage_start=date(2026, 10, 1),
        coverage_end=date(2026, 10, 23),
        source_observed_at=now(),
        builder_version="fixture",
        quality_report={},
    )
    db.add(pub)
    db.flush()
    board = DomesticInboundBoard(
        id=uuid4(),
        publication_id=pub.id,
        source_account_ref=account,
        source_warehouse_id="16168",
        inbound_order_sn="IB-WFS-BOARD-TEST",
        sku="TEST-SKU",
        store_id="fixture-store",
        attribution_key="fixture-store",
        balance_num=100,
        arrival_business_date=date(2026, 10, 20),
        payload_json={"available_good_num": 100},
    )
    db.add(board)
    db.flush()
    oid = uuid4()
    order = PackingOrder(
        id=oid,
        source_account_ref=account,
        warehouse_id="16168",
        candidate_id=oid,
        inbound_order_sn=board.inbound_order_sn,
        sku=board.sku,
        store_id="fixture-store",
        item_id="123456",
        pk="PK-" + oid.hex[:20],
        qty=10,
        customs_value=False,
        customs_src="default",
        is_test=True,
        business_test=True,
        status="approved",
        version=1,
        source_publication_id=pub.id,
        source_board_id=board.id,
        snapshot_json={
            "id": str(oid),
            "sku": board.sku,
            "product_name": "测试商品",
            "store_id": "fixture-store",
            "store_name": "测试店",
            "item_id": "123456",
            "gtin": "00000000000001",
            "msku": "TEST-MSKU",
        },
        actor_uid="fixture",
    )
    db.add(order)
    db.flush()
    return account, order


def _seed_shipment(db, account, order, shipment_id="WFS-TEST-001"):
    op_id = uuid4()
    ticket_id = uuid4()
    snap = {
        "its": False,
        "order": {
            "pk": order.pk,
            "sku": order.sku,
            "store_name": "测试店",
            "item_id": order.item_id,
            "gtin": order.snapshot_json.get("gtin"),
            "msku": order.snapshot_json.get("msku"),
            "business_test": order.business_test,
        },
    }
    db.add(
        WfsCreation(
            id=op_id,
            order_id=order.id,
            source_account_ref=account,
            store_id=order.store_id,
            idempotency_key=uuid4(),
            request_hash="abc",
            snapshot=snap,
            actor_uid="fixture",
            state="SUCCEEDED",
            # Any state past AWAITING_APPROVAL carries the written approval (0073 CHECK).
            approval_ref="fixture-approval:board",
            approved_by="fixture-approver",
            approved_at=now(),
        )
    )
    db.add(
        WfsCreationTicket(
            id=ticket_id,
            operation_id=op_id,
            number=1,
            state="SUCCEEDED",
            allocation={"number": 1, "boxes": 2, "units": 8, "ranges": []},
            result={"labels": {shipment_id: {"state": "READY"}}},
        )
    )
    db.flush()
    return ticket_id


def _seed_board(db, account, order, *, cargo_code, store_id, status=2, goods=None):
    pub_id = uuid4()
    db.add(
        WfsBoardPublication(
            id=pub_id,
            source_account_ref=account,
            status="published",
            is_current=True,
            cargo_run_id=uuid4(),
            shipping_run_id=uuid4(),
            coverage_start=date(2026, 6, 1),
            coverage_end=date(2026, 10, 30),
            source_observed_at=datetime.now(UTC),
            builder_version="wfs_board.v1",
            quality_report={"rows": 1},
        )
    )
    goods = goods or [
        {
            "msku": order.snapshot_json.get("msku"),
            "sku": order.sku,
            "product_name": "测试商品",
            "gtin": order.snapshot_json.get("gtin"),
            "declare_num": 40,
            "shipments_num": 40,
            "received_num": 38,
            "damaged_qty": 2,
        }
    ]
    db.add(
        WfsShipmentBoardRow(
            publication_id=pub_id,
            id=uuid4(),
            source_account_ref=account,
            cargo_id="900001",
            cargo_code=cargo_code,
            in_bound_order_id=f"PMC-{cargo_code}",
            store_id=store_id,
            store_name="CN0001-测试店",
            status=status,
            status_name="RECEIVING_IN_PROGRESS",
            cargo_sync_status="已申报",
            logistics_code="LAX2T",
            cargo_created_at=T0,
            cargo_updated_at=T0,
            to_await_at=T0,
            to_receive_at=T0,
            declared_units=40,
            shipped_units=40,
            received_units=38,
            damaged_units=2,
            sku_count=1,
            shipping_codes=["SP202610160010009"],
            shipping_status="已发货",
            warehouse_id="16168",
            actual_delivery_date=date(2026, 10, 18),
            arrival_date=None,
            expected_arrival_date=date(2026, 11, 5),
            logistics_numbers=["ZY010009"],
            payload_json={
                "cargo": {"creator": "运营A", "distribution_addresses": "1 Test Ave"},
                "goods": goods,
                "shipping_lists": [{"shipping_code": "SP202610160010009"}],
            },
        )
    )
    db.flush()
    return pub_id


def test_creation_only_row_is_pending_until_lingxing_sees_it(db):
    account, order = _seed_order(db)
    ticket_id = _seed_shipment(db, account, order)
    svc = ShipmentBoardService(db, frozenset({account}), None)

    listed = svc.list(ShipmentBoardQuery())

    assert listed.total == 1
    row = listed.items[0]
    assert row.source == "creation_only"
    assert row.id == f"cr:{ticket_id}:WFS-TEST-001"
    assert row.shipment_id == "WFS-TEST-001"
    assert row.label_state == "READY"
    assert row.lingxing_sync_status == "PENDING"
    assert row.status_label == "待领星同步"
    assert listed.freshness.stale is True and listed.freshness.publication_id is None
    detail = svc.detail(row.id)
    assert detail.pk == order.pk and detail.lingxing_note
    summary = svc.summary(ShipmentBoardQuery())
    assert summary.test == 1 and summary.pending_lingxing_sync == 1 and summary.by_status == {}


def test_lingxing_row_links_creation_and_exposes_fulfillment(db):
    account, order = _seed_order(db)
    ticket_id = _seed_shipment(db, account, order, shipment_id="3292441WFB")
    pub_id = _seed_board(db, account, order, cargo_code="3292441WFB", store_id=order.store_id)
    svc = ShipmentBoardService(db, frozenset({account}), None)

    listed = svc.list(ShipmentBoardQuery())

    assert listed.total == 1
    row = listed.items[0]
    assert row.source == "lingxing" and row.id == f"lx:{pub_id}:900001"
    assert row.lingxing_sync_status == "SYNCED" and row.status_label == "收货中"
    assert row.ticket_id == ticket_id and row.label_state == "READY" and row.pk == order.pk
    assert row.declared_units == 40 and row.received_units == 38 and row.damaged_units == 2
    assert row.actual_delivery_date == date(2026, 10, 18)
    assert row.shipping_codes == ["SP202610160010009"]
    assert row.created_at == T0
    assert listed.freshness.stale is False and listed.freshness.publication_id == pub_id

    detail = svc.detail(row.id)
    assert [g.received_num for g in detail.goods] == [38]
    assert detail.creator == "运营A" and detail.lingxing_note is None
    assert detail.allocation == {"number": 1, "boxes": 2, "units": 8, "ranges": []}

    summary = svc.summary(ShipmentBoardQuery())
    assert summary.total == 1 and summary.pending_lingxing_sync == 0
    assert summary.by_status == {"2": 1}

    # 8088 产品维度 counts only items with a Walmart Item ID that have shipped out; this seed has
    # neither (no listing row, no derived facts), so it stays out of the product view.
    assert svc.products(ShipmentBoardQuery()).total == 0
    assert row.arrival_bucket == "none" and row.exception_types == []

    assert svc.list(ShipmentBoardQuery(status=3)).total == 0
    assert svc.list(ShipmentBoardQuery(sync="PENDING")).total == 0
    assert svc.list(ShipmentBoardQuery(keyword="SP2026", keyword_field="shipping")).total == 1
    assert svc.list(ShipmentBoardQuery(keyword="PMC-3292", keyword_field="inbound")).total == 1


def test_keyword_filter(db):
    account, order = _seed_order(db)
    _seed_shipment(db, account, order)
    svc = ShipmentBoardService(db, frozenset({account}), None)
    q = ShipmentBoardQuery(keyword="WFS-TEST", keyword_field="shipment")
    assert svc.list(q).total == 1
    assert svc.list(ShipmentBoardQuery(keyword="no-match", keyword_field="shipment")).total == 0


def test_products_skip_cancelled_cargos(db):
    account, order = _seed_order(db)
    _seed_board(db, account, order, cargo_code="CANCELLED1", store_id=order.store_id, status=4)
    svc = ShipmentBoardService(db, frozenset({account}), None)

    assert svc.list(ShipmentBoardQuery()).total == 1
    assert svc.list(ShipmentBoardQuery()).items[0].status_label == "已取消"
    assert svc.products(ShipmentBoardQuery()).total == 0


BOARD_TABLES = (
    "ods_lingxing_wfs_cargos",
    "ods_lingxing_wfs_cargo_goods",
    "ods_lingxing_wfs_shipping_lists",
    "gov_wfs_board_publications",
    "mart_wfs_shipment_board",
)


def test_migration_0071_matches_orm_metadata():
    """282-03: migration 0071 is frozen explicit DDL (no model import). It must create exactly
    what the ORM models declare (columns, types, nullability, PK / unique / FK + ON DELETE /
    check names, indexes incl. the partial unique index); downgrade refuses while any row
    exists and drops all five tables once they are empty."""
    if os.environ.get("WFS_LOCAL_INTEGRATION") != "1":
        pytest.skip("explicit local integration opt-in required (WFS_LOCAL_INTEGRATION=1)")
    from app.db.base import Base
    from tests.modules.pmc_wfs.schema_support import run_migration, table_structure

    register_productlist_sync_models()
    url, database = integration_target()
    token = uuid4().hex[:12]
    mig, orm = f"wfs_mig0071_{token}", f"wfs_orm0071_{token}"
    admin = create_engine(url, hide_parameters=True)
    try:
        with admin.begin() as c:
            assert c.scalar(text("select current_database()")) == database
            for schema in (mig, orm):
                c.execute(text(f'CREATE SCHEMA "{schema}"'))
                c.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                for ref in ("gov_integration_sync_runs", "ods_api_raw_request_refs"):
                    c.execute(text(f'CREATE TABLE "{ref}" (id uuid PRIMARY KEY)'))
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            run_migration(c, "20261030_0071_wfs_lingxing_board.py")
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{orm}"'))
            Base.metadata.create_all(
                c, tables=[Base.metadata.tables[name] for name in BOARD_TABLES]
            )
        with admin.connect() as c:
            migrated = table_structure(c, mig, BOARD_TABLES)
            declared = table_structure(c, orm, BOARD_TABLES)
        assert migrated == declared
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(
                text(
                    "INSERT INTO gov_wfs_board_publications (id, source_account_ref, status,"
                    " is_current, cargo_run_id, coverage_start, coverage_end,"
                    " source_observed_at, published_at, builder_version, quality_report)"
                    " VALUES (gen_random_uuid(), 'acct', 'published', false, gen_random_uuid(),"
                    " DATE '2026-10-01', DATE '2026-10-31', now(), now(), 'fixture', '{}')"
                )
            )
        with pytest.raises(RuntimeError, match="retain WFS evidence"):
            with admin.begin() as c:
                c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
                run_migration(c, "20261030_0071_wfs_lingxing_board.py", "downgrade")
        with admin.begin() as c:
            c.execute(text(f'SET LOCAL search_path TO "{mig}"'))
            c.execute(text("DELETE FROM gov_wfs_board_publications"))
            run_migration(c, "20261030_0071_wfs_lingxing_board.py", "downgrade")
            left = [n for n in BOARD_TABLES if c.scalar(text("select to_regclass(:n)"), {"n": n})]
            assert left == []
    finally:
        with admin.begin() as c:
            for schema in (mig, orm):
                assert schema.startswith("wfs_") and token in schema
                c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_exception_detector_opens_refreshes_and_auto_resolves(db):
    """8088 rule 创建后长期未发货 (7 days) through the durable case lifecycle."""
    from sqlalchemy import select

    from app.modules.pmc_wfs.exception_detector import SYSTEM_ACTOR, WfsExceptionDetector
    from app.modules.pmc_wfs.exception_models import WfsExceptionAction, WfsExceptionCase

    account, order = _seed_order(db)
    _seed_board(db, account, order, cargo_code="7000001WFB", store_id=order.store_id, status=0)
    mart = db.scalar(
        select(WfsShipmentBoardRow).where(WfsShipmentBoardRow.cargo_code == "7000001WFB")
    )
    mart.status_name = "PENDING_SHIPMENT_DETAILS"
    mart.shipping_codes = []
    mart.payload_json = {
        **mart.payload_json,
        "cargo": {"cargo_create_date": "2026-10-01 09:00:00"},
        "derived": {"version": "wfs_board_derived.v1", "region": "美西"},
    }
    db.flush()

    first = WfsExceptionDetector(db, account, today=date(2026, 10, 20)).run()
    assert (first.hits, first.created) == (1, 1)
    case = db.scalar(select(WfsExceptionCase).where(WfsExceptionCase.shipment_id == "7000001WFB"))
    assert case.rule_family == "create_long_unshipped" and case.status == "OPEN"
    assert case.rule_version == "WFS-RULES-20261010" and case.severity == "LOW"
    assert case.summary == "创建 19 天仍未补发货信息 / 未关联发货单"

    again = WfsExceptionDetector(db, account, today=date(2026, 10, 20)).run()
    assert (again.created, again.refreshed, again.auto_resolved) == (0, 1, 0)

    gone = WfsExceptionDetector(db, account, today=date(2026, 10, 5)).run()
    assert gone.auto_resolved == 1
    db.refresh(case)
    assert case.status == "RESOLVED"
    actions = db.scalars(
        select(WfsExceptionAction).where(WfsExceptionAction.case_id == case.id)
    ).all()
    assert [(a.action_type, a.actor_uid) for a in actions] == [("RESOLVE", SYSTEM_ACTOR)]

    back = WfsExceptionDetector(db, account, today=date(2026, 10, 21)).run()
    assert back.reopened == 1
    db.refresh(case)
    assert case.status == "OPEN" and case.summary == "创建 20 天仍未补发货信息 / 未关联发货单"
