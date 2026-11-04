"""Durable execution boundary: uncertain writes are read back, never blindly re-sent.

Per planned shipment (ticket), Rocky 2026-11-04:

* Walmart refuses, or the request provably never left -> FAILED with the reason; boxes freed.
* Walmart answers with the shipment -> SUCCEEDED, labels fetched.
* No trustworthy answer (timeout, 5xx, accepted without ids) -> stays RUNNING ("提交中") and
  is read back by our order id (= ticket id) every 3 minutes, at most 10 times; still not
  found after the 10th read -> FAILED ("查询超时"), boxes freed.
* Retry (FAILED only) first reads back by the same order id; only if Walmart has nothing is
  the same order sent again, so one batch of boxes can never become two shipments.
"""

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.modules.pmc_wfs.creation_config import POLL_INTERVAL_SECONDS, POLL_MAX_ATTEMPTS
from app.modules.pmc_wfs.creation_models import (
    WfsBoxHold,
    WfsCreation,
    WfsCreationEvent,
    WfsCreationTicket,
)
from app.modules.pmc_wfs.creation_service import guard_write, manually_approved
from app.modules.pmc_wfs.walmart_gateway import DefinitiveRejection, NotSent, ResultUnknown

__all__ = ["DefinitiveRejection", "run_operation", "shipments_of"]

Schedule = Callable[[str, str, int], None]
TIMEOUT_REASON = (
    f"已每 {POLL_INTERVAL_SECONDS // 60} 分钟查询一次、共 {POLL_MAX_ATTEMPTS} 次，"
    "仍未在 Walmart 查到这票货件，按失败处理"
)


def shipments_of(values) -> list[dict]:
    """Adapter result -> verified shipment records (ids unique, bounded)."""
    if not isinstance(values, list) or len(values) > 5000:
        raise ValueError("unverified shipment result")
    records = []
    for value in values:
        record = {"shipment_id": value} if isinstance(value, str) else dict(value)
        sid = record.get("shipment_id")
        if not isinstance(sid, str) or not sid.strip() or len(sid) > 128:
            raise ValueError("unverified shipment result")
        records.append(record)
    if len({r["shipment_id"] for r in records}) != len(records):
        raise ValueError("unverified shipment result")
    return records


# Kept for callers that only need ids.
def actual_ids(values):
    records = shipments_of(values)
    if not records:
        raise ValueError("unverified shipment result")
    return [r["shipment_id"] for r in records]


def _event(session, ident, kind, **evidence):
    session.add(
        WfsCreationEvent(operation_id=ident, actor_uid="wfs-worker", kind=kind, evidence=evidence)
    )


def _snapshot(op, ticket):
    return {
        **op.snapshot,
        "approval_ref": op.approval_ref,
        "ticket_boxes": ticket.allocation.get("boxes"),
    }


def release_holds(session, ident, ticket, reason_code):
    """Failed or rejected: the ticket's boxes go back to the packing order."""
    count = session.scalar(
        select(func.count()).select_from(WfsBoxHold).where(WfsBoxHold.ticket_id == ticket.id)
    )
    if count:
        session.execute(delete(WfsBoxHold).where(WfsBoxHold.ticket_id == ticket.id))
        _event(
            session,
            ident,
            "holds_released",
            ticket_id=str(ticket.id),
            boxes=count,
            reason=reason_code,
        )
    return count


def _fail(session, ident, ticket, code, reason):
    ticket.state, ticket.error_code = "FAILED", code[:64]
    result = {k: v for k, v in ticket.result.items() if k != "polling"}
    ticket.result = {
        **result,
        "error_message": reason[:500],
        "failed_at": datetime.now(UTC).isoformat(),
    }
    _event(session, ident, "failed", ticket_id=str(ticket.id), code=code, reason=reason[:500])
    release_holds(session, ident, ticket, code)


def _succeed(session, ident, ticket, records):
    shipments = {r["shipment_id"]: r for r in records}
    ticket.state, ticket.error_code = "SUCCEEDED", None
    result = {k: v for k, v in ticket.result.items() if k not in ("polling", "error_message")}
    labels = dict(result.get("labels", {}))
    for sid in shipments:
        labels.setdefault(sid, {"state": "PENDING"})
    ticket.result = {
        **result,
        "shipments": shipments,
        "labels": labels,
        "succeeded_at": datetime.now(UTC).isoformat(),
    }
    _event(session, ident, "succeeded", ticket_id=str(ticket.id), shipments=sorted(shipments))


