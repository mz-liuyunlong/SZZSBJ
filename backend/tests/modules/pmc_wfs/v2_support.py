"""Synthetic fixtures for a task-owned PostgreSQL instance, never the business DB."""

import importlib.util
import os
from pathlib import Path
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from app.modules.pmc_wfs.creation_worker import DefinitiveRejection, run_operation


class SyntheticGateway:
    enabled = True

    def __init__(self):
        self.creates = []
        self.fail_label = False
        self.unknown = False
        self.reject = False

    def validate(self, snapshot):
        assert snapshot["source_account_ref"].startswith("wfs-fixture-")

    def create(self, ticket_id, snapshot, allocation):
        self.creates.append(ticket_id)
        if self.reject:
            raise DefinitiveRejection()
        if self.unknown:
            raise TimeoutError()
        return ["TEST-" + ticket_id]

    def reconcile(self, ticket_id, snapshot):
        return ["TEST-" + ticket_id] if ticket_id in self.creates else None

    def label(self, shipment_id, snapshot):
        if self.fail_label:
            raise TimeoutError()
        return b"%PDF-1.4\n% synthetic WFS test label\n%%EOF"

    def preview(self, snapshot):
        return {"synthetic": True, "destinations": ["TEST-FC"]}


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V2_MIGRATIONS = (
    "20261029_0068_wfs_creation.py",
    "20261101_0073_wfs_creation_manual_approval.py",
)


def install_v2_schema(conn):
    """Synthetic source tables (no source FKs) + the real V2 migrations, in order."""
    register_productlist_sync_models()
    # These are freshly generated synthetic source tables, not clones of a business schema.
    # Add no source FKs here: unrelated modules may have cyclic metadata. V2 itself is
    # installed using its real migrations and retains all declared FK/unique/check constraints.
    existing = set(
        conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))
    )
    if "ops_wfs_creation_operations" in existing:
        return
    for table in Base.metadata.tables.values():
        if not table.name.startswith(
            (
                "ops_domestic_",
                "evt_domestic_",
                "dwd_domestic_",
                "gov_domestic_",
                "mart_domestic_",
                "dwd_lingxing_sku_",
                "ops_pmc_wfs_",
                "evt_pmc_wfs_",
            )
        ):
            continue
        if table.name not in existing:
            conn.execute(CreateTable(table, include_foreign_key_constraints=[]))
    versions = Path(__file__).parents[3] / "alembic" / "versions"
    for index, name in enumerate(V2_MIGRATIONS):
        migration = module_from(versions / name, f"v2_test_migration_{index}")
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()


def engine_and_schema():
    url = os.environ["WFS_V2_TEST_DATABASE_URL"]
    engine = create_engine(url, hide_parameters=True)
    assert engine.url.host == "127.0.0.1" and engine.url.port == 56543
    assert engine.url.database.startswith("wfs_v2_test_")
    with engine.connect() as conn:
        directory = conn.scalar(text("SHOW data_directory"))
        assert "/wfs-v2-" in directory.replace("\\", "/")
    with engine.begin() as conn:
        install_v2_schema(conn)
    return engine


def engine_and_local_schema():
    """Same V2 schema inside a throwaway schema of the verified local development DB
    (opt-in ``WFS_LOCAL_INTEGRATION=1``). Returns (engine, drop) where drop() removes it."""
    from sqlalchemy import event

    from tests.modules.pmc_wfs.schema_support import integration_target

    url, database = integration_target()
    schema = "wfs_v2_local_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as conn:
        assert conn.scalar(text("select current_database()")) == database
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def set_path(dbapi_connection, _):
        # No public fallback: a table the fixture did not create must fail loudly.
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        dbapi_connection.commit()

    with engine.begin() as conn:
        install_v2_schema(conn)

    def drop():
        engine.dispose()
        assert schema.startswith("wfs_v2_local_") and len(schema) == 45
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

    return engine, drop


def seed_fixture(session, boxes=30, per=4):
    seed_module = module_from(Path(__file__).with_name("test_pending.py"), "old_wfs_fixture")
    account, order, box, lines = seed_module.seed(session)
    lines[0].boxes, lines[0].units_per_box = boxes, per
    session.delete(lines[1])
    box.total_qty = boxes * per
    order.qty = boxes * per
    box.approved_qty_snapshot = boxes * per
    session.commit()
    return account, order, box, lines[0]


def factory_for(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def app_for(engine, account, gateway):
    from fastapi import FastAPI

    from app.core.api import install_api_foundation
    from app.core.auth import Principal, get_optional_principal
    from app.modules.pmc_wfs.creation_router import router as creation_router
    from app.modules.pmc_wfs.gateway import get_creation_gateway
    from app.modules.pmc_wfs.router import router, service
    from app.modules.pmc_wfs.service import WfsService
    from app.modules.pmc_wfs.tasks import get_creation_dispatcher

    app = FastAPI()
    install_api_foundation(app)
    app.include_router(router)
    app.include_router(creation_router, prefix="/api/pmc/wfs/pending-packing")
    factory = factory_for(engine)

    def scoped_service():
        with Session(engine) as session:
            yield WfsService(session, frozenset({account}), None)

    principal = Principal(user_id="16", permissions=frozenset({"*"}))
    app.dependency_overrides[service] = scoped_service
    app.dependency_overrides[get_optional_principal] = lambda: principal
    app.dependency_overrides[get_creation_gateway] = lambda: gateway
    app.dependency_overrides[get_creation_dispatcher] = lambda: (
        lambda ident, action: run_operation(factory, gateway, UUID(ident), action)
    )
    return app
