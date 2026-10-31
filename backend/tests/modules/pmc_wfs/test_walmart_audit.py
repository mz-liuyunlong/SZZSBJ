"""Persistent Walmart call audit + write ledger (SQLite; duck-typed against the gateway)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.pmc_wfs.walmart_audit import (
    DbAuditSink,
    DbWriteLedger,
    LedgerRefused,
    WalmartCallAudit,
    WalmartWriteLedgerEntry,
)


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
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[WalmartCallAudit.__table__, WalmartWriteLedgerEntry.__table__],
    )
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_audit_sink_persists_every_record_without_bodies(factory) -> None:
    sink = DbAuditSink(factory)
    sink(Record(outcome="attempt", status_code=None))
    sink(Record())
    sink(
        Record(operation_key="wfs_inventory", risk="read", approval_ref=None, idempotency_key=None)
    )
    with factory() as s:
        rows = list(s.scalars(select(WalmartCallAudit).order_by(WalmartCallAudit.created_at)))
    assert [r.outcome for r in rows] == ["attempt", "ok", "ok"]
    assert (
        rows[0].idempotency_key == "wfs-create:PMC-TEST-HK2614-ABC" and rows[0].status_code is None
    )
    assert rows[1].status_code == 201 and rows[1].duration_ms == 812
    assert rows[2].approval_ref is None and rows[2].risk == "read"
    assert not any(hasattr(r, "body") or hasattr(r, "response") for r in rows)


def test_ledger_lifecycle_blocks_open_and_done_keys(factory) -> None:
    ledger = DbWriteLedger(factory)
    key = "wfs-create:PMC-TEST-HK2614-ABC"
    fields = {
        "store_code": "HK2614",
        "operation_key": "wfs_inbound_shipment_create",
        "actor_uid": "pmc-wfs-creation",
        "approval_ref": "wfs-ticket:1",
        "request_sha256": "b" * 64,
    }
    assert ledger.status(key) is None
    ledger.begin(key, **fields)
    assert ledger.status(key) == "attempting"
    # A second worker while the first is still posting.
    with pytest.raises(LedgerRefused, match="WALMART_WRITE_PENDING_REVIEW"):
        ledger.begin(key, **fields)
    ledger.finish(
        key, outcome="unknown", status_code=None, error_code="WALMART_GATEWAY_UNAVAILABLE"
    )
    with pytest.raises(LedgerRefused, match="WALMART_WRITE_PENDING_REVIEW"):
        ledger.begin(key, **fields)
    # Reconcile after a read-back.
    with pytest.raises(LedgerRefused, match="WALMART_LEDGER_RESOLUTION_INVALID"):
        ledger.resolve(key, outcome="attempting", note="x")
    ledger.resolve(key, outcome="failed", note="read-back: nothing at Walmart")
    # Same payload may be retried once resolved as failed; a different payload may not.
    with pytest.raises(LedgerRefused, match="WALMART_WRITE_PAYLOAD_CHANGED"):
        ledger.begin(key, **{**fields, "request_sha256": "c" * 64})
    ledger.begin(key, **fields)
    ledger.finish(key, outcome="ok", status_code=201, error_code=None)
    with pytest.raises(LedgerRefused, match="WALMART_WRITE_ALREADY_DONE"):
        ledger.begin(key, **fields)
    with factory() as s:
        entry = s.scalar(select(WalmartWriteLedgerEntry))
    assert entry is not None and entry.attempts == 2 and entry.outcome == "ok"
    assert entry.note == "read-back: nothing at Walmart"
    with pytest.raises(LedgerRefused, match="WALMART_LEDGER_ENTRY_MISSING"):
        ledger.finish("nope", outcome="ok", status_code=200, error_code=None)
