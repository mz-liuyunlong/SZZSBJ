"""Real local PostgreSQL tests in a process-owned schema; existing data never touched."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import WalmartListingDimension
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication, DomesticInboundBoard
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder, now
from app.modules.pmc_domestic.warehouse_models import PackingBoxLine, PackingBoxSet
from app.modules.pmc_domestic.warehouse_schemas import CustomsCommand, ReboxCommand
from app.modules.pmc_domestic.warehouse_service import WarehouseService
from app.modules.pmc_wfs.models import WfsBoxAllocation, WfsDraft, WfsEvent
from app.modules.pmc_wfs.router import service as dependency
from app.modules.pmc_wfs.schemas import DraftCommand, IdentityCommand, PendingFilter, PendingQuery
from app.modules.pmc_wfs.service import WfsService
from scripts.wfs_pending_local_schema import local_url


@pytest.fixture(scope="module")
def engine():
    url = local_url()
    get_settings.cache_clear()
    schema = "wfs_test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as c:
        assert c.scalar(text("select current_database()")) == "szzsbj_dev"
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_engine = create_engine(url, hide_parameters=True)

    @event.listens_for(db_engine, "connect")
    def set_path(conn, _):
        # No public fallback: an omitted fixture table must fail, never read business data.
        with conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()

    try:
        register_productlist_sync_models()
        # Clone schema only, including its actual deployed constraints. Metadata contains
        # unrelated historical naming collisions and is not a migration substitute.
        with db_engine.begin() as c:
            names = list(
                c.scalars(text("select tablename from pg_tables where schemaname='public'"))
            )
            for name in names:
                assert name.replace("_", "").isalnum()
                c.execute(text(f'CREATE TABLE "{name}" (LIKE public."{name}" INCLUDING ALL)'))
            fks = c.execute(
                text("""
                select r.relname, k.conname, pg_get_constraintdef(k.oid)
                from pg_constraint k join pg_class r on r.oid=k.conrelid
                join pg_namespace n on n.oid=r.relnamespace
                where n.nspname='public' and k.contype='f'
            """)
            ).all()
            for table, name, definition in fks:
                assert name.replace("_", "").isalnum()
                definition = definition.replace("public.", f'"{schema}".')
                c.execute(text(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" {definition}'))
        with db_engine.begin() as c:
            c.execute(
                text("""CREATE FUNCTION prevent_wfs_test_events() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'immutable'; END; $$ LANGUAGE plpgsql""")
            )
            c.execute(
                text("""CREATE TRIGGER wfs_test_event_guard BEFORE UPDATE OR DELETE
                ON evt_pmc_wfs_draft_events FOR EACH ROW
                EXECUTE FUNCTION prevent_wfs_test_events()""")
            )
        yield db_engine
    finally:
        db_engine.dispose()
        # Drop only the exact schema created by this fixture, never a user-supplied name.
        assert schema.startswith("wfs_test_") and len(schema) == 41
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


def seed(s):
    account = "wfs-fixture-" + uuid4().hex
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
    s.add(pub)
    s.flush()
    board = DomesticInboundBoard(
        id=uuid4(),
        publication_id=pub.id,
        source_account_ref=account,
        source_warehouse_id="16168",
        inbound_order_sn="IB-WFS-TEST",
        sku="TEST-SKU",
        store_id="fixture-store",
        attribution_key="fixture-store",
        balance_num=100,
        arrival_business_date=date(2026, 10, 20),
        payload_json={"available_good_num": 100},
    )
    s.add(board)
    s.flush()
    oid = uuid4()
    snapshot = dict(
        id=str(oid),
        candidate_version="a" * 64,
        source_account_ref=account,
        warehouse_id="16168",
        publication_id=str(pub.id),
        board_id=str(board.id),
        inbound_order_sn=board.inbound_order_sn,
        sku=board.sku,
        product_name="测试商品",
        store_id="fixture-store",
        store_name="测试店",
        item_id="123456",
        gtin="00000000000001",
        msku="TEST-MSKU",
        purchase_order_sns=[],
        arrival_purchased=None,
        candidate_created_on="2026-10-20",
        overdue=False,
        stock_balance=100,
        available_quantity=100,
        default_quantity=10,
        can_approve=True,
        blocked_reasons=[],
        source_observed_at=now().isoformat(),
    )
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
        snapshot_json=snapshot,
        actor_uid="fixture",
    )
    s.add(order)
    s.flush()
    s.add(
        PackingAllocation(
            order_id=oid,
            source_account_ref=account,
            warehouse_id="16168",
            source_board_id=board.id,
            source_publication_id=pub.id,
            qty=10,
        )
    )
    box = PackingBoxSet(
        id=uuid4(),
        order_id=oid,
        total_qty=10,
        approved_qty_snapshot=10,
        version=1,
        completed_at=now(),
        completed_by="fixture",
        actor_uid="fixture",
    )
    s.add(box)
    s.flush()
    lines = []
    for n, per in enumerate((4, 6), 1):
        line = PackingBoxLine(
            id=uuid4(),
            box_set_id=box.id,
            line_no=n,
            box_type="A",
            boxes=1,
            units_per_box=per,
            length_cm=58,
            width_cm=40,
            height_cm=45,
            gross_weight_kg=3,
        )
        s.add(line)
        lines.append(line)
    s.flush()
    s.commit()  # Commit only the fixture savepoint; the outer test transaction still rolls back.
    return account, order, box, lines


def command(account, order, box, lines):
    return DraftCommand(
        source_account_ref=account,
        idempotency_key=uuid4(),
        selections=[
            dict(
                order_id=order.id,
                expected_version=order.version,
                expected_box_version=box.version,
                box_line_ids=[r.id for r in lines],
            )
        ],
        return_address=dict(
            address_line1="Test street",
            city="Katy",
            state_code="TX",
            postal_code="77449",
            country_code="US",
        ),
    )


def test_query_counts_and_unknown_identity(db):
    account, order, box, _ = seed(db)
    svc = WfsService(db, frozenset({account}), None)
    assert svc.list(PendingQuery()).total == 1
    assert svc.summary(PendingFilter()).available_units == 10
    assert svc.summary(PendingFilter(only_test=True)).test == 1
    assert svc.list(PendingQuery(keyword="no-match")).total == 0
    assert (
        WfsService(db, frozenset({account}), frozenset({"other"})).list(PendingQuery()).total == 0
    )
    assert WfsService(db, frozenset(), None).list(PendingQuery()).total == 0
    order.snapshot_json = {**order.snapshot_json, "gtin": None}
    db.flush()
    assert svc.detail(order.id).blocked_reasons == ["GTIN_INVALID"]
    box.completed_at = box.completed_by = None
    db.flush()
    assert svc.list(PendingQuery()).total == 0
    assert svc.summary(PendingFilter()).waiting == 1


def test_drafts_split_idempotency_and_domestic_guard(db):
    account, order, box, lines = seed(db)
    svc = WfsService(db, frozenset({account}), None)
    cmd = command(account, order, box, lines)
    result = svc.submit(cmd, "fixture")
    assert len(result.drafts) == 2
    assert result.drafts[0].payload["items"][0]["order"]["gtin"] == "00000000000001"
    assert svc.submit(cmd, "fixture") == result
    assert svc.summary(PendingFilter()).ready == 0
    assert db.scalar(select(func.count()).select_from(WfsBoxAllocation)) == 2
    with pytest.raises(ApiError) as err:
        svc.submit(command(account, order, box, lines), "fixture")
    assert err.value.status_code == 409
    with pytest.raises(ApiError) as err:
        WarehouseService(db).command(
            order.id,
            "customs",
            CustomsCommand(
                source_account_ref=account,
                expected_version=1,
                idempotency_key=uuid4(),
                value=True,
                reason="测试原因",
            ),
            "fixture",
            frozenset({account}),
        )
    assert err.value.details["reason"] == "WFS_BOXES_OCCUPIED"


def test_main_tail_and_stale_version(db):
    account, order, box, lines = seed(db)
    svc = WfsService(db, frozenset({account}), None)
    cmd = command(account, order, box, lines[:1])
    cmd.selections[0].expected_version = 99
    with pytest.raises(ApiError):
        svc.submit(cmd, "fixture")
    assert db.scalar(select(func.count()).select_from(WfsDraft)) == 0
    svc.submit(command(account, order, box, lines[:1]), "fixture")
    assert svc.detail(order.id).available_line_ids == [lines[1].id]
    assert not svc.detail(order.id).can_edit
    svc.submit(command(account, order, box, lines[1:]), "fixture")
    assert svc.summary(PendingFilter()).ready == 0


def test_identity_switch_transfers_not_duplicates_stock(db):
    account, order, box, _ = seed(db)
    listing = WalmartListingDimension(
        source_system="lingxing",
        source_account_ref=account,
        platform_code="walmart",
        store_id="new-store",
        item_id="999999",
        msku="NEW-MSKU",
        local_sku=order.sku,
        gtin="00000000000002",
        standard_status="PUBLISHED",
        raw_status="PUBLISHED",
        fulfillment_type="0",
        business_hash="b" * 64,
        source_observed_at=now(),
        synced_at=now(),
    )
    db.add(listing)
    db.flush()
    svc = WfsService(db, frozenset({account}), None)
    choice = svc.identity_options(order.id).listings[0]
    cmd = IdentityCommand(
        source_account_ref=account,
        expected_version=1,
        expected_box_version=1,
        idempotency_key=uuid4(),
        target_store_id="new-store",
        target_item_id="999999",
        listing_version=choice.listing_version,
        reason="换店测试",
    )
    result = svc.switch(order.id, cmd, "fixture")
    assert result.order.id != order.id and order.status == "voided"
    assert result.order.box_set.total_qty == 10
    assert result.order.box_set.completed_at == box.completed_at
    assert db.scalar(select(func.sum(PackingAllocation.qty))) == 10
    assert db.scalar(select(PackingAllocation.order_id)) == result.order.id
    assert svc.switch(order.id, cmd, "fixture").order.id == result.order.id


def test_concurrent_submit(engine):
    with Session(engine, expire_on_commit=False) as s:
        account, order, box, lines = seed(s)
        cmd = command(account, order, box, lines[:1])
        s.commit()

    def worker(_):
        with Session(engine) as s:
            svc = WfsService(s, frozenset({account}), None)
            try:
                return (
                    svc.submit(cmd.model_copy(update={"idempotency_key": uuid4()}), "fixture")
                    .drafts[0]
                    .id
                )
            except ApiError as e:
                return e.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sum(r == 409 for r in results) == 1


def test_http_contract_and_permissions(db):
    account, order, box, lines = seed(db)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    app.dependency_overrides[dependency] = lambda: WfsService(db, frozenset({account}), None)
    actor = Principal(user_id="fixture", permissions=frozenset({"page:pmc:wfs:view"}))
    app.dependency_overrides[get_optional_principal] = lambda: actor
    with TestClient(app) as client:
        prefix = "/api/pmc/wfs/pending-packing"
        response = client.get(prefix + "/orders")
        assert response.status_code == 200 and response.json()["data"]["total"] == 1
        assert response.json()["request_id"]
        assert client.post(prefix + "/drafts", json={}).status_code == 403
        assert client.get(prefix + "/orders/not-uuid").status_code == 422
        assert client.get(prefix + "/orders/" + str(uuid4())).status_code == 404
    assert "/api/pmc/wfs/pending-packing/drafts" in app.openapi()["paths"]
    # Exercise the actual route dependency and successful JSON response model too.
    actor = Principal(user_id="fixture", permissions=frozenset({"*"}))
    del app.dependency_overrides[dependency]
    body = command(account, order, box, lines).model_dump(mode="json")
    with TestClient(app) as client:
        response = client.post(prefix + "/drafts", json=body)
        assert response.status_code == 200
        drafts = response.json()["data"]["drafts"]
        assert len(drafts) == 2 and all(d["status"] == "pending" for d in drafts)
        retry = client.post(prefix + "/drafts", json=body)
        assert retry.json()["data"] == response.json()["data"]


def test_strict_inputs():
    with pytest.raises(ValueError):
        DraftCommand(
            source_account_ref="x",
            idempotency_key=uuid4(),
            selections=[],
            return_address={},
            its="yes",
        )


def test_rebox_before_submit_and_block_after_submit(db):
    account, order, box, _ = seed(db)
    scope = frozenset({account})
    cmd = ReboxCommand(
        source_account_ref=account,
        expected_version=1,
        expected_box_version=1,
        idempotency_key=uuid4(),
        reason="装箱调整",
        lines=[dict(box_type="A", boxes=1, units_per_box=10, gross_weight_kg=3)],
    )
    changed = WarehouseService(db).command(order.id, "rebox", cmd, "fixture", scope)
    assert changed.box_set.version == 2
    assert changed.box_set.completed_at == box.completed_at
    svc = WfsService(db, scope, None)
    cmd_draft = DraftCommand(
        source_account_ref=account,
        idempotency_key=uuid4(),
        selections=[
            dict(
                order_id=order.id,
                expected_version=changed.version,
                expected_box_version=2,
                box_line_ids=[r.id for r in changed.box_set.lines],
            )
        ],
        return_address=dict(
            address_line1="Test street", city="Katy", state_code="TX", postal_code="77449"
        ),
    )
    svc.submit(cmd_draft, "fixture")
    with pytest.raises(ApiError) as err:
        WarehouseService(db).command(
            order.id,
            "rebox",
            cmd.model_copy(
                update={
                    "expected_version": changed.version,
                    "expected_box_version": 2,
                    "idempotency_key": uuid4(),
                }
            ),
            "fixture",
            scope,
        )
    assert err.value.details["reason"] == "WFS_BOXES_OCCUPIED"


def test_actor_scope_and_immutable_audit(db):
    from sqlalchemy.exc import DBAPIError

    account, order, box, lines = seed(db)
    svc = WfsService(db, frozenset({account}), None)
    cmd = command(account, order, box, lines[:1])
    svc.submit(cmd, "fixture")
    with pytest.raises(ApiError) as err:
        svc.submit(cmd, "other-actor")
    assert err.value.details["reason"] == "IDEMPOTENCY_KEY_REUSED"
    with pytest.raises(ApiError) as err:
        WfsService(db, frozenset({account}), frozenset({"other"})).detail(order.id)
    assert err.value.status_code == 404
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("UPDATE evt_pmc_wfs_draft_events SET kind='tampered'"))
    assert db.scalar(select(WfsEvent.kind)) == "submit"


def test_invalid_line_batch_rolls_back_and_business_test_is_independent(db):
    account, order, box, lines = seed(db)
    order.business_test = False
    db.commit()
    svc = WfsService(db, frozenset({account}), None)
    assert svc.summary(PendingFilter(only_test=True)).completed == 0
    assert svc.detail(order.id).order.is_test is True
    cmd = command(account, order, box, lines)
    cmd.selections[0].box_line_ids.append(uuid4())
    with pytest.raises(ApiError):
        svc.submit(cmd, "fixture")
    assert db.scalar(select(func.count()).select_from(WfsDraft).where(
        WfsDraft.source_account_ref == account
    )) == 0
    assert not svc.repo.occupied([order.id])
