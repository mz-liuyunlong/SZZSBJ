"""Persistent Walmart audit + write ledger: lifecycle, process restart, races, PostgreSQL.

SQLite covers lifecycle, restart (a second ledger object on the same file is a "new
process") and the insert race through the unique constraint. The PostgreSQL section runs
only when ``SZZSBJ_PG_TEST_URL`` points at a database (the Mac dev DB in CI tickets) and
exercises ``SELECT ... FOR UPDATE`` with real concurrent connections.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.integrations.walmart.gateway import GatewayError, WalmartGateway
from app.modules.walmart_scf.persistence import (
    DbAuditSink,
    DbWriteLedger,
    WalmartCallAudit,
    WalmartWriteLedgerEntry,
    build_production_gateway,
)

TABLES = [WalmartCallAudit.__table__, WalmartWriteLedgerEntry.__table__]
FIELDS = {
    "store_code": "HK2614",
    "operation_key": "wfs_inbound_shipment_create",
    "actor_uid": "pmc-wfs-creation",
    "approval_ref": "wfs-ticket:1",
    "request_sha256": "b" * 64,
}


@dataclass(frozen=True)
class Record:
    store_code: str = "HK2614"
    operation_key: str = "wfs_inbound_shipment_create"
    risk: str = "write"
    actor_kind: str = "system"
    actor_uid: str = "pmc-wfs-creation"
    approval_ref: str | None = "wfs-ticket:1"
    idempotency_key: str | None = "wfs-create:PMC-TEST-HK2614-ABC"
    contract_sha256: str | None = "a" * 64
    registry_version: str = "0123456789abcdef"
    request_sha256: str | None = "b" * 64
    status_code: int | None = 201
    outcome: str = "ok"
    error_code: str | None = None
    duration_ms: int = 812


@pytest.fixture
def sqlite_factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}")

    @event.listens_for(engine, "connect")
    def _busy(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA busy_timeout = 5000")

    Base.metadata.create_all(engine, tables=TABLES)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_audit_sink_persists_every_record_without_bodies(sqlite_factory) -> None:
    sink = DbAuditSink(sqlite_factory)
    sink(Record(outcome="attempt", status_code=None))
    sink(Record())
    sink(
        Record(operation_key="wfs_inventory", risk="read", approval_ref=None, idempotency_key=None)
    )
    with sqlite_factory() as s:
        rows = list(s.scalars(select(WalmartCallAudit).order_by(WalmartCallAudit.created_at)))
    assert [r.outcome for r in rows] == ["attempt", "ok", "ok"]
    assert (
        rows[0].idempotency_key == "wfs-create:PMC-TEST-HK2614-ABC" and rows[0].status_code is None
    )
    assert rows[1].status_code == 201 and rows[1].duration_ms == 812
    assert rows[2].approval_ref is None and rows[2].risk == "read"
    assert {c.name for c in WalmartCallAudit.__table__.columns}.isdisjoint({"body", "response"})


def test_ledger_lifecycle_blocks_open_and_done_keys(sqlite_factory) -> None:
    ledger = DbWriteLedger(sqlite_factory)
    key = "wfs-create:PMC-TEST-HK2614-ABC"
    assert ledger.status(key) is None
    ledger.begin(key, **FIELDS)
    assert ledger.status(key) == "attempting"
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        ledger.begin(key, **FIELDS)
    ledger.finish(
        key, outcome="unknown", status_code=None, error_code="WALMART_GATEWAY_UNAVAILABLE"
    )
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        ledger.begin(key, **FIELDS)
    assert ledger.open_keys() == [key]
    with pytest.raises(GatewayError, match="WALMART_LEDGER_RESOLUTION_INVALID"):
        ledger.resolve(key, outcome="attempting", note="x")
    ledger.resolve(key, outcome="failed", note="read-back: nothing at Walmart")
    assert ledger.open_keys() == []
    with pytest.raises(GatewayError, match="WALMART_WRITE_PAYLOAD_CHANGED"):
        ledger.begin(key, **{**FIELDS, "request_sha256": "c" * 64})
    ledger.begin(key, **FIELDS)
    ledger.finish(key, outcome="ok", status_code=201, error_code=None)
    with pytest.raises(GatewayError, match="WALMART_WRITE_ALREADY_DONE"):
        ledger.begin(key, **FIELDS)
    with sqlite_factory() as s:
        entry = s.scalar(select(WalmartWriteLedgerEntry))
    assert entry is not None and entry.attempts == 2 and entry.outcome == "ok"
    assert entry.note == "read-back: nothing at Walmart"
    with pytest.raises(GatewayError, match="WALMART_LEDGER_ENTRY_MISSING"):
        ledger.finish("nope", outcome="ok", status_code=200, error_code=None)


def test_open_attempt_survives_a_process_restart(sqlite_factory, tmp_path) -> None:
    """Worker A claims a key and dies mid-call; worker B (new process) must not redo it."""
    worker_a = DbWriteLedger(sqlite_factory)
    worker_a.begin("wfs-create:PMC-RESTART", **FIELDS)
    del worker_a  # the process is gone; only the database remembers
    fresh_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}")
    worker_b = DbWriteLedger(sessionmaker(bind=fresh_engine, expire_on_commit=False))
    assert worker_b.status("wfs-create:PMC-RESTART") == "attempting"
    with pytest.raises(GatewayError, match="WALMART_WRITE_PENDING_REVIEW"):
        worker_b.begin("wfs-create:PMC-RESTART", **FIELDS)
    assert worker_b.open_keys() == ["wfs-create:PMC-RESTART"]
    worker_b.resolve("wfs-create:PMC-RESTART", outcome="ok", note="reconcile: shipment found")
    with pytest.raises(GatewayError, match="WALMART_WRITE_ALREADY_DONE"):
        worker_b.begin("wfs-create:PMC-RESTART", **FIELDS)
    fresh_engine.dispose()


def test_insert_race_has_exactly_one_winner(sqlite_factory) -> None:
    ledger = DbWriteLedger(sqlite_factory)
    key = "wfs-create:PMC-RACE"
    results: list[str] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        try:
            ledger.begin(key, **FIELDS)
            results.append("won")
        except GatewayError as error:
            results.append(error.code)
        except Exception as error:  # SQLite lock timeouts surface here, never a 2nd winner
            results.append(type(error).__name__)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1, results
    assert ledger.status(key) == "attempting"
    with sqlite_factory() as s:
        assert s.scalar(text("select count(*) from integration_walmart_write_ledger")) == 1


def test_build_production_gateway_wires_persistence(monkeypatch, sqlite_factory, tmp_path):
    from app.integrations.walmart.contract_signing import ContractSigner
    from app.integrations.walmart.unified_api import reviewed_registry

    pem = tmp_path / "k.pem"
    pem.write_bytes(
        ContractSigner.generate(kid="szzsbj-2026-10", registry=reviewed_registry()).private_pem()
    )
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_PROTOCOL", "3")
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_STORE_ID_MAP", '{"110711149920800256": "HK2614"}')
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_CVM_ROLE", "role")
    monkeypatch.setenv("SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN", "qcs::cam::uin/1:roleName/x")
    monkeypatch.setenv("SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE", str(pem))
    monkeypatch.setenv("SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_ID", "szzsbj-2026-10")

    class NoNetwork:
        def get_identity(self):  # pragma: no cover
            raise AssertionError("no network in tests")

    gateway = build_production_gateway(sqlite_factory, identity_provider=NoNetwork())
    assert isinstance(gateway, WalmartGateway)
    assert isinstance(gateway.ledger, DbWriteLedger)
    # The default (no ledger passed) is refused by from_env itself.
    with pytest.raises(GatewayError, match="WALMART_LEDGER_REQUIRED"):
        WalmartGateway.from_env(identity_provider=NoNetwork())


# --- PostgreSQL (opt-in) -------------------------------------------------------------------

PG_URL = os.environ.get("SZZSBJ_PG_TEST_URL", "")


@pytest.fixture
def pg_factory() -> Iterator[sessionmaker[Session]]:
    if not PG_URL:
        pytest.skip("SZZSBJ_PG_TEST_URL not set")
    schema = "walmart_ledger_test_" + uuid4().hex
    admin = create_engine(PG_URL)
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(PG_URL, pool_size=8, max_overflow=8)

    @event.listens_for(engine, "connect")
    def set_path(conn, _):
        with conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()

    Base.metadata.create_all(engine, tables=TABLES)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_concurrent_claims_serialize_on_the_row(pg_factory) -> None:
    ledger = DbWriteLedger(pg_factory)
    key = "wfs-create:PMC-PG"
    ledger.begin(key, **FIELDS)
    ledger.finish(key, outcome="failed", status_code=503, error_code="WALMART_HTTP_503")
    # Eight workers retry the same failed key at once: FOR UPDATE lets exactly one re-open it.
    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        try:
            ledger.begin(key, **FIELDS)
            outcome = "won"
        except GatewayError as error:
            outcome = error.code
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1 and set(results) <= {"won", "WALMART_WRITE_PENDING_REVIEW"}
    with pg_factory() as s:
        entry = s.scalar(select(WalmartWriteLedgerEntry))
    assert entry is not None and entry.attempts == 2 and entry.outcome == "attempting"
    # Fresh key, eight inserters: the unique constraint picks one.
    results.clear()
    barrier = threading.Barrier(8)
    key2 = "wfs-create:PMC-PG-NEW"

    def inserter() -> None:
        barrier.wait()
        try:
            ledger.begin(key2, **FIELDS)
            outcome = "won"
        except GatewayError as error:
            outcome = error.code
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=inserter) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1 and set(results) <= {"won", "WALMART_WRITE_PENDING_REVIEW"}
