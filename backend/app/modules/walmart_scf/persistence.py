"""PostgreSQL persistence for the unified Walmart gateway: audit rows + write ledger.

Reviewer requirements (handover 76.13, round 2):

* ``integration_walmart_calls`` — one row per gateway call, including refused ones and
  the ``attempt`` row persisted *before* a write leaves the server. Never bodies.
* ``integration_walmart_write_ledger`` — one row per business write key. ``begin`` is an
  atomic claim (row lock + unique constraint), so two workers cannot both open the same
  key; ``finish`` records the outcome; an ``attempting`` or ``unknown`` entry survives a
  process restart and blocks the key until ``resolve`` closes it after a read-back.

``build_production_gateway`` is the only supported way to construct the gateway for
production: it always wires these two tables in. The in-memory ledger is test-only.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.integrations.walmart.gateway import (
    LEDGER_OPEN,
    FileOutbox,
    GatewayError,
    WalmartGateway,
    ledger_begin_check,
    ledger_transition_check,
)

OPEN_OUTCOMES = LEDGER_OPEN
DEFAULT_OUTBOX_DIR = "/var/lib/szzsbj/walmart-audit-outbox"
OUTBOX_DIR_ENV = "SZZSBJ_WALMART_AUDIT_OUTBOX_DIR"


def _now() -> datetime:
    return datetime.now(UTC)


class WalmartCallAudit(Base):
    __tablename__ = "integration_walmart_calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_ref: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(160), index=True)
    contract_sha256: Mapped[str | None] = mapped_column(String(64))
    registry_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_sha256: Mapped[str | None] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )


class WalmartWriteLedgerEntry(Base):
    __tablename__ = "integration_walmart_write_ledger"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_walmart_write_ledger_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class DbAuditSink:
    """``AuditSink``: one committed row per ``CallRecord`` in its own short session.

    Any failure propagates: the gateway keeps the record in its outbox, refuses further
    writes until it is flushed, and never pretends the evidence was stored.
    """

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._factory = session_factory

    def __call__(self, record: Any) -> None:
        with self._factory() as session:
            session.add(
                WalmartCallAudit(
                    store_code=record.store_code,
                    operation_key=record.operation_key,
                    risk=record.risk,
                    actor_kind=record.actor_kind,
                    actor_uid=record.actor_uid,
                    approval_ref=record.approval_ref,
                    idempotency_key=record.idempotency_key,
                    contract_sha256=record.contract_sha256,
                    registry_version=record.registry_version,
                    request_sha256=record.request_sha256,
                    status_code=record.status_code,
                    outcome=record.outcome,
                    error_code=record.error_code,
                    duration_ms=int(record.duration_ms),
                )
            )
            session.commit()


class DbWriteLedger:
    """``WriteLedger`` on ``integration_walmart_write_ledger``.

    Claim semantics: the row is read ``FOR UPDATE`` (PostgreSQL) so concurrent workers
    serialize on the key; a brand-new key is inserted under the unique constraint and a
    losing inserter sees ``IntegrityError`` -> ``WALMART_WRITE_PENDING_REVIEW``. Nothing
    here is cached in memory, so a restarted process sees exactly the persisted state.

    State machine (``gateway.ledger_transition_check``): ``finish`` only from
    ``attempting``; ``resolve`` only from an open key (attempting / unknown), never from
    ``ok``; a re-claim must match store, operation
    and request digest of the earlier attempt (``WALMART_LEDGER_KEY_REUSED`` /
    ``WALMART_WRITE_PAYLOAD_CHANGED``). ``finish`` and ``resolve`` also lock the row.
    """

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._factory = session_factory

    @staticmethod
    def _locked(session: Any, key: str):
        stmt = select(WalmartWriteLedgerEntry).where(WalmartWriteLedgerEntry.idempotency_key == key)
        if session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        return session.scalar(stmt)

    def begin(
        self,
        key: str,
        *,
        store_code: str,
        operation_key: str,
        actor_uid: str,
        approval_ref: str,
        request_sha256: str,
    ) -> None:
        with self._factory() as session:
            entry = self._locked(session, key)
            if entry is None:
                session.add(
                    WalmartWriteLedgerEntry(
                        idempotency_key=key,
                        store_code=store_code,
                        operation_key=operation_key,
                        actor_uid=actor_uid,
                        approval_ref=approval_ref,
                        request_sha256=request_sha256,
                        outcome="attempting",
                    )
                )
                try:
                    session.commit()
                except IntegrityError:
                    # Lost the race to another worker that inserted the same key first.
                    session.rollback()
                    raise GatewayError("WALMART_WRITE_PENDING_REVIEW") from None
                return
            ledger_begin_check(
                {
                    "outcome": entry.outcome,
                    "store_code": entry.store_code,
                    "operation_key": entry.operation_key,
                    "request_sha256": entry.request_sha256,
                },
                store_code=store_code,
                operation_key=operation_key,
                request_sha256=request_sha256,
            )
            entry.outcome = "attempting"
            entry.actor_uid = actor_uid
            entry.approval_ref = approval_ref
            entry.attempts += 1
            entry.status_code = None
            entry.error_code = None
            entry.updated_at = _now()
            session.commit()

    def finish(
        self, key: str, *, outcome: str, status_code: int | None, error_code: str | None
    ) -> None:
        with self._factory() as session:
            entry = self._locked(session, key)
            if entry is None:
                raise GatewayError("WALMART_LEDGER_ENTRY_MISSING")
            ledger_transition_check(entry.outcome, to=outcome, via="finish")
            entry.outcome = outcome
            entry.status_code = status_code
            entry.error_code = error_code
            entry.updated_at = _now()
            session.commit()

    def status(self, key: str) -> str | None:
        with self._factory() as session:
            return session.scalar(
                select(WalmartWriteLedgerEntry.outcome).where(
                    WalmartWriteLedgerEntry.idempotency_key == key
                )
            )

    def resolve(self, key: str, *, outcome: str, note: str) -> None:
        """Reconcile hook: close an open (attempting / unknown) key after a Walmart read-back.

        Targets: ok / failed / provider_error. ``ok`` is terminal; a closed retryable key is
        reopened only through ``begin``.
        """
        with self._factory() as session:
            entry = self._locked(session, key)
            if entry is None:
                raise GatewayError("WALMART_LEDGER_ENTRY_MISSING")
            ledger_transition_check(entry.outcome, to=outcome, via="resolve")
            entry.outcome = outcome
            entry.note = note[:500]
            entry.updated_at = _now()
            session.commit()

    def open_keys(self, *, limit: int = 200) -> list[str]:
        """Keys a reconcile job must look at (attempting / unknown), oldest first."""
        with self._factory() as session:
            return list(
                session.scalars(
                    select(WalmartWriteLedgerEntry.idempotency_key)
                    .where(WalmartWriteLedgerEntry.outcome.in_(OPEN_OUTCOMES))
                    .order_by(WalmartWriteLedgerEntry.updated_at)
                    .limit(limit)
                )
            )


def build_production_gateway(
    session_factory: Callable[[], Any],
    *,
    identity_provider: Any = None,
    outbox_dir: str | None = None,
) -> WalmartGateway:
    """The production gateway: environment configuration + persistent audit, ledger and
    a durable file outbox (``SZZSBJ_WALMART_AUDIT_OUTBOX_DIR``) drained on start."""
    import os

    directory = outbox_dir or os.environ.get(OUTBOX_DIR_ENV, "").strip() or DEFAULT_OUTBOX_DIR
    try:
        outbox = FileOutbox(directory)
    except OSError:
        raise GatewayError("WALMART_AUDIT_OUTBOX_REQUIRED") from None
    return WalmartGateway.from_env(
        audit=DbAuditSink(session_factory),
        ledger=DbWriteLedger(session_factory),
        outbox=outbox,
        identity_provider=identity_provider,
    )
