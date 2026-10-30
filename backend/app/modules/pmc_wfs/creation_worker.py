"""Durable execution boundary: uncertain writes are reconciled, never blindly retried."""

import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationEvent, WfsCreationTicket
from app.modules.pmc_wfs.creation_service import guard_write


class DefinitiveRejection(Exception):
    """An adapter may raise this only with evidence that no shipment was created."""


def actual_ids(values):
    if (
        not isinstance(values, list)
        or not values
        or len(values) > 5000
        or any(not isinstance(v, str) or not v.strip() or len(v) > 128 for v in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("unverified shipment result")
    return values


def run_operation(factory, gateway, ident, action="execute"):
    """Callable by Celery or an isolated test; factory and adapter are explicit dependencies."""
    ident = UUID(str(ident))
    with factory() as session:
        guard_write(session)
        op = session.get(WfsCreation, ident)
        if op is None:
            return
        gateway.validate(op.snapshot)
        ticket_ids = list(
            session.scalars(
                select(WfsCreationTicket.id)
                .where(WfsCreationTicket.operation_id == ident)
                .order_by(WfsCreationTicket.number)
            )
        )
    for ticket_id in ticket_ids:
        execute_ticket(factory, gateway, ident, ticket_id, action)
    with factory() as session:
        op = session.scalar(select(WfsCreation).where(WfsCreation.id == ident).with_for_update())
        states = list(
            session.scalars(
                select(WfsCreationTicket.state).where(WfsCreationTicket.operation_id == ident)
            )
        )
        if states and all(s == "SUCCEEDED" for s in states):
            op.state = "SUCCEEDED"
        elif "SUCCEEDED" in states:
            op.state = "PARTIAL"
        elif "UNKNOWN" in states:
            op.state = "UNKNOWN"
        elif "RUNNING" in states:
            op.state = "RUNNING"
        elif "QUEUED" in states:
            op.state = "QUEUED"
        else:
            op.state = "FAILED"
        session.commit()


def execute_ticket(factory, gateway, ident, ticket_id, action):
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        op = session.get(WfsCreation, ident)
        snapshot, allocation = op.snapshot, ticket.allocation
        mode = None
        if ticket.state == "QUEUED" and action in {"execute", "reconcile"}:
            mode = "create"
        elif action == "reconcile" and ticket.state in {"UNKNOWN", "RUNNING"}:
            started = ticket.result.get("started_at")
            if ticket.state == "RUNNING" and started:
                if datetime.now(UTC) - datetime.fromisoformat(started) < timedelta(minutes=10):
                    return
            mode = "reconcile"
        elif ticket.state != "SUCCEEDED":
            return
        if mode:
            ticket.state = "RUNNING"
            attempt = str(uuid4())
            ticket.result = {
                **ticket.result,
                "started_at": datetime.now(UTC).isoformat(),
                "attempt": attempt,
            }
            op.state = "RUNNING"
            session.add(
                WfsCreationEvent(
                    operation_id=ident,
                    actor_uid="wfs-worker",
                    kind=f"started_{mode}",
                    evidence={"ticket_id": str(ticket_id)},
                )
            )
            session.commit()
    if mode:
        try:
            values = (
                gateway.create(str(ticket_id), snapshot, allocation)
                if mode == "create"
                else gateway.reconcile(str(ticket_id), snapshot)
            )
            ids = actual_ids(values)
            state, error = "SUCCEEDED", None
        except DefinitiveRejection:
            ids, state, error = [], "FAILED", "WFS_PLATFORM_REJECTED"
        except Exception:
            # No response, malformed result and process/network ambiguity keep all holds.
            ids, state, error = [], "UNKNOWN", "WFS_RESULT_UNKNOWN"
        with factory() as session:
            ticket = session.scalar(
                select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
            )
            if ticket.result.get("attempt") != attempt:
                return  # A newer reconciliation owns this result; do not overwrite it.
            ticket.state, ticket.error_code = state, error
            ticket.result = {**ticket.result, "labels": {sid: {"state": "PENDING"} for sid in ids}}
            session.add(
                WfsCreationEvent(
                    operation_id=ident,
                    actor_uid="wfs-worker",
                    kind=state.lower(),
                    evidence={"ticket_id": str(ticket_id)},
                )
            )
            session.commit()
    # Serializing label retrieval on the ticket prevents concurrent retries overwriting results.
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.state != "SUCCEEDED":
            return
        labels = dict(ticket.result.get("labels", {}))
        for sid, value in labels.items():
            if value["state"] == "READY":
                continue
            try:
                pdf = gateway.label(sid, snapshot)
                if (
                    not isinstance(pdf, bytes)
                    or not pdf.startswith(b"%PDF-")
                    or len(pdf) > 10_000_000
                ):
                    raise ValueError("invalid label")
                labels[sid] = {"state": "READY", "pdf": base64.b64encode(pdf).decode("ascii")}
            except Exception:
                labels[sid] = {"state": "FAILED"}
        ticket.result = {**ticket.result, "labels": labels}
        session.add(
            WfsCreationEvent(
                operation_id=ident,
                actor_uid="wfs-worker",
                kind="labels",
                evidence={
                    "ticket_id": str(ticket_id),
                    "states": {sid: v["state"] for sid, v in labels.items()},
                },
            )
        )
        session.commit()