def _start_polling(session, ident, ticket, code, schedule):
    now = datetime.now(UTC)
    ticket.state, ticket.error_code = "RUNNING", code[:64] if code else None
    ticket.result = {
        **ticket.result,
        "polling": {
            "count": 0,
            "max": POLL_MAX_ATTEMPTS,
            "next_at": (now + timedelta(seconds=POLL_INTERVAL_SECONDS)).isoformat(),
            "since": now.isoformat(),
        },
    }
    _event(session, ident, "polling_started", ticket_id=str(ticket.id), code=code)
    return True


def run_operation(factory, gateway, ident, action="execute", schedule: Schedule | None = None):
    """Callable by Celery or an isolated test; factory, adapter and scheduler are explicit."""
    ident = UUID(str(ident))
    with factory() as session:
        guard_write(session)
        op = session.get(WfsCreation, ident)
        if op is None:
            return
        if not manually_approved(op):
            # Red line: no Walmart call (create, read-back or label) without a written
            # human approval for this operation. Record the refusal, touch nothing else.
            _event(session, ident, "refused_unapproved", action=action, state=op.state)
            session.commit()
            return
        if action in ("execute", "retry"):
            gateway.validate(op.snapshot)
        ticket_ids = list(
            session.scalars(
                select(WfsCreationTicket.id)
                .where(WfsCreationTicket.operation_id == ident)
                .order_by(WfsCreationTicket.number)
            )
        )
    poll_again = False
    for ticket_id in ticket_ids:
        poll_again |= execute_ticket(factory, gateway, ident, ticket_id, action)
    with factory() as session:
        op = session.scalar(select(WfsCreation).where(WfsCreation.id == ident).with_for_update())
        states = list(
            session.scalars(
                select(WfsCreationTicket.state).where(WfsCreationTicket.operation_id == ident)
            )
        )
        if states and all(s == "SUCCEEDED" for s in states):
            op.state = "SUCCEEDED"
        elif "RUNNING" in states:
            op.state = "RUNNING"
        elif "UNKNOWN" in states:
            op.state = "UNKNOWN"
        elif "QUEUED" in states:
            op.state = "QUEUED"  # approved, not yet executed
        elif "SUCCEEDED" in states:
            op.state = "PARTIAL"
        else:
            op.state = "FAILED"
        session.commit()
    if poll_again and schedule is not None:
        schedule(str(ident), "poll", POLL_INTERVAL_SECONDS)


def _claim(factory, ident, ticket_id, action):
    """Decide under the ticket row lock what this run does; returns (mode, snapshot, ...)."""
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        op = session.get(WfsCreation, ident)
        if not manually_approved(op):
            return None
        polling = ticket.result.get("polling")
        mode = None
        if ticket.state == "QUEUED" and action in ("execute", "retry", "reconcile"):
            mode = "create"
        elif ticket.state == "RUNNING" and polling and action == "poll":
            mode = "poll"
        elif ticket.state in ("RUNNING", "UNKNOWN") and action == "reconcile":
            started = ticket.result.get("started_at")
            if ticket.state == "RUNNING" and not polling and started:
                if datetime.now(UTC) - datetime.fromisoformat(started) < timedelta(minutes=10):
                    return None  # a worker is still inside the create call
            mode = "check"
        elif ticket.state == "SUCCEEDED":
            return ("labels", _snapshot(op, ticket), ticket.allocation, None)
        if mode is None:
            return None
        attempt = str(uuid4())
        if mode == "create":
            submissions = int(ticket.result.get("submissions", 0))
            ticket.result = {
                **{k: v for k, v in ticket.result.items() if k != "error_message"},
                "started_at": datetime.now(UTC).isoformat(),
                "attempt": attempt,
                "submissions": submissions + 1,
            }
            ticket.state, ticket.error_code = "RUNNING", None
            op.state = "RUNNING"
            _event(
                session,
                ident,
                "started_create",
                ticket_id=str(ticket_id),
                submission=submissions + 1,
            )
            mode = "resubmit" if submissions else "create"
        else:
            ticket.result = {**ticket.result, "attempt": attempt}
        session.commit()
        return (mode, _snapshot(op, ticket), ticket.allocation, attempt)


