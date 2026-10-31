"""Persistent audit and write-idempotency ledger for Walmart gateway calls (ch. 76.6).

Two tables, both written by the unified ``WalmartGateway`` through the sinks below:

* ``integration_walmart_calls`` — one row per gateway call, including refused ones and
  the ``attempt`` row written before a write goes out. Never request/response bodies.
* ``integration_walmart_write_ledger`` — one row per business write key
  (``wfs-create:<inboundOrderId>`` ...). A key whose last attempt is still open or ended
  unknown is refused by the gateway until a reconcile step resolves it; a key that
  succeeded is never executed again.

The sinks only duck-type the gateway's ``CallRecord`` / ``WriteLedger`` so this module
imports nothing from the shared Walmart package and works on this branch alone.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import now

OPEN_OUTCOMES = frozenset({"attempting", "unknown"})
RESOLVABLE_OUTCOMES = frozenset({"ok", "provider_error", "failed"})


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
        DateTime(timezone=True), nullable=False, default=now, index=True
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
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now, onupdate=now
    )


class LedgerRefused(RuntimeError):
    """Stable code; the gateway surfaces it to the business side unchanged."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DbAuditSink:
    """``AuditSink``: one committed row per ``CallRecord`` in its own short session."""

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
                    idempotency_key=getattr(record, "idempotency_key", None),
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

    ``begin`` takes a row lock (``SELECT ... FOR UPDATE`` on PostgreSQL) so two workers
    cannot both open the same key; the unique constraint is the last line of defence.
    """

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._factory = session_factory

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
            stmt = select(WalmartWriteLedgerEntry).where(
                WalmartWriteLedgerEntry.idempotency_key == key
            )
            if session.get_bind().dialect.name == "postgresql":
                stmt = stmt.with_for_update()
            entry = session.scalar(stmt)
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
                session.commit()
                return
            if entry.outcome in OPEN_OUTCOMES:
                raise LedgerRefused("WALMART_WRITE_PENDING_REVIEW")
            if entry.outcome == "ok":
                raise LedgerRefused("WALMART_WRITE_ALREADY_DONE")
            if entry.request_sha256 != request_sha256:
                raise LedgerRefused("WALMART_WRITE_PAYLOAD_CHANGED")
            entry.outcome = "attempting"
            entry.actor_uid = actor_uid
            entry.approval_ref = approval_ref
            entry.attempts += 1
            entry.status_code = None
            entry.error_code = None
            entry.updated_at = now()
            session.commit()

    def finish(
        self, key: str, *, outcome: str, status_code: int | None, error_code: str | None
    ) -> None:
        with self._factory() as session:
            entry = session.scalar(
                select(WalmartWriteLedgerEntry).where(
                    WalmartWriteLedgerEntry.idempotency_key == key
                )
            )
            if entry is None:
                raise LedgerRefused("WALMART_LEDGER_ENTRY_MISSING")
            entry.outcome = outcome
            entry.status_code = status_code
            entry.error_code = error_code
            entry.updated_at = now()
            session.commit()

    def status(self, key: str) -> str | None:
        with self._factory() as session:
            return session.scalar(
                select(WalmartWriteLedgerEntry.outcome).where(
                    WalmartWriteLedgerEntry.idempotency_key == key
                )
            )

    def resolve(self, key: str, *, outcome: str, note: str) -> None:
        """Reconcile hook: close an open/unknown attempt after a Walmart read-back."""
        if outcome not in RESOLVABLE_OUTCOMES:
            raise LedgerRefused("WALMART_LEDGER_RESOLUTION_INVALID")
        with self._factory() as session:
            entry = session.scalar(
                select(WalmartWriteLedgerEntry).where(
                    WalmartWriteLedgerEntry.idempotency_key == key
                )
            )
            if entry is None:
                raise LedgerRefused("WALMART_LEDGER_ENTRY_MISSING")
            entry.outcome = outcome
            entry.note = note[:500]
            entry.updated_at = now()
            session.commit()