def execute_ticket(factory, gateway, ident, ticket_id, action) -> bool:
    """Run one ticket; returns True when a later poll must be scheduled."""
    claimed = _claim(factory, ident, ticket_id, action)
    if claimed is None:
        return False
    mode, snapshot, allocation, attempt = claimed
    if mode == "labels":
        _labels(factory, gateway, ident, ticket_id, snapshot)
        return False
    outcome, payload = None, None
    if mode == "resubmit":
        # Retry: ask Walmart first whether our order id already exists.
        try:
            found = gateway.reconcile(str(ticket_id), snapshot)
            if found:
                outcome, payload = "ok", shipments_of(found)
        except Exception as error:
            outcome, payload = "unknown", getattr(error, "code", "WFS_RESULT_UNKNOWN")
    if outcome is None and mode in ("create", "resubmit"):
        try:
            records = shipments_of(gateway.create(str(ticket_id), snapshot, allocation))
            outcome, payload = ("ok", records) if records else ("unknown", "WFS_ACCEPTED")
        except DefinitiveRejection as error:
            outcome, payload = "rejected", (error.code, error.reason or "Walmart 拒绝了请求")
        except NotSent as error:
            outcome, payload = "not_sent", (error.code, error.reason or error.code)
        except ResultUnknown as error:
            outcome, payload = "unknown", error.code
        except Exception:
            # No response, malformed result and process/network ambiguity keep all holds.
            outcome, payload = "unknown", "WFS_RESULT_UNKNOWN"
    if mode in ("poll", "check"):
        try:
            found = gateway.reconcile(str(ticket_id), snapshot)
            outcome, payload = ("ok", shipments_of(found)) if found else ("missing", None)
        except Exception as error:
            outcome, payload = "missing", getattr(error, "code", "WFS_RESULT_UNKNOWN")
    poll_again = False
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.result.get("attempt") != attempt:
            return False  # A newer run owns this ticket; do not overwrite it.
        if outcome == "ok":
            _succeed(session, ident, ticket, payload)
            _resolve(gateway, ticket_id, "ok", "read back / created")
        elif outcome in ("rejected", "not_sent"):
            _fail(session, ident, ticket, *payload)
        elif outcome == "unknown":
            poll_again = _start_polling(session, ident, ticket, payload, None)
        elif outcome == "missing" and mode == "poll":
            polling = dict(ticket.result["polling"])
            polling["count"] += 1
            polling["last_checked_at"] = datetime.now(UTC).isoformat()
            if payload:
                polling["last_error"] = payload
            if polling["count"] >= polling.get("max", POLL_MAX_ATTEMPTS):
                ticket.result = {**ticket.result, "polling": polling}
                _fail(session, ident, ticket, "WFS_RESULT_TIMEOUT", TIMEOUT_REASON)
                _resolve(gateway, ticket_id, "failed", "not found after polling")
            else:
                polling["next_at"] = (
                    datetime.now(UTC) + timedelta(seconds=POLL_INTERVAL_SECONDS)
                ).isoformat()
                ticket.result = {**ticket.result, "polling": polling}
                _event(session, ident, "polled", ticket_id=str(ticket_id), count=polling["count"])
                poll_again = True
        elif outcome == "missing" and mode == "check" and ticket.state == "UNKNOWN":
            # A pre-polling UNKNOWN ticket joins the regular 3-minute schedule.
            poll_again = _start_polling(
                session, ident, ticket, payload or "WFS_RESULT_UNKNOWN", None
            )
        session.commit()
        succeeded = ticket.state == "SUCCEEDED"
    if succeeded:
        _labels(factory, gateway, ident, ticket_id, snapshot)
    return poll_again


def _resolve(gateway, ticket_id, outcome, note):
    resolve = getattr(gateway, "resolve", None)
    if resolve is not None:
        resolve(str(ticket_id), outcome, note)


def _labels(factory, gateway, ident, ticket_id, snapshot):
    # Serializing label retrieval on the ticket prevents concurrent retries overwriting results.
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.state != "SUCCEEDED":
            return
        labels = dict(ticket.result.get("labels", {}))
        shipments = ticket.result.get("shipments", {})
        single = len(labels) == 1
        for sid, value in labels.items():
            if value["state"] == "READY":
                continue
            cartons = (shipments.get(sid) or {}).get("cartons") or (
                ticket.allocation.get("boxes") if single else None
            )
            try:
                pdf = gateway.label(sid, snapshot, cartons=cartons)
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
        _event(
            session,
            ident,
            "labels",
            ticket_id=str(ticket_id),
            states={sid: v["state"] for sid, v in labels.items()},
        )
        session.commit()
